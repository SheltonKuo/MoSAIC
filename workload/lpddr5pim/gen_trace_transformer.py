"""Generate transformer decode traces and mapping manifests for LPDDR5-PIM."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WEIGHT_BYTES = 0.5
ACTIVATION_BYTES = 2
KV_BYTES = 2

_DTYPE_BYTES = {
    "int4": WEIGHT_BYTES,
    "fp16": ACTIVATION_BYTES,
}


@dataclass(frozen=True)
class Org:
    """LPDDR5PIM_32Gb_x16 system used by sim_gemm.py."""

    standard_name: str = "LPDDR5-PIM"
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
    channel_width: int = 16
    prefetch_size: int = 16

    @property
    def transaction_bytes(self) -> int:
        return self.prefetch_size * self.channel_width // 8

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


class AddressEncoder:
    """Encode CacheLineInterleave plus RoBaRaCoCh coordinates."""

    def __init__(self, org: Org):
        self.org = org
        if org.channel & (org.channel - 1):
            raise ValueError("channel count must be a power of two")
        self.channel_bits = int(math.log2(org.channel))

    def __call__(
        self,
        channel: int,
        rank: int,
        bankgroup: int,
        bank: int,
        row: int,
        column: int,
    ) -> int:
        org = self.org
        limits = (
            ("channel", channel, org.channel),
            ("rank", rank, org.rank),
            ("bankgroup", bankgroup, org.bankgroup),
            ("bank", bank, org.bank),
            ("row", row, org.row),
            ("column", column, org.columns_per_row),
        )
        for name, value, limit in limits:
            if not 0 <= value < limit:
                raise ValueError(f"{name}={value} is outside [0, {limit})")

        intra_burst = column + org.columns_per_row * (
            rank + org.rank * (bankgroup + org.bankgroup * (bank + org.bank * row))
        )
        return (intra_burst << (5 + self.channel_bits)) | (channel << 5)


class TraceWriter:
    """Buffered trace writer that does not retain the complete trace."""

    def __init__(self, path: str, header: list[str]):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._file = open(path, "w", encoding="utf-8")
        self._buffer: list[str] = []
        self.counts: Counter[str] = Counter()
        self.entry_count = 0
        for line in header:
            self.comment(line)

    def comment(self, text: str) -> None:
        self._append(f"# {text}")

    def emit(self, op: str, addr: int) -> None:
        self._append(f"{op} 0x{addr:010x}")
        self.counts[op] += 1
        self.entry_count += 1

    def _append(self, line: str) -> None:
        self._buffer.append(line)
        if len(self._buffer) >= 8192:
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            self._file.write("\n".join(self._buffer) + "\n")
            self._buffer.clear()

    def close(self) -> None:
        self.flush()
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def _ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def estimate_mapping_sizes(manifest: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Estimate logical and tiled physical bytes for weights and KV caches.

    ``real_bytes`` is the dense matrix size from shape and dtype. ``occupied_bytes``
    charges every required logical K tile at the configured tile size, including
    unused elements in the final K tile and output stripe. A mini-tile is charged
    as half a DRAM row, even when it is the only used half of a physical row.
    """
    organization = manifest["organization"]
    tile_bytes = (
        int(manifest["tiling"]["logical_columns_per_tile"])
        * int(organization["transaction_bytes"])
    )
    totals = {
        "static_weights": {"real_bytes": 0.0, "occupied_bytes": 0.0},
        "kv_cache": {"real_bytes": 0.0, "occupied_bytes": 0.0},
    }

    for region in manifest["regions"]:
        kind = region.get("kind")
        if kind == "weight":
            category = "static_weights"
        elif kind == "kv_cache":
            category = "kv_cache"
        else:
            continue

        dtype = region["dtype"]
        try:
            element_bytes = _DTYPE_BYTES[dtype]
        except KeyError as error:
            raise ValueError(f"unsupported mapped dtype: {dtype}") from error

        elements = math.prod(int(dimension) for dimension in region["shape"])
        totals[category]["real_bytes"] += elements * element_bytes
        totals[category]["occupied_bytes"] += (
            int(region["logical_k_tiles"])
            * int(region["n_serial"])
            * int(region["n_parallel"])
            * tile_bytes
        )

    totals["total"] = {
        metric: sum(totals[category][metric] for category in ("static_weights", "kv_cache"))
        for metric in ("real_bytes", "occupied_bytes")
    }
    return totals


def _rank_coords(rank_unit: int, org: Org) -> tuple[int, int]:
    return rank_unit // org.rank, rank_unit % org.rank


