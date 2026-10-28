# MoSAIC: A Timing-Aware Co-Design of Fine-Grained Tiling and Row-Transition Pipelining for Near-Bank PIM

MoSAIC extends Ramulator 2.1 [1] with LPDDR5-PIM, LPDDR6-PIM, and GDDR7-PIM
workloads, supporting GEMM and Transformer trace generation and cycle-accurate
simulation.
We further develop row-transition pipelining and fine-grained tiling based on it
for better throughput and memory efficiency.

## Build

See [README_Ramulator2.md](README_Ramulator2.md) for the complete Ramulator
documentation. 

Quick build from the repository root:

```bash
mkdir -p build
cd build
cmake ..
make -j
cd ..
```

Then install the Python package:

```bash
pip install -e .
```

## Workloads

Each platform directory under `workload/` provides the same entry points.
Transformer model descriptions are stored in `workload/modelconfig/`.

- **Baseline:** standard PIM DRAM and controller.
- **RTP** overlaps the next row's precharge and activation with current-row
  MAC execution.
- **Tile segments:** places one, two, or four logical tiles in each DRAM row.

Run `python <script> --help` for all options.

## Quick start

```bash
python workload/lpddr5pim/sim_gemm.py --variant rtp
python workload/lpddr6pim/sim_transformer.py \
  --model-config workload/modelconfig/llama3_8B.json \
  --prefix-length 512 --single-layer --pim-variant rtp
```

Use `workload/<platform>/`, where `<platform>` is `lpddr5pim`, `lpddr6pim`, or
`gddr7pim`:

| Script | Purpose |
| --- | --- |
| `gen_trace_gemm.py` | Generate a tiled GEMM/GEMV trace. |
| `sim_gemm.py` | Generate and simulate GEMM on baseline or RTP. |
| `gen_trace_transformer.py` | Generate a Transformer decode trace and mapping manifest. |
| `sim_transformer.py` | Generate or reuse a trace and simulate Transformer decode. |




## Acknowledgments and License

This project is built upon
[Ramulator 2.1](https://github.com/CMU-SAFARI/ramulator2), an open-source DRAM simulator developed by the SAFARI Research Group at ETH Zurich and Carnegie Mellon University.

We gratefully acknowledge the original Ramulator developers for providing the open-source simulation framework.


Haocong Luo, F. Nisa Bostanci, Ataberk Olgun, Maria Makeenkova, Ziad Malik, Ipek Akdeniz, and Onur Mutlu. 2026. Ramulator 2.1: A Composable Memory System Simulator for Modern DRAM Systems.