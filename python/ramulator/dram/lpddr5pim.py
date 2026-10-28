"""LPDDR5-PIM DRAM standard for Ramulator 2.1.

Extends LPDDR5 with the IANUS PIM command set:
  - ACTAB1/ACTAB2: all-bank split activate
  - MACAB: all-bank MAC (one token)
  - MACSB: same-bank MAC
  - MACPB: per-bank MAC
  - WR_BB: write to bank buffer
  - RD_BB: read from bank buffer
  - WR_RB: write to rank buffer
  - RD_RB: read from rank buffer
  - MV_RB: move (bank buffer -> rank buffer)
  - MV_BB: move (rank buffer -> bank buffer)
  - SFM: softmax
  - ACT_FUNC: activation function
  - SETM / SETH: set model / set head
  - BARRIER: synchronization barrier
  - RFMab / RFMpb: refresh management (inherited from LPDDR5)
"""

import math

from ramulator.dram.spec import DRAMStandard, TimingConstraint


class LPDDR5PIM(DRAMStandard):
    name = "LPDDR5PIM"
    internal_prefetch_size = 16
    read_latency = "nCL + nBL_min"

    _WCK_CK_RATIO = 4

    levels = {
        "Channel":   "N_A",
        "Rank":      "N_A",
        "BankGroup": "N_A",
        "Bank":      "Closed",
        "Row":       "Closed",
        "Column":    "N_A",
    }

    commands = [
        "ACT1", "ACT2", "PREpb", "PREab", "CAS_RD", "CAS_WR",
        "RD", "WR", "RDA", "WRA",
        "REFab", "REFpb", "RFMab", "RFMpb",
        "ACTAB1", "ACTAB2",
        "MACAB",
        "MACSB", "MACPB",
        "WR_BB", "MV_RB", "MV_BB",
        "RD_BB", "WR_RB", "RD_RB",
        "SFM", "ACT_FUNC",
        "SETM", "SETH", "BARRIER",
    ]

    command_cycles = {}

    states = ["Opened", "Closed", "Activating", "N_A"]

    timing_params = [
        "rate", "nBL_min", "nBL_max",
        "nCL", "nRCD", "nRP", "nRPab", "nRAS", "nRC",
        "nWR", "nRTP", "nCWL", "nPPD",
        "nCCDS", "nCCDL", "nCCDS_WR", "nCCDL_WR",
        "nRRDS", "nRRDL",
        "nWTRS", "nWTRL",
        "nFAW", "nRFC", "nRFCpb", "nREFI", "nREFIpb",
        "nWCKPST", "nCAS", "nAAD", "nCS", "tCK_ps",
        "nPBR2PBR", "nPBR2ACT",
        "nCCDAB",
        "nCCDSB",
        "nCCDPB",
        "nWR_BB",
        "nRD_BB",
        "nWR_RB",
        "nRD_RB",
        "nMV_RB",
        "nMV_BB",
        "nSFM",
        "nACT_FUNC",
        "nWR_BB2MAC",
        "nWR_RB2MV_BB",
        "nMV_RB2SFM",
    ]

    supported_requests = {"Read": "RD", "Write": "WR"}

    timing_constraints = [
        TimingConstraint(level="Channel", preceding=["RD", "RDA"], following=["RD", "RDA"], latency="nBL_min"),
        TimingConstraint(level="Channel", preceding=["WR", "WRA"], following=["WR", "WRA"], latency="nBL_min"),
        TimingConstraint(level="Channel",
                         preceding=["MACAB", "MACSB", "MACPB"],
                         following=["MACAB", "MACSB", "MACPB"],
                         latency="nBL_min"),
        TimingConstraint(level="Channel",
                         preceding=["WR_BB", "RD_BB", "WR_RB", "RD_RB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC"],
                         following=["WR_BB", "RD_BB", "WR_RB", "RD_RB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC"],
                         latency="nBL_min"),
        TimingConstraint(level="Channel",
                         preceding=["WR_BB"],
                         following=["MACAB", "MACSB", "MACPB"],
                         latency="nWR_BB2MAC"),
        TimingConstraint(level="Channel",
                         preceding=["WR_RB"],
                         following=["MV_BB", "SFM", "ACT_FUNC"],
                         latency="nWR_RB2MV_BB"),
        TimingConstraint(level="Channel",
                         preceding=["MV_RB"],
                         following=["SFM", "ACT_FUNC"],
                         latency="nMV_RB2SFM"),
        TimingConstraint(level="Channel",
                         preceding=["ACTAB1", "ACTAB2"], following=["ACTAB1", "ACTAB2"], latency="2"),
        TimingConstraint(level="Channel", preceding=["ACTAB1"], following=["ACTAB2"], latency="1"),
        TimingConstraint(level="Channel", preceding=["ACTAB2"],
                         following=["MACAB"], latency="nRCD"),

        TimingConstraint(level="Bank", preceding=["CAS_RD"], following=["RD", "RDA"], latency="nCAS"),
        TimingConstraint(level="Bank", preceding=["CAS_WR"], following=["WR", "WRA"], latency="nCAS"),

        TimingConstraint(level="Rank", preceding=["RD", "RDA"], following=["RD", "RDA"], latency="nCCDS"),
        TimingConstraint(level="Rank", preceding=["WR", "WRA"], following=["WR", "WRA"], latency="nCCDS_WR"),
        TimingConstraint(level="Rank", preceding=["RD", "RDA"], following=["WR", "WRA"], latency="nCL + nBL_min + 2 - nCWL"),
        TimingConstraint(level="Rank", preceding=["WR", "WRA"], following=["RD", "RDA"], latency="nCWL + nBL_min + nWTRS"),
        TimingConstraint(level="Rank", preceding=["RD", "RDA"], following=["RD", "RDA", "WR", "WRA"],
                         latency="nBL_min + nCS", window=1, sibling=True),
        TimingConstraint(level="Rank", preceding=["WR", "WRA"], following=["RD", "RDA"],
                         latency="nCL + nBL_min + nCS - nCWL", window=1, sibling=True),
        TimingConstraint(level="Rank", preceding=["RD"], following=["PREab"], latency="nRTP"),
        TimingConstraint(level="Rank", preceding=["WR"], following=["PREab"], latency="nCWL + nBL_min + 1 + nWR"),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["ACT2", "REFpb"], latency="nRRDS"),
        TimingConstraint(level="Rank", preceding=["ACT1", "REFpb"], following=["ACT1", "REFpb"],
                         latency="nFAW", window=4, shared_window=True),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["PREab"], latency="nRAS"),
        TimingConstraint(level="Rank", preceding=["PREab"], following=["ACT2"], latency="nRPab"),
        TimingConstraint(level="Rank", preceding=["PREpb", "PREab"], following=["PREpb", "PREab"], latency="nPPD"),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["REFab"], latency="nRAS + nRPab"),
        TimingConstraint(level="Rank", preceding=["PREpb"], following=["REFab"], latency="nRP"),
        TimingConstraint(level="Rank", preceding=["PREab"], following=["REFab", "REFpb"], latency="nRPab"),
        TimingConstraint(level="Rank", preceding=["RDA"], following=["REFab"], latency="nRP + nRTP"),
        TimingConstraint(level="Rank", preceding=["WRA"], following=["REFab"], latency="nCWL + nBL_min + 1 + nWR + nRP"),
        TimingConstraint(level="Rank", preceding=["REFab"], following=["ACT2"], latency="nRFC"),
        TimingConstraint(level="Rank", preceding=["REFab"], following=["PREab", "REFpb", "REFab"], latency="nRFC"),
        TimingConstraint(level="Rank", preceding=["REFpb"], following=["REFpb"], latency="nPBR2PBR"),
        TimingConstraint(level="Rank", preceding=["REFpb"], following=["REFab"], latency="nRFCpb"),
        TimingConstraint(level="Rank", preceding=["REFpb"], following=["ACT2"], latency="nPBR2ACT"),

        TimingConstraint(level="Rank", preceding=["ACTAB1"], following=["PREab"], latency="nRAS"),
        TimingConstraint(level="Rank", preceding=["PREab"], following=["ACTAB1"], latency="nRPab"),
        TimingConstraint(level="Rank", preceding=["ACTAB1"], following=["REFab"], latency="nRC"),
        TimingConstraint(level="Rank", preceding=["REFab"], following=["ACTAB1"], latency="nRFC"),
        TimingConstraint(level="Rank",
                         preceding=["MACAB", "MACSB", "MACPB"],
                         following=["PREab"], latency="nRTP"),
        TimingConstraint(level="Rank", preceding=["ACTAB1"], following=["ACTAB1"], latency="nRC"),
        TimingConstraint(level="Rank", preceding=["ACTAB1"], following=["ACTAB2"], latency="1"),
        TimingConstraint(level="Rank", preceding=["ACTAB2"],
                         following=["MACAB"], latency="nRCD"),
        TimingConstraint(level="Rank", preceding=["MACAB"],
                         following=["MACAB"], latency="nCCDAB"),
        TimingConstraint(level="Rank", preceding=["MACSB"], following=["MACSB"], latency="nCCDSB"),
        TimingConstraint(level="Rank", preceding=["MACPB"], following=["MACPB"], latency="nCCDPB"),

        TimingConstraint(level="BankGroup", preceding=["RD", "RDA"], following=["RD", "RDA"], latency="nCCDL"),
        TimingConstraint(level="BankGroup", preceding=["WR", "WRA"], following=["WR", "WRA"], latency="nCCDL_WR"),
        TimingConstraint(level="BankGroup", preceding=["RD", "RDA"], following=["WR", "WRA"],
                         latency="nCL + nBL_max + 2 - nCWL"),
        TimingConstraint(level="BankGroup", preceding=["WR", "WRA"], following=["RD", "RDA"],
                         latency="nCWL + nBL_max + nWTRL"),
        TimingConstraint(level="BankGroup", preceding=["ACT2"], following=["ACT2"], latency="nRRDL"),

        TimingConstraint(level="Bank", preceding=["ACT2"], following=["ACT2"], latency="nRC"),
        TimingConstraint(level="Bank", preceding=["ACT2"],
                         following=["RD", "RDA", "WR", "WRA",
                                    "MACAB",
                                    "MACSB", "MACPB"],
                         latency="nRCD"),
        TimingConstraint(level="Bank", preceding=["ACTAB2"],
                         following=["MACAB"], latency="nRCD"),
        TimingConstraint(level="Bank", preceding=["ACT2"], following=["PREpb"], latency="nRAS"),
        TimingConstraint(level="Bank", preceding=["PREpb"], following=["ACT2"], latency="nRP"),
        TimingConstraint(level="Bank", preceding=["RD"], following=["PREpb"], latency="nRTP"),
        TimingConstraint(level="Bank", preceding=["WR"], following=["PREpb"],
                         latency="nCWL + nBL_min + 1 + nWR"),
        TimingConstraint(level="Bank", preceding=["RDA"], following=["ACT2"], latency="nRTP + nRP"),
        TimingConstraint(level="Bank", preceding=["WRA"], following=["ACT2"],
                         latency="nCWL + nBL_min + 1 + nWR + nRP"),
        TimingConstraint(level="Bank",
                         preceding=["MACAB", "MACSB", "MACPB"],
                         following=["PREpb"], latency="nRTP"),
        TimingConstraint(level="Bank", preceding=["REFpb"], following=["ACT2"], latency="nRFCpb"),
        TimingConstraint(level="Bank", preceding=["ACT2"], following=["REFpb"], latency="nRC"),
        TimingConstraint(level="Bank", preceding=["PREpb"], following=["REFpb"], latency="nRP"),
        TimingConstraint(level="Bank", preceding=["RDA"], following=["REFpb"], latency="nRTP + nRP"),
        TimingConstraint(level="Bank", preceding=["WRA"], following=["REFpb"],
                         latency="nCWL + nBL_min + 1 + nWR + nRP"),
    ]

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        bank_mode = {
            (4, 4): "BG",
            (1, 8): "8B",
            (1, 16): "16B",
        }.get((org_dict["bankgroup"], org_dict["bank"]))
        timing_dict["nRRDS"]    = cls._resolve_nRRDS(timing_dict["tCK_ps"], bank_mode)
        timing_dict["nRRDL"]    = cls._resolve_nRRDL(timing_dict["tCK_ps"], bank_mode)
        timing_dict["nFAW"]     = cls._resolve_nFAW(timing_dict["tCK_ps"], bank_mode)
        timing_dict["nRFC"]     = cls._resolve_nRFC(org_dict["density"], timing_dict["tCK_ps"])
        timing_dict["nRFCpb"]   = cls._resolve_nRFCpb(org_dict["density"], timing_dict["tCK_ps"])
        timing_dict["nREFI"]    = cls._resolve_nREFI(timing_dict["tCK_ps"])
        timing_dict["nREFIpb"]  = cls._resolve_nREFIpb(timing_dict["tCK_ps"])
        timing_dict["nPBR2PBR"] = cls._resolve_nPBR2PBR(org_dict["density"], timing_dict["tCK_ps"])
        timing_dict["nPBR2ACT"] = cls._resolve_nPBR2ACT(timing_dict["tCK_ps"], bank_mode)

        nCCDL   = timing_dict["nCCDL"]
        nCCDS   = timing_dict["nCCDS"]
        nBL_min = timing_dict["nBL_min"]
        timing_dict.setdefault("nCCDAB",    nCCDL)
        timing_dict.setdefault("nCCDSB",    nCCDL)
        timing_dict.setdefault("nCCDPB",    nCCDS)
        timing_dict.setdefault("nWR_BB",       nBL_min)
        timing_dict.setdefault("nRD_BB",      nBL_min)
        timing_dict.setdefault("nWR_RB",      nBL_min)
        timing_dict.setdefault("nRD_RB",      nBL_min)
        timing_dict.setdefault("nMV_RB",       nBL_min)
        timing_dict.setdefault("nMV_BB",       nBL_min)
        timing_dict.setdefault("nSFM",        nBL_min)
        timing_dict.setdefault("nACT_FUNC",   nBL_min)
        nCWL = timing_dict["nCWL"]
        timing_dict.setdefault("nWR_BB2MAC",    nCWL + nBL_min)
        timing_dict.setdefault("nWR_RB2MV_BB",  nCWL + nBL_min)
        timing_dict.setdefault("nMV_RB2SFM",    timing_dict["nMV_RB"])

    @staticmethod
    def _resolve_nRRDS(tCK_ps, bank_mode):
        tRRD_ps = {"BG": 5_000, "8B": 10_000, "16B": 5_000}.get(bank_mode)
        return max(2, math.ceil(tRRD_ps / tCK_ps)) if tRRD_ps else -1

    @staticmethod
    def _resolve_nRRDL(tCK_ps, bank_mode):
        tRRDL_ps = {"BG": 5_000, "8B": 10_000, "16B": 5_000}.get(bank_mode)
        return max(2, math.ceil(tRRDL_ps / tCK_ps)) if tRRDL_ps else -1

    @staticmethod
    def _resolve_nFAW(tCK_ps, bank_mode):
        tFAW_ps = {"BG": 20_000, "8B": 40_000, "16B": 20_000}.get(bank_mode)
        return math.ceil(tFAW_ps / tCK_ps) if tFAW_ps else -1

    @staticmethod
    def _resolve_nRFC(density, tCK_ps):
        tRFC_ns = {2048: 130, 3072: 180, 4096: 180, 6144: 210, 8192: 210,
                   12288: 280, 16384: 280, 24576: 380, 32768: 380}.get(density)
        return math.ceil(tRFC_ns * 1000 / tCK_ps) if tRFC_ns else -1

    @staticmethod
    def _resolve_nRFCpb(density, tCK_ps):
        tRFC_ns = {2048: 60, 3072: 90, 4096: 90, 6144: 120, 8192: 120,
                   12288: 140, 16384: 140, 24576: 190, 32768: 190}.get(density)
        return math.ceil(tRFC_ns * 1000 / tCK_ps) if tRFC_ns else -1

    @staticmethod
    def _resolve_nREFI(tCK_ps):
        return 3_906_000 // tCK_ps

    @staticmethod
    def _resolve_nREFIpb(tCK_ps):
        return 488_000 // tCK_ps

    @staticmethod
    def _resolve_nPBR2PBR(density, tCK_ps):
        t_ns = {2048: 60, 3072: 90, 4096: 90, 6144: 90, 8192: 90,
                12288: 90, 16384: 90, 24576: 90, 32768: 90}.get(density)
        return math.ceil(t_ns * 1000 / tCK_ps) if t_ns else -1

    @staticmethod
    def _resolve_nPBR2ACT(tCK_ps, bank_mode):
        tPBR2ACT_ps = {"BG": 7_500, "8B": 10_000, "16B": 7_500}.get(bank_mode)
        return math.ceil(tPBR2ACT_ps / tCK_ps) if tPBR2ACT_ps else -1


