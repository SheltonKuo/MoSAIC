"""Generate tiled GEMM traces for LPDDR5-PIM, including multi-row K tiling."""

import argparse
import math
import os


class Org:
    channel       = 4
    rank          = 2
    bankgroup     = 4
    bank          = 4
    row           = 1 << 17
    column        = 1 << 10
    channel_width = 16
    prefetch_size = 16


class AddressEncoder:
    """Encode CacheLineInterleave(0) plus RoBaRaCoCh coordinates."""

    def __init__(self, org):
        self.org = org
        if org.channel & (org.channel - 1):
            raise ValueError("channel count must be a power of two")
        self.channel_bits = int(math.log2(org.channel))
        self.columns_per_row = org.column // org.prefetch_size

    def __call__(self, channel, rank, bankgroup, bank, row, column):
        org = self.org
        limits = (
            ("channel", channel, org.channel),
            ("rank", rank, org.rank),
            ("bankgroup", bankgroup, org.bankgroup),
            ("bank", bank, org.bank),
            ("row", row, org.row),
            ("column", column, self.columns_per_row),
        )
        for name, value, limit in limits:
            if not 0 <= value < limit:
                raise ValueError(f"{name}={value} is outside [0, {limit})")

        intra_burst = column + self.columns_per_row * (
            rank + org.rank * (bankgroup + org.bankgroup * (bank + org.bank * row))
        )
        return (intra_burst << (5 + self.channel_bits)) | (channel << 5)


def _fmt(op, addr):
    return f"{op} 0x{addr:010x}"


def _barriers(encode, n_ch, n_ra):
    return [
        _fmt("BARRIER", encode(ch, ra, 0, 0, 0, 0))
        for ch in range(n_ch)
        for ra in range(n_ra)
    ]


