"""LPDDR6-PIM DRAM standard for Ramulator 2.1.

Extends LPDDR6 with the IANUS PIM command set:
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

LPDDR6 differences from LPDDR5 that affect the PIM adaptation:
  - CA bus: every-other-CK command protocol → command_cycles entries
  - Column access: CAS (single gating command) instead of CAS_RD/CAS_WR
  - Data commands: RD_S/WR_S (short, BL24) instead of RD/WR
  - Latency params: nRL/nWL instead of nCL/nCWL
  - BL: BL24 (nBL_min = 6 at high-rate) instead of BL16 (nBL_min = 2)
  - ACU-based row timing (nACU, nRP=nACU+ceil(18ns/tCK), nRPab=nACU+ceil(21ns/tCK))
  - No RFMab/RFMpb (LPDDR6 does not define RFM in JESD209-6)
"""

import math

from ramulator.dram.spec import DRAMStandard, TimingConstraint


class LPDDR6PIM(DRAMStandard):
    name = "LPDDR6PIM"
    internal_prefetch_size = 16
    data_payload_bytes = 32
    read_latency = "nRL + nBL_min"

    levels = {
        "Channel":   "N_A",
        "Rank":      "N_A",
        "BankGroup": "N_A",
        "Bank":      "Closed",
        "Row":       "Closed",
        "Column":    "N_A",
    }

    commands = [
        "ACT1", "ACT2", "PREpb", "PREab", "CAS",
        "RD_S", "WR_S", "RDA_S", "WRA_S",
        "REFab",
        "ACTAB1", "ACTAB2",
        "MACAB",
        "MACSB", "MACPB",
        "WR_BB", "MV_RB", "MV_BB",
        "RD_BB", "WR_RB", "RD_RB",
        "SFM", "ACT_FUNC",
        "SETM", "SETH", "BARRIER",
    ]

    command_cycles = {
        "ACT1": 2, "ACT2": 2, "PREpb": 2, "PREab": 2, "CAS": 2,
        "RD_S": 2, "WR_S": 2, "RDA_S": 2, "WRA_S": 2, "REFab": 2,
        "ACTAB1": 2, "ACTAB2": 2, "MACAB": 2,
        "MACSB": 2, "MACPB": 2,
        "WR_BB": 2, "MV_RB": 2, "MV_BB": 2,
        "RD_BB": 2, "WR_RB": 2, "RD_RB": 2,
        "SFM": 2, "ACT_FUNC": 2,
        "SETM": 2, "SETH": 2, "BARRIER": 2,
    }

    states = ["Opened", "Closed", "Activating", "N_A"]

    timing_params = [
        "rate", "nBL_min", "nBL_max",
        "nRL", "nWL",
        "nRCDr", "nRCDw", "nRP", "nRPab", "nRAS", "nRC",
        "nWTP", "nRTP", "nPPD",
        "nCCDS", "nCCDL", "nCCDS_WR", "nCCDL_WR",
        "nRRD",
        "nWTRS", "nWTRL",
        "nRTW_S", "nRTW_L",
        "nFAW", "nRFC", "nREFI",
        "nWCKPST", "nCAS", "nAAD", "nCS", "tCK_ps",
        "nACU",
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

    supported_requests = {"Read": "RD_S", "Write": "WR_S"}

    timing_constraints = [
        TimingConstraint(level="Channel", preceding=["RD_S", "RDA_S"], following=["RD_S", "RDA_S"], latency="nBL_min"),
        TimingConstraint(level="Channel", preceding=["WR_S", "WRA_S"], following=["WR_S", "WRA_S"], latency="nBL_min"),
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
                         following=["MACAB"], latency="nRCDr"),

        TimingConstraint(level="Bank", preceding=["CAS"], following=["RD_S", "RDA_S", "WR_S", "WRA_S"], latency="nCAS"),

        TimingConstraint(level="Rank", preceding=["RD_S", "RDA_S"], following=["RD_S", "RDA_S"], latency="nCCDS"),
        TimingConstraint(level="Rank", preceding=["WR_S", "WRA_S"], following=["WR_S", "WRA_S"], latency="nCCDS_WR"),
        TimingConstraint(level="Rank", preceding=["RD_S", "RDA_S"], following=["WR_S", "WRA_S"], latency="nRTW_S"),
        TimingConstraint(level="Rank", preceding=["WR_S", "WRA_S"], following=["RD_S", "RDA_S"],
                         latency="nWL + nBL_min + nWTRS"),
        TimingConstraint(level="Rank", preceding=["RD_S", "RDA_S"],
                         following=["RD_S", "RDA_S", "WR_S", "WRA_S"],
                         latency="nBL_min + nCS", window=1, sibling=True),
        TimingConstraint(level="Rank", preceding=["WR_S", "WRA_S"], following=["RD_S", "RDA_S"],
                         latency="nRL + nBL_min + nCS - nWL", window=1, sibling=True),
        TimingConstraint(level="Rank", preceding=["RD_S"], following=["PREab"], latency="nRTP"),
        TimingConstraint(level="Rank", preceding=["WR_S"], following=["PREab"], latency="nWL + nBL_max + nWTP"),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["ACT2"], latency="nRRD"),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["ACT2"], latency="nFAW", window=4),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["PREab"], latency="nRAS"),
        TimingConstraint(level="Rank", preceding=["PREab"], following=["ACT2"], latency="nRPab"),
        TimingConstraint(level="Rank", preceding=["PREpb", "PREab"], following=["PREpb", "PREab"], latency="nPPD"),
        TimingConstraint(level="Rank", preceding=["ACT2"], following=["REFab"], latency="nRAS + nRPab"),
        TimingConstraint(level="Rank", preceding=["PREpb"], following=["REFab"], latency="nRP"),
        TimingConstraint(level="Rank", preceding=["PREab"], following=["REFab"], latency="nRPab"),
        TimingConstraint(level="Rank", preceding=["RDA_S"], following=["REFab"], latency="nRP + nRTP"),
        TimingConstraint(level="Rank", preceding=["WRA_S"], following=["REFab"],
                         latency="nWL + nBL_max + nWTP + nRP"),
        TimingConstraint(level="Rank", preceding=["REFab"], following=["ACT2"], latency="nRFC"),
        TimingConstraint(level="Rank", preceding=["REFab"], following=["PREab", "REFab"], latency="nRFC"),

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
                         following=["MACAB"], latency="nRCDr"),
        TimingConstraint(level="Rank", preceding=["MACAB"],
                         following=["MACAB"], latency="nCCDAB"),
        TimingConstraint(level="Rank", preceding=["MACSB"], following=["MACSB"], latency="nCCDSB"),
        TimingConstraint(level="Rank", preceding=["MACPB"], following=["MACPB"], latency="nCCDPB"),

        TimingConstraint(level="BankGroup", preceding=["RD_S", "RDA_S"], following=["RD_S", "RDA_S"], latency="nCCDL"),
        TimingConstraint(level="BankGroup", preceding=["WR_S", "WRA_S"], following=["WR_S", "WRA_S"], latency="nCCDL_WR"),
        TimingConstraint(level="BankGroup", preceding=["RD_S", "RDA_S"], following=["WR_S", "WRA_S"],
                         latency="nRTW_L"),
        TimingConstraint(level="BankGroup", preceding=["WR_S", "WRA_S"], following=["RD_S", "RDA_S"],
                         latency="nWL + nBL_max + nWTRL"),
        TimingConstraint(level="BankGroup", preceding=["ACT2"], following=["ACT2"], latency="nRRD"),

        TimingConstraint(level="Bank", preceding=["ACT2"], following=["ACT2"], latency="nRC"),
        TimingConstraint(level="Bank", preceding=["ACT2"],
                         following=["RD_S", "RDA_S", "WR_S", "WRA_S",
                                    "MACAB",
                                    "MACSB", "MACPB"],
                         latency="nRCDr"),
        TimingConstraint(level="Bank", preceding=["ACTAB2"],
                         following=["MACAB"], latency="nRCDr"),
        TimingConstraint(level="Bank", preceding=["ACT2"], following=["PREpb"], latency="nRAS"),
        TimingConstraint(level="Bank", preceding=["PREpb"], following=["ACT2"], latency="nRP"),
        TimingConstraint(level="Bank", preceding=["RD_S"], following=["PREpb"], latency="nRTP"),
        TimingConstraint(level="Bank", preceding=["WR_S"], following=["PREpb"],
                         latency="nWL + nBL_max + nWTP"),
        TimingConstraint(level="Bank", preceding=["RDA_S"], following=["ACT2"], latency="nRTP + nRP"),
        TimingConstraint(level="Bank", preceding=["WRA_S"], following=["ACT2"],
                         latency="nWL + nBL_max + nWTP + nRP"),
        TimingConstraint(level="Bank",
                         preceding=["MACAB", "MACSB", "MACPB"],
                         following=["PREpb"], latency="nRTP"),
    ]

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        tCK_ps = timing_dict["tCK_ps"]
        rate = timing_dict["rate"]

        nACU = cls._resolve_nACU(rate)
        timing_dict["nACU"]  = nACU
        timing_dict["nRAS"]  = max(math.ceil(20_000 / tCK_ps), 4)
        timing_dict["nRP"]   = nACU + max(math.ceil(18_000 / tCK_ps), 4)
        timing_dict["nRPab"] = nACU + max(math.ceil(21_000 / tCK_ps), 4)
        timing_dict["nRC"]   = timing_dict["nRAS"] + timing_dict["nRP"]
        timing_dict["nBL_max"] = cls._resolve_nBL_max(rate)
        timing_dict["nRFC"]  = cls._resolve_nRFC(org_dict["die_density"], tCK_ps)
        timing_dict["nREFI"] = 3_906_000 // tCK_ps

        nWCK2DQO = timing_dict.get("nWCK2DQO", 0)
        nRL = timing_dict["nRL"]
        nWL = timing_dict["nWL"]
        nBL_min = timing_dict["nBL_min"]
        nBL_max = timing_dict["nBL_max"]
        if "nRTW_S" not in timing_dict:
            timing_dict["nRTW_S"] = nRL + nBL_min + nWCK2DQO - nWL
        if "nRTW_L" not in timing_dict:
            timing_dict["nRTW_L"] = nRL + nBL_max + nWCK2DQO - nWL

        nCCDL = timing_dict["nCCDL"]
        nCCDS = timing_dict["nCCDS"]
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
        nWL = timing_dict["nWL"]
        timing_dict.setdefault("nWR_BB2MAC",    nWL + nBL_min)
        timing_dict.setdefault("nWR_RB2MV_BB",  nWL + nBL_min)
        timing_dict.setdefault("nMV_RB2SFM",    timing_dict["nMV_RB"])

    @classmethod
    def _resolve_nACU(cls, rate):
        return cls._lookup_speed_grade(rate, {
            (80, 1067): 6,
            (1067, 1600): 9,
            (1600, 2133): 12,
            (2133, 2750): 16,
            (2750, 3200): 18,
            (3200, 3750): 21,
            (3750, 4267): 24,
            (4267, 4800): 27,
            (4800, 5500): 31,
            (5500, 6400): 36,
            (6400, 7500): 42,
            (7500, 8533): 47,
            (8533, 9600): 53,
            (9600, 10667): 59,
        })

    @classmethod
    def _resolve_nBL_max(cls, rate):
        return cls._lookup_speed_grade(rate, {
            (80, 3200): 6,
            (3200, 10667): 12,
        })

    @staticmethod
    def _lookup_speed_grade(rate, table):
        for (lower_rate, upper_rate), value in table.items():
            if lower_rate < rate <= upper_rate:
                return value
        return -1

    @staticmethod
    def _resolve_nRFC(die_density, tCK_ps):
        tRFC_ns = {
            4096: None, 6144: 210, 8192: 210,
            12288: 280, 16384: 280,
            24576: 380, 32768: 380,
            49152: 550, 65536: 550,
        }.get(die_density)
        if tRFC_ns is None:
            return -1
        return math.ceil(tRFC_ns * 1000 / tCK_ps)