def _bank_coords(lane: int, org: Org) -> tuple[int, int]:
    return lane // org.bank, lane % org.bank


def _global_lane_coords(lane: int, org: Org) -> tuple[int, int, int, int]:
    rank_unit, bank_lane = divmod(lane, org.banks_per_rank)
    channel, rank = _rank_coords(rank_unit, org)
    bankgroup, bank = _bank_coords(bank_lane, org)
    return channel, rank, bankgroup, bank


SUPPORTED_TILINGS = ("baseline", "mini-tile", "mini-tile-16", "mini-tile-32")


def tile_columns_for_variant(variant: str, org: Org) -> int:
    if variant == "baseline":
        return org.columns_per_row
    if variant == "mini-tile":
        return org.columns_per_row // 2
    if variant.startswith("mini-tile-"):
        try:
            tile_columns = int(variant.rsplit("-", 1)[1])
        except ValueError as error:
            raise ValueError(f"invalid tiling variant: {variant}") from error
        if tile_columns in (16, 32) and org.columns_per_row % tile_columns == 0:
            return tile_columns
    raise ValueError(f"variant must be one of {SUPPORTED_TILINGS}")


def tile_segments_for_variant(variant: str, org: Org) -> int:
    return org.columns_per_row // tile_columns_for_variant(variant, org)


def _segments(k_dim: int, elem_bytes: float, variant: str, org: Org) -> list[dict[str, int]]:
    elems_per_burst = int(org.transaction_bytes / elem_bytes)
    tile_cols = tile_columns_for_variant(variant, org)
    tiles_per_row = org.columns_per_row // tile_cols
    tile_elems = tile_cols * elems_per_burst
    result = []
    elem_offset = 0
    logical_tile = 0
    while elem_offset < k_dim:
        elems = min(tile_elems, k_dim - elem_offset)
        physical_tile = logical_tile // tiles_per_row
        column_offset = (logical_tile % tiles_per_row) * tile_cols
        result.append(
            {
                "logical_tile": logical_tile,
                "physical_tile": physical_tile,
                "column_offset": column_offset,
                "columns": _ceil_div(elems, elems_per_burst),
                "element_offset": elem_offset,
                "elements": elems,
            }
        )
        logical_tile += 1
        elem_offset += elems
    return result


def _load_model_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as config_file:
        config = json.load(config_file)
    required = (
        "hidden_size",
        "intermediate_size",
        "num_attention_heads",
        "num_key_value_heads",
        "num_hidden_layers",
        "max_position_embeddings",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"model config is missing: {', '.join(missing)}")
    hidden = int(config["hidden_size"])
    heads = int(config["num_attention_heads"])
    kv_heads = int(config["num_key_value_heads"])
    if hidden % heads:
        raise ValueError("hidden_size must be divisible by num_attention_heads")
    if heads % kv_heads:
        raise ValueError("num_attention_heads must be divisible by num_key_value_heads")
    return config


def _model_name(path: str) -> str:
    """Return a stable, file-name-derived label for generated artifacts."""
    return Path(path).stem.lower().replace("-", "_")


def _moe_spec(config: dict[str, Any]) -> dict[str, int] | None:
    """Normalize the two MoE config conventions used by the supplied models."""
    expert_count = config.get("num_experts", config.get("num_local_experts"))
    active_count = config.get("num_experts_per_tok")
    if expert_count is None and active_count is None:
        return None
    if expert_count is None or active_count is None:
        raise ValueError("MoE model config must define expert count and num_experts_per_tok")
    expert_count, active_count = int(expert_count), int(active_count)
    if not 1 <= active_count <= expert_count:
        raise ValueError("num_experts_per_tok must be in [1, number of experts]")
    return {
        "num_experts": expert_count,
        "active_experts": active_count,
        "expert_intermediate_size": int(config.get("moe_intermediate_size", config["intermediate_size"])),
    }