LPDDR5PIM.org_presets = {
    "LPDDR5PIM_8Gb_x16":  {
        "density": 8192, "dq": 16, "channel_width": 16,
        "rank": 1, "bankgroup": 4, "bank": 4, "row": 1 << 15, "column": 1 << 10,
    },
    "LPDDR5PIM_16Gb_x16": {
        "density": 16384, "dq": 16, "channel_width": 16,
        "rank": 1, "bankgroup": 4, "bank": 4, "row": 1 << 16, "column": 1 << 10,
    },
    "LPDDR5PIM_32Gb_x16": {
        "density": 32768, "dq": 16, "channel_width": 16,
        "rank": 1, "bankgroup": 4, "bank": 4, "row": 1 << 17, "column": 1 << 10,
    },
}

LPDDR5PIM.timing_presets = {
    "LPDDR5PIM_5500": {
        "rate": 5500, "nBL_min": 2, "nBL_max": 4, "nCL": 15,
        "nRCD": 13, "nRP": 13, "nRPab": 15,
        "nRAS": 29, "nRC": 42, "nWR": 24, "nRTP": 6, "nCWL": 8, "nPPD": 2,
        "nCCDS": 2, "nCCDL": 4, "nCCDS_WR": 2, "nCCDL_WR": 4,
        "nWTRS": 5, "nWTRL": 9, "nWCKPST": 1, "nCAS": 0,
        "nAAD": 8, "nCS": 2,
        "tCK_ps": 1453,
    },
    "LPDDR5PIM_6400": {
        "rate": 6400, "nBL_min": 2, "nBL_max": 4, "nCL": 17,
        "nRCD": 15, "nRP": 15, "nRPab": 17,
        "nRAS": 34, "nRC": 49, "nWR": 28, "nRTP": 6, "nCWL": 9, "nPPD": 2,
        "nCCDS": 2, "nCCDL": 4, "nCCDS_WR": 2, "nCCDL_WR": 4,
        "nWTRS": 5, "nWTRL": 10, "nWCKPST": 1, "nCAS": 0,
        "nAAD": 8, "nCS": 2,
        "tCK_ps": 1250,
    },
    "LPDDR5PIM_8533": {
        "rate": 8533, "nBL_min": 2, "nBL_max": 4, "nCL": 23,
        "nRCD": 20, "nRP": 20, "nRPab": 23,
        "nRAS": 45, "nRC": 65, "nWR": 37, "nRTP": 8, "nCWL": 12, "nPPD": 2,
        "nCCDS": 2, "nCCDL": 4, "nCCDS_WR": 2, "nCCDL_WR": 4,
        "nWTRS": 7, "nWTRL": 13, "nWCKPST": 1, "nCAS": 0,
        "nAAD": 8, "nCS": 2,
        "tCK_ps": 938,
    },
}
