"""Run an end-to-end single-token transformer decode on LPDDR6-PIM."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ramulator
from workload.lpddr6pim.gen_trace_transformer import (
    Org,
    SUPPORTED_TILINGS,
    estimate_mapping_sizes,
    generate_transformer_trace,
    tile_segments_for_variant,
)

ORG_PRESET = "LPDDR6PIM_32Gb_x12"
TIMING_PRESET = "LPDDR6PIM_10667"
CLOCK_RATIO = 1
NUM_CHANNELS = 4
NUM_RANKS = 2
STANDARD_NAME = "LPDDR6-PIM"

_PIM_VARIANTS = {
    "baseline": ("LPDDR6PIM", "LPDDR6PIM"),
    "rtp": ("LPDDR6PIM_RTP", "LPDDR6PIM_RTP"),
}


def build_sim(
    trace_path: str,
    *,
    org_preset: str = ORG_PRESET,
    timing_preset: str = TIMING_PRESET,
    pim_variant: str = "baseline",
    clock_ratio: int = CLOCK_RATIO,
    num_channels: int = NUM_CHANNELS,
    num_ranks: int = NUM_RANKS,
    tile_segments: int = 1,
):
    dram_name, controller_name = _PIM_VARIANTS[pim_variant]
    dram = getattr(ramulator.dram, dram_name)(
        org_preset=org_preset,
        timing_preset=timing_preset,
        rank=num_ranks,
    )
    controllers = []
    for _ in range(num_channels):
        controller_args = dict(
            dram=dram,
            scheduler=ramulator.scheduler.FRFCFS(),
            refresh_manager=ramulator.refresh_manager.AllBank(),
            row_policy=ramulator.row_policy.Open(),
            addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        )
        if pim_variant == "rtp":
            controller_args["mini_tile_segments"] = tile_segments
        controllers.append(getattr(ramulator.controller, controller_name)(
            **controller_args
        ))
    memory = ramulator.memory_system.GenericDRAM(
        clock_ratio=clock_ratio,
        controllers=controllers,
        channel_mapper=ramulator.channel_mapper.CacheLineInterleave(interleave_bits=0),
    )
    frontend = ramulator.frontend.PIMTrace(
        clock_ratio=clock_ratio,
        path=trace_path,
        max_issue_per_cycle=num_channels,
    )
    return frontend, memory


def _default_trace(prefix_length: int, variant: str, single_layer: bool) -> str:
    suffix = variant.replace("-", "_")
    if single_layer:
        suffix += "_single_layer"
    return f"workload/lpddr6pim/llama3_8b_decode_p{prefix_length}_{suffix}.trace"


def _mapping_is_compatible(
    path: str,
    *,
    prefix_length: int,
    variant: str,
    kv_capacity: int | None,
    num_layers: int | None,
) -> bool:
    try:
        with open(path, encoding="utf-8") as mapping_file:
            mapping = json.load(mapping_file)
    except (OSError, ValueError):
        return False

    model = mapping.get("model", {})
    decode = mapping.get("decode", {})
    layers_match = (
        model.get("simulated_layers") == num_layers
        if num_layers is not None
        else model.get("simulated_layers") == model.get("configured_layers")
    )
    return (
        mapping.get("schema_version") == 5
        and mapping.get("organization", {}).get("standard") == STANDARD_NAME
        and decode.get("prefix_length") == prefix_length
        and decode.get("kv_capacity") == (kv_capacity or prefix_length + 1)
        and mapping.get("tiling", {}).get("variant") == variant
        and layers_match
    )


def _format_size(byte_count: float) -> str:
    return f"{byte_count / (1 << 30):.3f} GiB ({byte_count / (1 << 20):.1f} MiB)"


def _print_memory_sizes(mapping: dict) -> None:
    sizes = estimate_mapping_sizes(mapping)
    print("\n=== LPDDR6-PIM Transformer Memory Size Estimate ===")
    print("  Category          Real matrix size          Occupied tiled size")
    for label, category in (
        ("Static weights", "static_weights"),
        ("KV cache", "kv_cache"),
        ("Total", "total"),
    ):
        print(
            f"  {label:<16}  {_format_size(sizes[category]['real_bytes']):<24}  "
            f"{_format_size(sizes[category]['occupied_bytes'])}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="LPDDR6-PIM transformer decode simulation")
    parser.add_argument("--prefix-length", type=int, default=512)
    parser.add_argument("--model-config", default="workload/modelconfig/llama3_8B.json")
    parser.add_argument("--variant", choices=SUPPORTED_TILINGS, default="baseline")
    parser.add_argument("--pim-variant", choices=tuple(_PIM_VARIANTS), default="baseline")
    parser.add_argument("--trace", default=None)
    parser.add_argument("--mapping", default=None)
    parser.add_argument("--kv-capacity", type=int, default=None)
    layers = parser.add_mutually_exclusive_group()
    layers.add_argument("--num-layers", type=int, default=None)
    layers.add_argument("--single-layer", action="store_true")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--org", default=ORG_PRESET)
    parser.add_argument("--timing", default=TIMING_PRESET)
    parser.add_argument("--num-channels", type=int, default=NUM_CHANNELS)
    parser.add_argument("--num-ranks", type=int, default=NUM_RANKS)
    args = parser.parse_args()

    num_layers = 1 if args.single_layer else args.num_layers
    trace_path = args.trace or _default_trace(args.prefix_length, args.variant, args.single_layer)
    mapping_path = args.mapping or str(Path(trace_path).with_suffix(".mapping.json"))
    compatible = _mapping_is_compatible(
        mapping_path,
        prefix_length=args.prefix_length,
        variant=args.variant,
        kv_capacity=args.kv_capacity,
        num_layers=num_layers,
    )
    mapping = None
    if args.regenerate or not os.path.exists(trace_path) or not compatible:
        mapping = generate_transformer_trace(
            trace_path,
            mapping_path,
            model_config_path=args.model_config,
            prefix_length=args.prefix_length,
            variant=args.variant,
            kv_capacity=args.kv_capacity,
            num_layers=num_layers,
            single_layer=args.single_layer,
        )
    if mapping is None:
        with open(mapping_path, encoding="utf-8") as mapping_file:
            mapping = json.load(mapping_file)
    _print_memory_sizes(mapping)
    if args.generate_only:
        return

    frontend, memory = build_sim(
        trace_path,
        org_preset=args.org,
        timing_preset=args.timing,
        pim_variant=args.pim_variant,
        num_channels=args.num_channels,
        num_ranks=args.num_ranks,
        tile_segments=tile_segments_for_variant(args.variant, Org()),
    )
    simulation = ramulator.Simulation(frontend, memory)
    simulation.run()
    channel_stats = simulation.stats["memory_system"]["controller"]
    channels = channel_stats if isinstance(channel_stats, list) else [channel_stats]
    print("\n=== LPDDR6-PIM Transformer Decode Simulation Results ===")
    print(f"  Prefix/context:      {args.prefix_length}/{args.prefix_length + 1}")
    print(f"  Tile variant:        {args.variant}")
    print(f"  PIM variant:         {args.pim_variant}")
    print(f"  Cycles:              {max(channel['cycles'] for channel in channels)}")
    print(f"  Read requests:       {sum(c.get('num_read_reqs', 0) for c in channels)}")
    print(f"  Write requests:      {sum(c.get('num_write_reqs', 0) for c in channels)}")
    print(f"  Row hits:            {sum(c.get('row_hits', 0) for c in channels)}")
    print(f"  Row misses:          {sum(c.get('row_misses', 0) for c in channels)}")
    print(f"  PIM ops total:       {sum(c.get('pim_queue_len', 0) for c in channels)}")
    print(f"  Mapping:             {mapping_path}")


if __name__ == "__main__":
    main()