class MappingPlanner:
    """Allocate weights and KV matrices with the same global bank striping."""

    def __init__(
        self,
        config: dict[str, Any],
        prefix_length: int,
        kv_capacity: int,
        variant: str,
        num_layers: int,
        org: Org,
    ):
        self.config = config
        self.prefix_length = prefix_length
        self.context_length = prefix_length + 1
        self.kv_capacity = kv_capacity
        self.variant = variant
        self.tile_columns = tile_columns_for_variant(variant, org)
        self.tiles_per_row = org.columns_per_row // self.tile_columns
        self.num_layers = num_layers
        self.org = org
        self.hidden = int(config["hidden_size"])
        self.intermediate = int(config["intermediate_size"])
        self.heads = int(config["num_attention_heads"])
        self.kv_heads = int(config["num_key_value_heads"])
        self.head_dim = self.hidden // self.heads
        self.moe = _moe_spec(config)
        self.n_parallel = org.total_banks
        self.weights: dict[tuple[int, str], dict[str, Any]] = {}
        self.kv: dict[tuple[int, int, str], dict[str, Any]] = {}
        self.regions: list[dict[str, Any]] = []

    def build(self) -> dict[str, Any]:
        next_static_row = 0

        def allocate_static_segments(
            segments: list[dict[str, int]], n_serial: int
        ) -> tuple[int, int, int]:
            """Allocate rows after linearizing tiles in MAC execution order."""
            nonlocal next_static_row
            rows = _ceil_div(len(segments) * n_serial, self.tiles_per_row)
            first = next_static_row
            next_static_row += rows
            return first, next_static_row, rows

        attention_shapes = (
            ("q_proj", self.hidden, self.hidden),
            ("k_proj", self.kv_heads * self.head_dim, self.hidden),
            ("v_proj", self.kv_heads * self.head_dim, self.hidden),
            ("o_proj", self.hidden, self.hidden),
        )
        for layer in range(self.num_layers):
            shapes = list(attention_shapes)
            if self.moe is None:
                shapes.extend(
                    (
                        ("gate_proj", self.intermediate, self.hidden),
                        ("up_proj", self.intermediate, self.hidden),
                        ("down_proj", self.hidden, self.intermediate),
                    )
                )
            else:
                shapes.append(("router", self.moe["num_experts"], self.hidden))
                expert_width = self.moe["expert_intermediate_size"]
                for expert in range(self.moe["num_experts"]):
                    shapes.extend(
                        (
                            (f"expert_{expert}_gate_proj", expert_width, self.hidden),
                            (f"expert_{expert}_up_proj", expert_width, self.hidden),
                            (f"expert_{expert}_down_proj", self.hidden, expert_width),
                        )
                    )
            for name, n_dim, k_dim in shapes:
                segments = _segments(k_dim, WEIGHT_BYTES, self.variant, self.org)
                n_serial = _ceil_div(n_dim, self.n_parallel)
                row_base, row_end, row_count = allocate_static_segments(
                    segments, n_serial
                )
                physical_tiles = _ceil_div(len(segments), self.tiles_per_row)
                mapping = {
                    "kind": "weight",
                    "layer": layer,
                    "name": name,
                    "shape": [n_dim, k_dim],
                    "dtype": "int4",
                    "scope": "all channel/rank/bank coordinates",
                    "row_base_per_bank": row_base,
                    "rows_per_bank": row_count,
                    "row_end_per_bank": row_end,
                    "n_parallel": self.n_parallel,
                    "n_serial": n_serial,
                    "logical_k_tiles": len(segments),
                    "physical_k_tiles": physical_tiles,
                    "segments": segments,
                    "output_mapping": (
                        "lane=n%n_parallel ordered channel,rank,bankgroup,bank; "
                        "serial=n//n_parallel"
                    ),
                    "mini_tile_allocation": (
                        "linear=logical_k_tile*n_serial+serial; "
                        f"row=base+linear//{self.tiles_per_row}; "
                        f"column_set=linear%{self.tiles_per_row}"
                        if self.tiles_per_row > 1
                        else "one full row per logical K tile"
                    ),
                }
                self.weights[layer, name] = mapping
                self.regions.append(mapping)

        next_kv_row = next_static_row
        for layer in range(self.num_layers):
            for kv_head in range(self.kv_heads):
                k_segments = _segments(self.head_dim, KV_BYTES, self.variant, self.org)
                k_n_serial = _ceil_div(self.kv_capacity, self.n_parallel)
                k_physical_tiles = max(segment["physical_tile"] for segment in k_segments) + 1
                k_rows = _ceil_div(
                    len(k_segments) * k_n_serial, self.tiles_per_row
                )
                key = {
                    "kind": "kv_cache",
                    "layer": layer,
                    "kv_head": kv_head,
                    "name": "key",
                    "shape": [self.kv_capacity, self.head_dim],
                    "dtype": "fp16",
                    "scope": "all channel/rank/bank coordinates",
                    "row_base_per_bank": next_kv_row,
                    "rows_per_bank": k_rows,
                    "row_end_per_bank": next_kv_row + k_rows,
                    "n_parallel": self.n_parallel,
                    "n_serial": k_n_serial,
                    "logical_k_tiles": len(k_segments),
                    "physical_k_tiles": k_physical_tiles,
                    "segments": k_segments,
                    "mapping": (
                        "lane=token%n_parallel ordered channel,rank,bankgroup,bank; "
                        "serial=token//n_parallel; mini-tile linear order is "
                        "logical_k_tile*n_serial+serial"
                    ),
                }
                self.kv[layer, kv_head, "key"] = key
                self.regions.append(key)
                next_kv_row += k_rows

                v_segments = _segments(self.kv_capacity, KV_BYTES, self.variant, self.org)
                v_physical_tiles = max(segment["physical_tile"] for segment in v_segments) + 1
                v_n_serial = _ceil_div(self.head_dim, self.n_parallel)
                v_rows = _ceil_div(
                    len(v_segments) * v_n_serial, self.tiles_per_row
                )
                value = {
                    "kind": "kv_cache",
                    "layer": layer,
                    "kv_head": kv_head,
                    "name": "value",
                    "shape": [self.head_dim, self.kv_capacity],
                    "dtype": "fp16",
                    "scope": "all channel/rank/bank coordinates",
                    "row_base_per_bank": next_kv_row,
                    "rows_per_bank": v_rows,
                    "row_end_per_bank": next_kv_row + v_rows,
                    "n_parallel": self.n_parallel,
                    "n_serial": v_n_serial,
                    "logical_k_tiles": len(v_segments),
                    "physical_k_tiles": v_physical_tiles,
                    "segments": v_segments,
                    "mapping": (
                        "lane=dimension%n_parallel ordered channel,rank,bankgroup,bank; "
                        "serial=dimension//n_parallel; mini-tile linear order is "
                        "logical_k_tile*n_serial+serial"
                    ),
                }
                self.kv[layer, kv_head, "value"] = value
                self.regions.append(value)
                next_kv_row += v_rows

        scratch_rows = max(
            256,
            _ceil_div(self.intermediate * ACTIVATION_BYTES, self.org.row_bytes),
        )
        scratch_base = next_kv_row
        if scratch_base + scratch_rows > self.org.row:
            used_mib = (scratch_base + scratch_rows) * self.org.row_bytes / (1 << 20)
            capacity_mib = self.org.row * self.org.row_bytes / (1 << 20)
            raise ValueError(
                f"mapping needs {scratch_base + scratch_rows} rows ({used_mib:.1f} MiB) "
                f"per bank, but {self.org.standard_name} has {self.org.row} rows "
                f"({capacity_mib:.1f} MiB)"
            )
        self.scratch = {
            "kind": "scratch",
            "name": "activation_and_rank_buffer_io",
            "scope": "all channel/rank/bank coordinates",
            "row_base_per_bank": scratch_base,
            "rows_per_bank": scratch_rows,
            "row_end_per_bank": scratch_base + scratch_rows,
            "dtype": "fp16",
        }
        self.regions.append(self.scratch)

        return {
            "schema_version": 5,
            "model": {
                "model_type": self.config.get("model_type", "unknown"),
                "hidden_size": self.hidden,
                "intermediate_size": self.intermediate,
                "num_attention_heads": self.heads,
                "num_key_value_heads": self.kv_heads,
                "head_dim": self.head_dim,
                "configured_layers": int(self.config["num_hidden_layers"]),
                "simulated_layers": self.num_layers,
                "moe": self.moe,
            },
            "decode": {
                "prefix_length": self.prefix_length,
                "new_token_position": self.prefix_length,
                "context_length": self.context_length,
                "kv_capacity": self.kv_capacity,
                "quantization": "W4A16KV16",
                "head_execution": "sequential",
                "q_heads_per_kv_head": self.heads // self.kv_heads,
            },
            "tiling": {
                "variant": self.variant,
                "logical_columns_per_tile": self.tile_columns,
                "tiles_per_physical_row": self.tiles_per_row,
                "physical_columns_per_row": self.org.columns_per_row,
                "weight_elements_per_burst": int(self.org.transaction_bytes / WEIGHT_BYTES),
                "fp16_elements_per_burst": int(self.org.transaction_bytes / KV_BYTES),
            },
            "organization": {
                "channels": self.org.channel,
                "ranks_per_channel": self.org.rank,
                "bankgroups_per_rank": self.org.bankgroup,
                "banks_per_bankgroup": self.org.bank,
                "rows_per_bank": self.org.row,
                "columns_per_row": self.org.columns_per_row,
                "transaction_bytes": self.org.transaction_bytes,
                "row_bytes": self.org.row_bytes,
                "standard": self.org.standard_name,
                "coordinate_order": self.org.coordinate_order,
                "address_mapping": self.org.address_mapping,
            },
            "policy": {
                "static_weights": (
                    f"output-neuron striped over all {self.org.total_banks} banks"
                ),
                "mini_tile_static_weights": (
                    f"consecutive MAC tiles fill all {self.tiles_per_row} column "
                    "sets of one row before advancing to the next row"
                ),
                "kv_cache": (
                    f"same global {self.org.total_banks}-bank striping as weight matrices"
                ),
                "softmax": "SFM on every rank-local score shard for each query head",
                "rope": "outside PIM with zero modeled latency before attention",
                "kv_cache_writeback": (
                    "deferred until after the modeled decode and omitted from trace"
                ),
                "external_boundaries": ("RD_RB+RD_BB before, WR_RB+WR_BB after residual/RMSNorm"),
                "excluded": ["embedding", "lm_head"],
            },
            "layer_schedule": [
                "q_proj",
                "k_proj",
                "v_proj",
                "external_rope_zero_time",
                "sequential_heads: qk -> sfm -> pv",
                "o_proj",
                "external_attention_residual_ffn_rmsnorm",
                *(
                    ["gate_proj", "up_proj", "act_func", "down_proj"]
                    if self.moe is None
                    else [
                        "router",
                        "external_topk_route",
                        "active_experts: gate_proj -> up_proj -> act_func -> down_proj",
                    ]
                ),
                "external_ffn_residual_next_rmsnorm",
            ],
            "regions": self.regions,
        }


