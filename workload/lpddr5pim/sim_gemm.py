"""Configure and run baseline or RTP GEMM simulations on LPDDR5-PIM."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ramulator

TRACE_PATH = "workload/lpddr5pim/lpddr5pim_gemm.trace"
ORG_PRESET    = "LPDDR5PIM_32Gb_x16"
TIMING_PRESET = "LPDDR5PIM_8533"
CLOCK_RATIO   = 1

NUM_CHANNELS = 4
NUM_RANKS    = 2


_VARIANT_MAP = {
    "baseline": ("LPDDR5PIM",     "LPDDR5PIM"),
    "rtp":      ("LPDDR5PIM_RTP", "LPDDR5PIM_RTP"),
}


def build_sim(trace_path, org_preset=ORG_PRESET,
              timing_preset=TIMING_PRESET, clock_ratio=CLOCK_RATIO,
              variant="baseline", num_channels=NUM_CHANNELS, num_ranks=NUM_RANKS,
              tile_segments=1, cmd_trace_path=None):
    dram_name, ctrl_name = _VARIANT_MAP[variant]
    dram = getattr(ramulator.dram, dram_name)(
        org_preset=org_preset,
        timing_preset=timing_preset,
        rank=num_ranks,
    )
    controllers = []
    for _ in range(num_channels):
        controller_args = {
            "dram": dram,
            "scheduler": ramulator.scheduler.FRFCFS(),
            "refresh_manager": ramulator.refresh_manager.PerBank(),
            "row_policy": ramulator.row_policy.Open(),
            "addr_mapper": ramulator.addr_mapper.RoBaRaCoCh(),
        }
        if variant == "rtp":
            controller_args["mini_tile_segments"] = tile_segments
        if cmd_trace_path is not None:
            controller_args["controller_plugins"] = [
                ramulator.controller_plugin.CmdTraceRecorder(path=cmd_trace_path)
            ]
        controllers.append(getattr(ramulator.controller, ctrl_name)(
            **controller_args
        ))
    mem = ramulator.memory_system.GenericDRAM(
        clock_ratio=clock_ratio,
        controllers=controllers,
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(interleave_bits=0),
    )
    fe = ramulator.frontend.PIMTrace(
        clock_ratio=clock_ratio,
        path=trace_path,
        max_issue_per_cycle=num_channels,
        drain_after_trace=True,
    )
    return fe, mem


def main():
    ap = argparse.ArgumentParser(description="LPDDR5-PIM GEMM simulation")
    ap.add_argument("--variant", default="baseline", choices=["baseline", "rtp"],
                    help="Row activation variant: baseline / rtp (Pipelined Row Activation)")
    ap.add_argument("--trace",      default=TRACE_PATH)
    ap.add_argument("--org",          default=ORG_PRESET)
    ap.add_argument("--timing",       default=TIMING_PRESET)
    ap.add_argument("--num-channels", type=int, default=NUM_CHANNELS)
    ap.add_argument("--num-ranks",    type=int, default=NUM_RANKS)
    ap.add_argument("--N",          type=int,   default=2048, help="Output neurons (weight rows)")
    ap.add_argument("--K",          type=int,   default=4096, help="Input features (weight cols)")
    ap.add_argument("--M",          type=int,   default=1,    help="Input tokens (activation cols)")
    ap.add_argument("--data-size",  type=float, default=0.5)
    ap.add_argument("--mini-tile",  action="store_true", default=False,
                    help="Split each DRAM row into 2 half-row sets (mini-tile mode)")
    ap.add_argument("--tile-segments", type=int, choices=(1, 2, 4), default=None,
                    help="Equal tiles per row: 1=full, 2=half, 4=quarter")
    ap.add_argument("--cmd-trace", default=None,
                    help="Record issued commands to this path plus .chN suffix")
    args = ap.parse_args()

    if args.tile_segments is None:
        tile_segments = 2 if args.mini_tile else 1
    elif args.mini_tile and args.tile_segments != 2:
        ap.error("--mini-tile conflicts with --tile-segments other than 2")
    else:
        tile_segments = args.tile_segments

    from workload.lpddr5pim.gen_trace_gemm import run_gemm
    run_gemm(
        args.trace,
        N=args.N, K=args.K, M=args.M,
        data_size=args.data_size,
        tile_segments=tile_segments,
    )

    fe, mem = build_sim(trace_path=args.trace, org_preset=args.org,
                        timing_preset=args.timing, variant=args.variant,
                        num_channels=args.num_channels, num_ranks=args.num_ranks,
                        tile_segments=tile_segments,
                        cmd_trace_path=args.cmd_trace)
    sim = ramulator.Simulation(fe, mem)
    sim.run()

    stats = sim.stats
    if not stats:
        return

    ch_stats = stats["memory_system"]["controller"]
    if isinstance(ch_stats, list):
        cycles   = max(c["cycles"] for c in ch_stats)
        pim_ops  = sum(c.get("pim_queue_len", 0) for c in ch_stats)
        rd_reqs  = sum(c.get("num_read_reqs",  0) for c in ch_stats)
        wr_reqs  = sum(c.get("num_write_reqs", 0) for c in ch_stats)
        row_hits = sum(c.get("row_hits",       0) for c in ch_stats)
        row_miss = sum(c.get("row_misses",     0) for c in ch_stats)
        avg_lat  = ch_stats[0].get("avg_read_latency", "N/A")
    else:
        cycles   = ch_stats["cycles"]
        pim_ops  = ch_stats.get("pim_queue_len", "N/A")
        rd_reqs  = ch_stats.get("num_read_reqs",  0)
        wr_reqs  = ch_stats.get("num_write_reqs", 0)
        row_hits = ch_stats.get("row_hits",       0)
        row_miss = ch_stats.get("row_misses",     0)
        avg_lat  = ch_stats.get("avg_read_latency", "N/A")
    variants = {"baseline": "baseline", "rtp": "RTP"}
    label = f"tiled, {variants[args.variant]}"
    useful_macs = args.N * args.K * args.M
    dram_name = _VARIANT_MAP[args.variant][0]
    timing = getattr(ramulator.dram, dram_name).timing_presets[args.timing]
    tck_ps = timing["tCK_ps"]
    print(f"\n=== LPDDR5-PIM GEMM ({label}) Simulation Results ===")
    print(f"  Tile segments/row:   {tile_segments}")
    print(f"  Cycles:              {cycles}")
    print(f"  Elapsed time (us):   {cycles * tck_ps / 1_000_000:.3f}")
    print(f"  Useful MACs/cycle:   {useful_macs / cycles:.3f}")
    print(f"  Useful ops/cycle:    {2 * useful_macs / cycles:.3f}")
    print(f"  Effective TOPS:      {2 * useful_macs / (cycles * tck_ps):.3f}")
    print(f"  Avg read latency:    {avg_lat}")
    print(f"  Read requests:       {rd_reqs}")
    print(f"  Write requests:      {wr_reqs}")
    print(f"  Row hits:            {row_hits}")
    print(f"  Row misses:          {row_miss}")
    print(f"  PIM ops total:       {pim_ops}")


if __name__ == "__main__":
    main()
else:
    fe, mem = build_sim(trace_path=TRACE_PATH, variant="baseline")
    sim = ramulator.Simulation(fe, mem)
