"""End-to-end transformer decode trace generator for LPDDR6-PIM."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from workload.lpddr5pim.gen_trace_transformer import (
    SUPPORTED_TILINGS,
    estimate_mapping_sizes,
    tile_segments_for_variant,
)
from workload.lpddr5pim.gen_trace_transformer import (
    generate_transformer_trace as _generate_transformer_trace,
)


@dataclass(frozen=True)
class Org:
    """32 GiB LPDDR6PIM_32Gb_x12 system used by sim_transformer.py."""

    standard_name: str = "LPDDR6-PIM"
    coordinate_order: str = "channel,rank,bankgroup,bank"
    address_mapping: str = (
        "CacheLineInterleave(0) + RoBaRaCoCh; channel bits above the "
        "32-byte offset, intra-channel LSB order column/rank/bg/bank/row"
    )
    channel: int = 4
    rank: int = 2
    bankgroup: int = 4
    bank: int = 4
    row: int = 1 << 17
    column: int = 1 << 10
    channel_width: int = 12
    prefetch_size: int = 16
    data_payload_bytes: int = 32

    @property
    def transaction_bytes(self) -> int:
        return self.data_payload_bytes

    @property
    def columns_per_row(self) -> int:
        return self.column // self.prefetch_size

    @property
    def row_bytes(self) -> int:
        return self.columns_per_row * self.transaction_bytes

    @property
    def rank_units(self) -> int:
        return self.channel * self.rank

    @property
    def banks_per_rank(self) -> int:
        return self.bankgroup * self.bank

    @property
    def total_banks(self) -> int:
        return self.rank_units * self.banks_per_rank


def generate_transformer_trace(
    output_path: str,
    mapping_path: str,
    *,
    model_config_path: str,
    prefix_length: int,
    variant: str = "baseline",
    kv_capacity: int | None = None,
    num_layers: int | None = None,
    mapped_num_layers: int | None = None,
    single_layer: bool = False,
    org: Org | None = None,
    mapping_org: Org | None = None,
) -> dict[str, Any]:
    return _generate_transformer_trace(
        output_path,
        mapping_path,
        model_config_path=model_config_path,
        prefix_length=prefix_length,
        variant=variant,
        kv_capacity=kv_capacity,
        num_layers=num_layers,
        mapped_num_layers=mapped_num_layers,
        single_layer=single_layer,
        org=Org() if org is None else org,
        mapping_org=mapping_org,
    )


def _default_output(prefix_length: int, variant: str, single_layer: bool) -> str:
    suffix = variant.replace("-", "_")
    if single_layer:
        suffix += "_single_layer"
    return f"workload/lpddr6pim/llama3_8b_decode_p{prefix_length}_{suffix}.trace"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an end-to-end LPDDR6-PIM transformer decode trace"
    )
    parser.add_argument("--prefix-length", type=int, default=512)
    parser.add_argument("--model-config", default="workload/modelconfig/llama3_8B.json")
    parser.add_argument("--variant", choices=SUPPORTED_TILINGS, default="baseline")
    parser.add_argument("--kv-capacity", type=int, default=None)
    layers = parser.add_mutually_exclusive_group()
    layers.add_argument("--num-layers", type=int, default=None)
    layers.add_argument("--single-layer", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--mapping", default=None)
    args = parser.parse_args()

    output = args.output or _default_output(
        args.prefix_length, args.variant, args.single_layer
    )
    mapping = args.mapping or str(Path(output).with_suffix(".mapping.json"))
    generate_transformer_trace(
        output,
        mapping,
        model_config_path=args.model_config,
        prefix_length=args.prefix_length,
        variant=args.variant,
        kv_capacity=args.kv_capacity,
        num_layers=args.num_layers,
        single_layer=args.single_layer,
    )


if __name__ == "__main__":
    main()


__all__ = [
    "Org", "SUPPORTED_TILINGS", "estimate_mapping_sizes",
    "generate_transformer_trace", "tile_segments_for_variant",
]