LPDDR6PIM.org_presets = {
    "LPDDR6PIM_8Gb_x12": {
        "die_density": 16384,
        "dq": 12,
        "channel_width": 12,
        "odt_enabled": True,
        "rank": 1,
        "bankgroup": 4,
        "bank": 4,
        "row": 1 << 15,
        "column": 1 << 10,
    },
    "LPDDR6PIM_16Gb_x12": {
        "die_density": 32768,
        "dq": 12,
        "channel_width": 12,
        "odt_enabled": True,
        "rank": 1,
        "bankgroup": 4,
        "bank": 4,
        "row": 1 << 16,
        "column": 1 << 10,
    },
    "LPDDR6PIM_32Gb_x12": {
        "die_density": 65536,
        "dq": 12,
        "channel_width": 12,
        "odt_enabled": True,
        "rank": 1,
        "bankgroup": 4,
        "bank": 4,
        "row": 1 << 17,
        "column": 1 << 10,
    },
}

LPDDR6PIM.timing_presets = {

    "LPDDR6PIM_8533": {
        "rate": 8533,
        "nBL_min": 6,
        "nRL": 47, "nWL": 22,
        "nRCDr": 40, "nRCDw": 18,
        "nWTP": 28, "nRTP": 12,
        "nPPD": 4,
        "nCCDS": 6, "nCCDL": 10, "nCCDS_WR": 6, "nCCDL_WR": 10,
        "nRRD": 10, "nWTRS": 15, "nWTRL": 28,
        "nWCK2DQO": 5,
        "nFAW": 32,
        "nWCKPST": 3, "nCAS": 2,
        "nAAD": 8, "nCS": 2,
        "tCK_ps": 469,
    },
    "LPDDR6PIM_10667": {
        "rate": 10667,
        "nBL_min": 6,
        "nRL": 56, "nWL": 26,
        "nRCDr": 48, "nRCDw": 22,
        "nWTP": 32, "nRTP": 14,
        "nPPD": 4,
        "nCCDS": 6, "nCCDL": 10, "nCCDS_WR": 6, "nCCDL_WR": 10,
        "nRRD": 10, "nWTRS": 17, "nWTRL": 32,
        "nWCK2DQO": 5,
        "nFAW": 40,
        "nWCKPST": 3, "nCAS": 2,
        "nAAD": 8, "nCS": 2,
        "tCK_ps": 375,
    },
}
