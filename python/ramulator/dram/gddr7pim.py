"""GDDR7-PIM DRAM standard for Ramulator 2.1.

Extends GDDR7 with the IANUS PIM command set adapted for the GDDR7 hierarchy.

Key structural differences from LPDDR5/6-PIM:
  - No BankGroup level: hierarchy is Channel -> Bank -> Row -> Column
  - Single-step ACTAB (no split ACTAB1+ACTAB2): GDDR7 has no Activating state
  - 16 banks per channel, all firing in parallel under MACAB
  - No MACPB (no BankGroup level to define per-BG MAC)
  - Controller extends HBMControllerBase (dual row/column bus), not LPDDRControllerBase
  - internal_prefetch_size = 32 (BL32); data_payload_bytes = 32 B (8 DQ x 32 beats)
  - Per-bank and all-bank refresh supported (REFpb + REFab)
"""

import math

from ramulator.dram.spec import DRAMStandard, TimingConstraint


class GDDR7PIM(DRAMStandard):
    name = "GDDR7PIM"
    manual_codegen = True
    internal_prefetch_size = 32
    data_payload_bytes = 32
    read_latency = "1 + nRL + nDQERL + nBL"

    levels = {
        "Channel": "N_A",
        "Bank":    "Closed",
        "Row":     "Closed",
        "Column":  "N_A",
    }

    commands = [
        "ACT", "PREpb", "PREab",
        "RD", "WR", "RDA", "WRA",
        "REFab", "REFpb",
        "RFMab", "RFMpb",
        "RCKSTRT", "RCKSTOP",
        "ACTAB",
        "MACAB",
        "MACSB",
        "WR_BB", "MV_RB", "MV_BB",
        "RD_BB", "WR_RB", "RD_RB",
        "SFM", "ACT_FUNC",
        "SETM", "SETH", "BARRIER",
    ]

    command_cycles = {
        "ACT": 2, "RD": 2, "RDA": 2, "WR": 2, "WRA": 2,
        "RCKSTRT": 2, "RCKSTOP": 2,
        "PREpb": 1, "PREab": 1,
        "REFpb": 1, "REFab": 1,
        "RFMpb": 1, "RFMab": 1,
        "ACTAB": 2, "MACAB": 2,
        "MACSB": 2,
        "WR_BB": 2, "MV_RB": 2, "MV_BB": 2,
        "RD_BB": 2, "WR_RB": 2, "RD_RB": 2,
        "SFM": 2, "ACT_FUNC": 2,
        "SETM": 2, "SETH": 2, "BARRIER": 2,
    }

    row_commands    = ["ACT", "PREpb", "PREab", "REFab", "REFpb", "RFMab", "RFMpb", "ACTAB"]
    column_commands = ["RD", "WR", "RDA", "WRA", "RCKSTRT", "RCKSTOP",
                       "MACAB",
                       "MACSB", "WR_BB", "RD_BB", "WR_RB", "RD_RB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC",
                       "SETM", "SETH", "BARRIER"]

    states = ["Opened", "Closed", "N_A"]

    timing_params = [
        "rate", "nBL", "nRL", "nWL", "nDQERL",
        "nRCDRD", "nRCDWR", "nRP", "nRAS", "nRC",
        "nRRD", "nRREFD", "nRPD", "nRTPSB", "nPPD", "nWR",
        "nCCD", "nCCDSB",
        "nWTR", "nWTRSB", "nRTW",
        "nREFI", "nREFIpb", "nRFCab", "nRFCpb", "nRDREFab", "nRFMab", "nRFMpb",
        "nRCKSTRT2RD", "nRD2RCKSTOP", "nRCKSP2ST", "nRCKST2SP",
        "nRCKSTOP_LAT", "nRCKEN", "nRCK_LS", "nRCKPST",
        "tCK_ps",
        "nCCDAB",
        "nCCDSB_PIM",
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
        TimingConstraint("Channel", ["RD", "RDA"], ["RD", "RDA"], "nCCD"),
        TimingConstraint("Channel", ["WR", "WRA"], ["WR", "WRA"], "nCCD"),
        TimingConstraint("Channel", ["RD", "RDA"], ["WR", "WRA"], "nRTW"),
        TimingConstraint("Channel", ["WR", "WRA"], ["RD", "RDA"], "nWL + nBL + nWTR"),
        TimingConstraint("Bank", ["RD", "RDA"], ["RD", "RDA"], "nCCDSB"),
        TimingConstraint("Bank", ["WR", "WRA"], ["WR", "WRA"], "nCCDSB"),
        TimingConstraint("Bank", ["WR", "WRA"], ["RD", "RDA"], "nWL + nBL + nWTRSB"),
        TimingConstraint("Channel", ["ACT"], ["ACT"], "nRRD"),
        TimingConstraint("Channel", ["PREpb", "PREab"], ["PREpb", "PREab"], "nPPD"),
        TimingConstraint("Bank", ["ACT"], ["ACT"], "nRC"),
        TimingConstraint("Bank", ["ACT"], ["RD", "RDA"], "nRCDRD"),
        TimingConstraint("Bank", ["ACT"], ["WR", "WRA"], "nRCDWR"),
        TimingConstraint("Bank", ["ACT"], ["PREpb"], "nRAS"),
        TimingConstraint("Bank", ["PREpb"], ["ACT"], "nRP"),
        TimingConstraint("Bank", ["PREpb"], ["ACT", "REFpb", "RFMpb"], "nRPD", sibling=True),
        TimingConstraint("Bank", ["RD"], ["PREpb"], "nRTPSB"),
        TimingConstraint("Bank", ["WR"], ["PREpb"], "nWL + nBL + nWR"),
        TimingConstraint("Channel", ["RD", "RDA"], ["PREab"], "nRTPSB"),
        TimingConstraint("Channel", ["WR", "WRA"], ["PREab"], "nWL + nBL + nWR"),
        TimingConstraint("Bank", ["RDA"], ["ACT", "REFpb", "RFMpb"], "nRTPSB + nRP"),
        TimingConstraint("Bank", ["WRA"], ["ACT", "REFpb", "RFMpb"], "nWL + nBL + nWR + nRP"),
        TimingConstraint("Channel", ["ACT"], ["REFab", "RFMab"], "nRC"),
        TimingConstraint("Channel", ["RD", "RDA"], ["REFab", "RFMab"], "nRDREFab"),
        TimingConstraint("Channel", ["PREpb", "PREab"], ["REFab", "RFMab"], "nRP"),
        TimingConstraint("Channel", ["RDA"], ["REFab", "RFMab"], "nRTPSB + nRP"),
        TimingConstraint("Channel", ["WRA"], ["REFab", "RFMab"], "nWL + nBL + nWR + nRP"),
        TimingConstraint("Channel", ["REFab"], ["ACT", "PREab", "REFab", "REFpb", "RFMab", "RFMpb"], "nRFCab"),
        TimingConstraint("Channel", ["REFpb"], ["REFpb", "RFMpb", "ACT"], "nRREFD"),
        TimingConstraint("Channel", ["REFpb"], ["REFab", "RFMab"], "nRFCpb"),
        TimingConstraint("Channel", ["ACT"], ["REFpb", "RFMpb"], "nRRD"),
        TimingConstraint("Channel", ["PREab"], ["REFpb", "RFMpb"], "nRP"),
        TimingConstraint("Bank", ["REFpb"], ["ACT", "REFpb", "RFMpb"], "nRFCpb"),
        TimingConstraint("Bank", ["ACT"], ["REFpb", "RFMpb"], "nRC"),
        TimingConstraint("Bank", ["PREpb"], ["REFpb", "RFMpb"], "nRP"),
        TimingConstraint("Channel", ["RFMab"], ["ACT", "PREab", "REFab", "REFpb", "RFMab", "RFMpb"], "nRFMab"),
        TimingConstraint("Channel", ["RFMpb"], ["REFpb", "RFMpb", "ACT"], "nRREFD"),
        TimingConstraint("Channel", ["RFMpb"], ["REFab", "RFMab"], "nRFMpb"),
        TimingConstraint("Bank", ["RFMpb"], ["ACT", "REFpb", "RFMpb"], "nRFMpb"),
        TimingConstraint("Channel", ["RCKSTRT"], ["RD", "RDA"], "nRCKSTRT2RD"),
        TimingConstraint("Channel", ["RD", "RDA"], ["RCKSTOP"], "nRD2RCKSTOP"),
        TimingConstraint("Channel", ["RCKSTOP"], ["RCKSTRT", "RD", "RDA"], "nRCKSP2ST"),
        TimingConstraint("Channel", ["RCKSTRT"], ["RCKSTOP"], "nRCKST2SP"),

        TimingConstraint("Channel", ["ACTAB"], ["ACTAB"], "nRRD"),
        TimingConstraint("Channel", ["ACTAB"], ["PREab"], "nRAS"),
        TimingConstraint("Channel", ["PREab"], ["ACTAB"], "nRP"),
        TimingConstraint("Channel", ["ACTAB"], ["REFab", "RFMab"], "nRC"),
        TimingConstraint("Channel", ["REFab"], ["ACTAB"], "nRFCab"),
        TimingConstraint("Channel", ["ACTAB"], ["MACAB"], "nRCDRD"),
        TimingConstraint("Bank", ["MACAB"], ["MACAB"], "nCCDAB"),
        TimingConstraint("Channel",
                         ["MACAB", "MACSB"],
                         ["PREab"], "nRTPSB"),
        TimingConstraint("Channel",
                         ["MACAB", "MACSB"],
                         ["MACAB", "MACSB"],
                         "nBL"),
        TimingConstraint("Channel",
                         ["WR_BB", "RD_BB", "WR_RB", "RD_RB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC"],
                         ["WR_BB", "RD_BB", "WR_RB", "RD_RB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC"],
                         "nBL"),
        TimingConstraint("Channel",
                         ["WR_BB"],
                         ["MACAB", "MACSB"],
                         "nWR_BB2MAC"),
        TimingConstraint("Channel",
                         ["WR_RB"],
                         ["MV_BB", "SFM", "ACT_FUNC"],
                         "nWR_RB2MV_BB"),
        TimingConstraint("Channel",
                         ["MV_RB"],
                         ["SFM", "ACT_FUNC"],
                         "nMV_RB2SFM"),
        TimingConstraint("Bank", ["MACSB"], ["MACSB"], "nCCDSB_PIM"),
        TimingConstraint("Bank", ["MACSB"], ["PREpb"], "nRTPSB"),
    ]

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        tCK = timing_dict["tCK_ps"]
        device_density = org_dict["device_density"]
        rate = timing_dict["rate"]

        timing_dict["nCCD"]     = timing_dict["nBL"]
        timing_dict["nCCDSB"]   = 4
        timing_dict["nPPD"]     = 2
        timing_dict["nRPD"]     = timing_dict["nPPD"]
        timing_dict["nREFI"]    = cls._resolve_nREFI(tCK)
        timing_dict["nREFIpb"]  = cls._resolve_nREFIpb(org_dict["bank"], tCK)
        timing_dict["nRC"]      = timing_dict["nRAS"] + timing_dict["nRP"]
        timing_dict["nRTW"]     = cls._resolve_nRTW(
            timing_dict["nRL"], timing_dict["nDQERL"],
            timing_dict["nBL"], timing_dict["nWL"])
        timing_dict["nRFCab"]   = cls._resolve_nRFCab(device_density, rate)
        timing_dict["nRFCpb"]   = cls._resolve_nRFCpb(device_density, rate)
        timing_dict["nRDREFab"] = timing_dict["nRL"] + timing_dict["nDQERL"] + timing_dict["nBL"] + 2
        timing_dict["nRFMab"]   = timing_dict["nRFCab"]
        timing_dict["nRFMpb"]   = timing_dict["nRFCpb"]
        timing_dict["nRCKPST"]  = 2
        timing_dict["nRD2RCKSTOP"] = max(1,
            timing_dict["nRL"] + timing_dict["nDQERL"] + timing_dict["nBL"] +
            timing_dict["nRCKPST"] - timing_dict["nRCKSTOP_LAT"])
        timing_dict["nRCKST2SP"] = timing_dict["nRL"] + timing_dict["nRCKSTRT2RD"]

        nCCD = timing_dict["nCCD"]
        nBL  = timing_dict["nBL"]
        timing_dict.setdefault("nCCDAB",     timing_dict["nCCDSB"])
        timing_dict.setdefault("nCCDSB_PIM", timing_dict["nCCDSB"])
        timing_dict.setdefault("nWR_BB",       nBL)
        timing_dict.setdefault("nRD_BB",      nBL)
        timing_dict.setdefault("nWR_RB",      nBL)
        timing_dict.setdefault("nRD_RB",      nBL)
        timing_dict.setdefault("nMV_RB",       nBL)
        timing_dict.setdefault("nMV_BB",       nBL)
        timing_dict.setdefault("nSFM",        nBL)
        timing_dict.setdefault("nACT_FUNC",   nBL)
        nWL = timing_dict["nWL"]
        timing_dict.setdefault("nWR_BB2MAC",    nWL + nBL)
        timing_dict.setdefault("nWR_RB2MV_BB",  nWL + nBL)
        timing_dict.setdefault("nMV_RB2SFM",    timing_dict["nMV_RB"])

    @staticmethod
    def _resolve_nREFI(tCK_ps):
        return math.floor(1_900_000 / tCK_ps)

    @staticmethod
    def _resolve_nREFIpb(bank, tCK_ps):
        if bank != 16:
            return -1
        return max(1, math.floor(1_900_000 / (16 * tCK_ps)))

    @staticmethod
    def _resolve_nRTW(nRL, nDQERL, nBL, nWL):
        return max(1, nRL + nDQERL + nBL + 3 - nWL + 1)

    @staticmethod
    def _resolve_nRFCab(device_density, rate):
        return {
            (16384, 28000): 315,
            (32768, 28000): 630,
            (65536, 28000): 1260,
        }.get((device_density, rate), -1)

    @staticmethod
    def _resolve_nRFCpb(device_density, rate):
        return {
            (16384, 28000): 105,
            (32768, 28000): 210,
            (65536, 28000): 420,
        }.get((device_density, rate), -1)