def run_gemm(output_path, *, N=2048, K=4096, M=1,
             data_size=0.5, org=None, mini_tile=False,
             tile_segments=None):
    """Generate a tiled GEMM trace.

    Parameters
    ----------
    N, K, M      : W is (N, K) weight in DRAM; A is (K, M) activation;
                   C is (N, M) output.
    data_size    : bytes per element (0.5=INT4, 1=INT8, 2=FP16)
    org          : Org object; defaults to LPDDR5PIM_8Gb_x16
    mini_tile    : if True, partition each DRAM row into 2 half-row sets and
                   pack consecutive MAC mini-tiles in issue order into the
                   first and second halves of one physical weight row.
    tile_segments: number of equal tiles per row (1, 2, or 4). None preserves
                   the legacy mini_tile flag: False selects 1, True selects 2.
    """
    if org is None:
        org = Org()
    if tile_segments is None:
        tile_segments = 2 if mini_tile else 1
    elif mini_tile and tile_segments != 2:
        raise ValueError("mini_tile=True conflicts with tile_segments != 2")
    if tile_segments not in (1, 2, 4):
        raise ValueError("tile_segments must be one of 1, 2, or 4")
    encode = AddressEncoder(org)
    n_ch  = org.channel
    n_ra  = org.rank
    n_bg  = org.bankgroup
    n_ba  = org.bank
    n_mac = org.prefetch_size * org.channel_width // int(data_size * 8)
    nc    = encode.columns_per_row
    transaction_bytes = org.prefetch_size * org.channel_width // 8

    if nc % tile_segments:
        raise ValueError("tile_segments must divide the burst columns per row")
    nc_eff = nc // tile_segments

    k_tile_elems  = nc_eff * n_mac
    n_k_tiles     = math.ceil(K / k_tile_elems)
    n_k_cols_list = []
    remaining = K
    for _ in range(n_k_tiles):
        chunk = min(remaining, k_tile_elems)
        n_k_cols_list.append(math.ceil(chunk / n_mac))
        remaining -= chunk

    n_N_par    = n_ch * n_ra * n_bg * n_ba
    n_N_serial = math.ceil(N / n_N_par)

    n_a_phys_rows = math.ceil(n_k_tiles / tile_segments)
    n_w_phys_rows = math.ceil(n_k_tiles * n_N_serial / tile_segments)

    a_base_row = 0
    w_base_row = M * n_a_phys_rows
    c_base_row = w_base_row + n_w_phys_rows

    lines = []

    for m in range(M):

        for k_tile, n_k_cols in enumerate(n_k_cols_list):

            a_phys_row = k_tile // tile_segments
            a_col_off = (k_tile % tile_segments) * nc_eff

            for ci in range(n_k_cols):
                for ch in range(n_ch):
                    for ra in range(n_ra):
                        addr = encode(
                            ch,
                            ra,
                            0,
                            0,
                            a_base_row + m * n_a_phys_rows + a_phys_row,
                            a_col_off + ci,
                        )
                        lines.append(_fmt("WR_BB", addr))

            for n_step in range(n_N_serial):
                linear_tile = k_tile * n_N_serial + n_step
                w_phys_row = linear_tile // tile_segments
                w_col_off = (linear_tile % tile_segments) * nc_eff
                for k_idx in range(n_k_cols):
                    for ch in range(n_ch):
                        for ra in range(n_ra):
                            addr = encode(
                                ch,
                                ra,
                                0,
                                0,
                                w_base_row + w_phys_row,
                                w_col_off + k_idx,
                            )
                            lines.append(_fmt("MAC_AB", addr))

                for bg in range(n_bg):
                    for ba in range(n_ba):
                        for ch in range(n_ch):
                            for ra in range(n_ra):
                                addr = encode(
                                    ch,
                                    ra,
                                    bg,
                                    ba,
                                    c_base_row + n_step,
                                    0,
                                )
                                lines.append(_fmt("MV_RB", addr))

        n_wb_cols = max(1, math.ceil(n_N_serial * data_size / transaction_bytes))
        for bg in range(n_bg):
            for ba in range(n_ba):
                for ci in range(n_wb_cols):
                    for ch in range(n_ch):
                        for ra in range(n_ra):
                            addr = encode(
                                ch,
                                ra,
                                bg,
                                ba,
                                c_base_row,
                                m * n_wb_cols + ci,
                            )
                            lines.append(_fmt("RD_RB", addr))
        lines.extend(_barriers(encode, n_ch, n_ra))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("# LPDDR5-PIM GEMM trace"
                " -- generated by workload/lpddr5pim/gen_trace_gemm.py\n")
        f.write(f"# W=({N},{K})  A=({K},{M})  data_size={data_size}\n")
        f.write(f"# org: ch={org.channel} ra={org.rank} bg={org.bankgroup}"
                f" ba={org.bank} row={org.row} col={org.column}\n")
        f.write(f"# tile: N_par={n_N_par} (ch={n_ch} x ra={n_ra}"
                f" x bg={n_bg} x ba={n_ba})"
                f"  K_per_tile={n_mac}  nc_eff={nc_eff}"
                f"  n_k_tiles={n_k_tiles} (activation_rows={n_a_phys_rows}"
                f" weight_rows={n_w_phys_rows})"
                f"  n_k_cols={n_k_cols_list}  n_N_serial={n_N_serial}"
                f"  tile_segments={tile_segments}\n")
        for line in lines:
            f.write(line + "\n")
    print(f"Generated {len(lines)} trace entries -> {output_path}")
    return len(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Generate LPDDR5-PIM GEMM trace")
    p.add_argument("--output",     default="workload/lpddr5pim/lpddr5pim_gemm.trace")
    p.add_argument("--N",          type=int,   default=2048, help="Output neurons (weight rows)")
    p.add_argument("--K",          type=int,   default=4096, help="Input features (weight cols)")
    p.add_argument("--M",          type=int,   default=1,    help="Input tokens (activation cols)")
    p.add_argument("--data-size",  type=float, default=0.5,
                   help="Bytes per element: 0.5=INT4, 1=INT8, 2=FP16")
    p.add_argument("--mini-tile",  action="store_true", default=False,
                   help="Split each DRAM row into 2 half-row sets (mini-tile mode)")
    p.add_argument("--tile-segments", type=int, choices=(1, 2, 4), default=None,
                   help="Equal tiles per row; overrides the default full-row layout")
    args = p.parse_args()

    run_gemm(
        args.output,
        N=args.N, K=args.K, M=args.M,
        data_size=args.data_size,
        mini_tile=args.mini_tile,
        tile_segments=args.tile_segments,
    )
