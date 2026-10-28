"""LPDDR6PIM_RTP — Pipelined Row Activation variant of LPDDR6PIM.

Same RTP design as LPDDR5PIM_RTP; key LPDDR6 differences:
  - Split ACTAB1/ACTAB2 (same as LPDDR5)
  - RCD timing is nRCDr (not nRCD)
  - Burst timing is nBL_min
  - Has MACPB (per-bank MAC)
"""
from ramulator.dram.lpddr6pim import LPDDR6PIM
from ramulator.dram.spec import TimingConstraint

_MAC_CMDS = ["MACAB", "MACSB", "MACPB"]
_ACTAB2_MACAB = set(["MACAB"])


def _is_actab2_to_macab(tc):
    return tc.preceding == ["ACTAB2"] and set(tc.following) == _ACTAB2_MACAB


_RTP_BASE = [
    tc for tc in LPDDR6PIM.timing_constraints
    if not _is_actab2_to_macab(tc)
    and not (tc.level == "Rank"
             and set(tc.preceding) == set(_MAC_CMDS)
             and tc.following == ["PREab"])
]

_RTP_EXTRA = [
    TimingConstraint("Rank",    ["ACTAB2"], ["CPYSB"],                                "nRCDr"),
    TimingConstraint("Channel", ["ACTAB2"], ["CPYSB"],                                "nRCDr"),
    TimingConstraint("Bank",    ["ACTAB2"], ["CPYSB"],                                "nRCDr"),
    TimingConstraint("Rank",    ["ACTAB2"], ["CPYSB_LA"],                             "nRCDr"),
    TimingConstraint("Channel", ["ACTAB2"], ["CPYSB_LA"],                             "nRCDr"),
    TimingConstraint("Bank",    ["ACTAB2"], ["CPYSB_LA"],                             "nRCDr"),
    TimingConstraint("Rank",    ["CPYSB"],  ["MACAB"],  "nCPYSB"),
    TimingConstraint("Channel", ["CPYSB"],  ["MACAB"],  "nCPYSB"),
    TimingConstraint("Rank",    ["CPYSB_LA"],["MACAB"], "nCPYSB"),
    TimingConstraint("Channel", ["CPYSB_LA"],["MACAB"], "nCPYSB"),
    TimingConstraint("Rank",    ["ACTAB1"],  ["PREab_LA"],                             "nRAS"),
    TimingConstraint("Rank",    ["CPYSB"],   ["PREab_LA"],                             "nRTP"),
    TimingConstraint("Rank",    ["CPYSB_LA"],["PREab_LA"],                             "nRTP"),
    TimingConstraint("Rank",    ["PREab_LA"],["ACTAB1"],                               "nRPab"),
    TimingConstraint("Rank",    ["PREab_LA"],["REFab"],                                "nRPab"),
    TimingConstraint("Rank",    ["MACAB"],   ["CPYSB_LA"],                             "nCCDAB"),
]


class LPDDR6PIM_RTP(LPDDR6PIM):
    name = "LPDDR6PIM_RTP"
    manual_codegen = True

    states        = ["Opened", "Closed", "Activating",
                     "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"]
    commands      = LPDDR6PIM.commands + ["CPYSB", "CPYSB_LA", "PREab_LA"]
    timing_params = LPDDR6PIM.timing_params + ["nCPYSB", "nCPYSB_LA"]
    timing_constraints = _RTP_BASE + _RTP_EXTRA

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        super().resolve_secondary_timings(timing_dict, org_dict)
        timing_dict.setdefault("nCPYSB",    1)
        timing_dict.setdefault("nCPYSB_LA", 1)


LPDDR6PIM_RTP.org_presets    = LPDDR6PIM.org_presets
LPDDR6PIM_RTP.timing_presets = LPDDR6PIM.timing_presets