GDDR7PIM.org_presets = {
    "GDDR7PIM_16Gb_x8": {
        "device_density":    16384,
        "channel_density":   4096,
        "channels_per_device": 4,
        "dq":                8,
        "channel_width":     8,
        "bank":              16,
        "row":               1 << 14,
        "column":            (1 << 6) << 5,
    },
    "GDDR7PIM_32Gb_x8": {
        "device_density":    32768,
        "channel_density":   16384,
        "channels_per_device": 2,
        "dq":                8,
        "channel_width":     8,
        "bank":              16,
        "row":               1 << 16,
        "column":            (1 << 6) << 5,
    },
    "GDDR7PIM_64Gb_x8": {
        "device_density": 65536,
        "channel_density": 32768,
        "channels_per_device": 2,
        "dq": 8,
        "channel_width": 8,
        "bank": 16,
        "row": 1 << 17,
        "column": (1 << 6) << 5,
    },
}

GDDR7PIM.timing_presets = {
    "GDDR7PIM_28000": {
        "rate": 28000, "nBL": 2,
        "nRL": 24, "nWL": 6, "nDQERL": 0,
        "nRCDRD": 30, "nRCDWR": 19,
        "nRP": 30, "nRAS": 60,
        "nWR": 30, "nRTPSB": 4,
        "nRRD": 4, "nRREFD": 21,
        "nWTR": 9, "nWTRSB": 11,
        "nRCKEN": 6, "nRCKSTOP_LAT": 10,
        "nRCK_LS": 2, "nRCKSP2ST": 8,
        "nRCKSTRT2RD": 2,
        "tCK_ps": 571,
    },
}