class TransformerTraceGenerator:
    def __init__(self, planner: MappingPlanner, writer: TraceWriter):
        self.plan = planner
        self.writer = writer
        self.org = planner.org
        self.addr = AddressEncoder(self.org)
        self.scratch_base = planner.scratch["row_base_per_bank"]
        self.scratch_rows = planner.scratch["rows_per_bank"]

    def _scratch_addr(
        self,
        channel: int,
        rank: int,
        tx_index: int = 0,
        bankgroup: int = 0,
        bank: int = 0,
    ) -> int:
        row = self.scratch_base + (tx_index // self.org.columns_per_row) % self.scratch_rows
        column = tx_index % self.org.columns_per_row
        return self.addr(channel, rank, bankgroup, bank, row, column)

    def _barrier(self, rank_units: list[int] | None = None) -> None:
        units = range(self.org.rank_units) if rank_units is None else rank_units
        for rank_unit in units:
            channel, rank = _rank_coords(rank_unit, self.org)
            self.writer.emit("BARRIER", self._scratch_addr(channel, rank))

    def _emit_input_transfer(
        self,
        source: str,
        elements: int,
        rank_units: list[int] | None = None,
    ) -> None:
        transactions = _ceil_div(elements * ACTIVATION_BYTES, self.org.transaction_bytes)
        units = range(self.org.rank_units) if rank_units is None else rank_units
        op = "WR_BB" if source == "external" else "MV_BB"
        for tx_index in range(transactions):
            for rank_unit in units:
                channel, rank = _rank_coords(rank_unit, self.org)
                self.writer.emit(op, self._scratch_addr(channel, rank, tx_index))

    def _emit_mv_rb(self, rank_units: list[int], row_offset: int) -> None:
        for rank_unit in rank_units:
            channel, rank = _rank_coords(rank_unit, self.org)
            for lane in range(self.org.banks_per_rank):
                bg, bank = _bank_coords(lane, self.org)
                self.writer.emit(
                    "MV_RB",
                    self._scratch_addr(channel, rank, row_offset, bg, bank),
                )

    def _emit_output_read(self, n_serial: int, rank_units: list[int]) -> None:
        transactions = max(
            1,
            _ceil_div(n_serial * ACTIVATION_BYTES, self.org.transaction_bytes),
        )
        for rank_unit in rank_units:
            channel, rank = _rank_coords(rank_unit, self.org)
            for lane in range(self.org.banks_per_rank):
                bg, bank = _bank_coords(lane, self.org)
                for tx_index in range(transactions):
                    self.writer.emit(
                        "RD_RB",
                        self._scratch_addr(channel, rank, tx_index, bg, bank),
                    )

    def _matrix_tile_address(
        self,
        mapping: dict[str, Any],
        segment: dict[str, int],
        n_step: int,
    ) -> tuple[int, int]:
        """Return the row and starting column for one issued MAC mini-tile."""
        linear_tile = segment["logical_tile"] * mapping["n_serial"] + n_step
        return (
            mapping["row_base_per_bank"] + linear_tile // self.plan.tiles_per_row,
            (linear_tile % self.plan.tiles_per_row) * self.plan.tile_columns,
        )

    def _static_gemm(
        self,
        layer: int,
        name: str,
        *,
        input_source: str = "external",
        read_output: bool = True,
        output_serial_offset: int = 0,
    ) -> None:
        mapping = self.plan.weights[layer, name]
        rank_units = list(range(self.org.rank_units))
        self.writer.comment(
            f"layer={layer} op={name} W={tuple(mapping['shape'])} W4A16"
        )
        n_serial = mapping["n_serial"]
        for segment in mapping["segments"]:
            self._emit_input_transfer(input_source, segment["elements"])
            for n_step in range(n_serial):
                row, column_offset = self._matrix_tile_address(
                    mapping, segment, n_step
                )
                for col_index in range(segment["columns"]):
                    column = column_offset + col_index
                    for rank_unit in rank_units:
                        channel, rank = _rank_coords(rank_unit, self.org)
                        self.writer.emit(
                            "MAC_AB",
                            self.addr(channel, rank, 0, 0, row, column),
                        )
                self._emit_mv_rb(rank_units, output_serial_offset + n_step)
        if read_output:
            self._emit_output_read(n_serial, rank_units)
        self._barrier()

    def _attention_head(self, layer: int, query_head: int) -> None:
        kv_head = query_head // (self.plan.heads // self.plan.kv_heads)
        key = self.plan.kv[layer, kv_head, "key"]
        value = self.plan.kv[layer, kv_head, "value"]
        rank_units = list(range(self.org.rank_units))
        context = self.plan.context_length

        self.writer.comment(
            f"layer={layer} attention_head={query_head} kv_head={kv_head} QK"
        )
        for rank_unit in rank_units:
            channel, rank = _rank_coords(rank_unit, self.org)
            self.writer.emit(
                "SET_HEAD",
                self.addr(channel, rank, 0, 0, key["row_base_per_bank"], 0),
            )

        for segment in key["segments"]:
            self._emit_input_transfer("external", segment["elements"], rank_units)
            for n_step in range(key["n_serial"]):
                row, column_offset = self._matrix_tile_address(
                    key, segment, n_step
                )
                for col_index in range(segment["columns"]):
                    for rank_unit in rank_units:
                        channel, rank = _rank_coords(rank_unit, self.org)
                        self.writer.emit(
                            "MAC_AB",
                            self.addr(
                                channel,
                                rank,
                                0,
                                0,
                                row,
                                column_offset + col_index,
                            ),
                        )
                self._emit_mv_rb(rank_units, n_step)

        for rank_unit in rank_units:
            channel, rank = _rank_coords(rank_unit, self.org)
            self.writer.emit(
                "SFM",
                self.addr(channel, rank, 0, 0, self.scratch_base, 0),
            )

        self.writer.comment(
            f"layer={layer} attention_head={query_head} kv_head={kv_head} PV"
        )
        for segment in value["segments"]:
            if segment["element_offset"] >= context:
                break
            active_elements = min(segment["elements"], context - segment["element_offset"])
            active_columns = _ceil_div(
                active_elements,
                int(self.org.transaction_bytes / KV_BYTES),
            )
            self._emit_input_transfer("rank_buffer", active_elements, rank_units)
            for n_step in range(value["n_serial"]):
                row, column_offset = self._matrix_tile_address(
                    value, segment, n_step
                )
                for col_index in range(active_columns):
                    for rank_unit in rank_units:
                        channel, rank = _rank_coords(rank_unit, self.org)
                        self.writer.emit(
                            "MAC_AB",
                            self.addr(
                                channel,
                                rank,
                                0,
                                0,
                                row,
                                column_offset + col_index,
                            ),
                        )
                self._emit_mv_rb(rank_units, n_step)
        self._emit_output_read(value["n_serial"], rank_units)
        self._barrier()

    def _external_boundary(self, label: str) -> None:
        """Model a hidden-vector trip around a zero-time host operation."""
        self.writer.comment(f"external={label} begin")
        elems_per_bank = _ceil_div(self.plan.hidden, self.org.total_banks)
        bank_transactions = max(
            1,
            _ceil_div(elems_per_bank * ACTIVATION_BYTES, self.org.transaction_bytes),
        )
        for rank_unit in range(self.org.rank_units):
            channel, rank = _rank_coords(rank_unit, self.org)
            for lane in range(self.org.banks_per_rank):
                bg, bank = _bank_coords(lane, self.org)
                for tx_index in range(bank_transactions):
                    address = self._scratch_addr(channel, rank, tx_index, bg, bank)
                    self.writer.emit("RD_RB", address)
                    self.writer.emit("RD_BB", address)
        self._barrier()

        rank_elements = _ceil_div(self.plan.hidden, self.org.rank_units)
        rank_transactions = _ceil_div(
            rank_elements * ACTIVATION_BYTES,
            self.org.transaction_bytes,
        )
        for tx_index in range(rank_transactions):
            for rank_unit in range(self.org.rank_units):
                channel, rank = _rank_coords(rank_unit, self.org)
                self.writer.emit("WR_RB", self._scratch_addr(channel, rank, tx_index))
        for rank_unit in range(self.org.rank_units):
            channel, rank = _rank_coords(rank_unit, self.org)
            for lane in range(self.org.banks_per_rank):
                bg, bank = _bank_coords(lane, self.org)
                for tx_index in range(bank_transactions):
                    self.writer.emit(
                        "WR_BB",
                        self._scratch_addr(channel, rank, tx_index, bg, bank),
                    )
        self._barrier()
        self.writer.comment(f"external={label} end")

    def generate(self) -> None:
        self._external_boundary("input_rmsnorm")
        for layer in range(self.plan.num_layers):
            self.writer.comment(f"layer={layer} begin")
            self._static_gemm(layer, "q_proj")
            self._static_gemm(layer, "k_proj")
            self._static_gemm(layer, "v_proj")
            self.writer.comment(
                f"layer={layer} external=rope zero_time kv_cache_writeback=deferred"
            )
            for query_head in range(self.plan.heads):
                self._attention_head(layer, query_head)
            self._static_gemm(layer, "o_proj")
            self._external_boundary(f"layer_{layer}_attention_residual_ffn_rmsnorm")

            if self.plan.moe is None:
                self._ffn(layer, "")
            else:
                self._static_gemm(layer, "router")
                active = range(self.plan.moe["active_experts"])
                self.writer.comment(
                    f"layer={layer} external=topk_route zero_time "
                    f"active_experts={list(active)} total_experts={self.plan.moe['num_experts']}"
                )
                for expert in active:
                    self._ffn(layer, f"expert_{expert}_")
            self._external_boundary(f"layer_{layer}_ffn_residual_next_rmsnorm")
            self.writer.comment(f"layer={layer} end")

    def _ffn(self, layer: int, prefix: str) -> None:
        """Emit the gated FFN for a dense layer or one selected MoE expert."""
        gate = f"{prefix}gate_proj"
        up = f"{prefix}up_proj"
        down = f"{prefix}down_proj"
        self._static_gemm(layer, gate, read_output=False)
        self._static_gemm(
            layer,
            up,
            read_output=False,
            output_serial_offset=self.plan.weights[layer, gate]["n_serial"],
        )
        self.writer.comment(f"layer={layer} op={prefix}silu_gate_multiply")
        for rank_unit in range(self.org.rank_units):
            channel, rank = _rank_coords(rank_unit, self.org)
            self.writer.emit("ACT_FUNC", self._scratch_addr(channel, rank))
        self._barrier()
        self._static_gemm(layer, down, input_source="rank_buffer")


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
    """Generate one decode trace and its mapping/capacity manifest.

    ``num_layers`` controls trace execution. ``mapped_num_layers`` can be
    larger so the manifest and capacity estimate cover the full model while a
    shorter prefix of layers is simulated. ``mapping_org`` likewise permits a
    capacity-only organization that differs from the trace/simulation device.
    """
    if prefix_length < 0:
        raise ValueError("prefix_length must be non-negative")
    org = Org() if org is None else org
    tile_columns_for_variant(variant, org)
    config = _load_model_config(model_config_path)
    configured_layers = int(config["num_hidden_layers"])
    if single_layer:
        if num_layers not in (None, 1):
            raise ValueError("single_layer cannot be combined with num_layers other than 1")
        num_layers = 1
    if num_layers is None:
        num_layers = configured_layers
    if not 1 <= num_layers <= configured_layers:
        raise ValueError(f"num_layers must be in [1, {configured_layers}]")
    if mapped_num_layers is None:
        mapped_num_layers = num_layers
    if not num_layers <= mapped_num_layers <= configured_layers:
        raise ValueError(
            f"mapped_num_layers must be in [{num_layers}, {configured_layers}]"
        )
    context_length = prefix_length + 1
    if context_length > int(config["max_position_embeddings"]):
        raise ValueError("prefix_length + 1 exceeds max_position_embeddings")
    if kv_capacity is None:
        kv_capacity = context_length
    if not context_length <= kv_capacity <= int(config["max_position_embeddings"]):
        raise ValueError(
            "kv_capacity must be at least prefix_length + 1 and no larger than "
            "max_position_embeddings"
        )

    trace_planner = MappingPlanner(
        config,
        prefix_length,
        kv_capacity,
        variant,
        num_layers,
        org,
    )
    trace_manifest = trace_planner.build()
    mapping_org = org if mapping_org is None else mapping_org
    if mapped_num_layers == num_layers and mapping_org == org:
        manifest = trace_manifest
    else:
        mapping_planner = MappingPlanner(
            config,
            prefix_length,
            kv_capacity,
            variant,
            mapped_num_layers,
            mapping_org,
        )
        manifest = mapping_planner.build()
    manifest["schema_version"] = 5
    manifest["model"]["mapped_layers"] = mapped_num_layers
    manifest["model"]["simulated_layers"] = num_layers
    manifest["simulation_mapping"] = {
        "simulated_layers": num_layers,
        "rows_per_bank": org.row,
        "reserved_rows_per_bank": trace_planner.scratch["row_end_per_bank"],
        "capacity_note": (
            "trace addresses use this compact simulated-layer mapping; "
            "regions and capacity totals describe mapped_layers"
        ),
    }
    with open(model_config_path, "rb") as config_file:
        config_sha256 = hashlib.sha256(config_file.read()).hexdigest()
    manifest["model"]["config_path"] = str(Path(model_config_path))
    manifest["model"]["config_sha256"] = config_sha256
    header = [
        f"{org.standard_name} end-to-end transformer decode trace",
        f"model_config={model_config_path}",
        (
            f"prefix_length={prefix_length} context_length={context_length} "
            f"simulated_layers={num_layers} mapped_layers={mapped_num_layers} "
            f"variant={variant} quantization=W4A16KV16"
        ),
        f"moe={trace_planner.moe}",
        f"mapping={mapping_path}",
        "embedding and lm_head are intentionally excluded",
    ]
    with TraceWriter(output_path, header) as writer:
        TransformerTraceGenerator(trace_planner, writer).generate()
    manifest["trace"] = {
        "path": output_path,
        "entry_count": writer.entry_count,
        "command_counts": dict(sorted(writer.counts.items())),
    }
    os.makedirs(os.path.dirname(mapping_path) or ".", exist_ok=True)
    with open(mapping_path, "w", encoding="utf-8") as mapping_file:
        json.dump(manifest, mapping_file, indent=2)
        mapping_file.write("\n")
    print(f"Generated {writer.entry_count} trace entries -> {output_path}")
    print(f"Wrote data mapping -> {mapping_path}")
    return manifest


def _default_output(
    model_config_path: str, prefix_length: int, variant: str, single_layer: bool = False
) -> str:
    suffix = variant.replace("-", "_")
    if single_layer:
        suffix += "_single_layer"
    return f"workload/lpddr5pim/{_model_name(model_config_path)}_decode_p{prefix_length}_{suffix}.trace"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an end-to-end LPDDR5-PIM transformer decode trace"
    )
    parser.add_argument("--prefix-length", type=int, default=512)
    parser.add_argument("--model-config", default="workload/modelconfig/llama3_8B.json")
    parser.add_argument("--variant", choices=SUPPORTED_TILINGS, default="baseline")
    parser.add_argument(
        "--kv-capacity",
        type=int,
        default=None,
        help="Allocated tokens per KV cache (default: prefix length + 1)",
    )
    layer_group = parser.add_mutually_exclusive_group()
    layer_group.add_argument(
        "--num-layers",
        type=int,
        default=None,
        help="Debug subset; default uses every layer in the model config",
    )
    layer_group.add_argument(
        "--single-layer",
        action="store_true",
        help="Generate only the first transformer layer for a quick test",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument("--mapping", default=None)
    args = parser.parse_args()

    output = args.output or _default_output(
        args.model_config,
        args.prefix_length,
        args.variant,
        args.single_layer,
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
