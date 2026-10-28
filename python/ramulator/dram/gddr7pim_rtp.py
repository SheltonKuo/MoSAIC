"""GDDR7PIM_RTP — Pipelined Row Activation variant of GDDR7PIM.

Key GDDR7 differences from LPDDR5/6:
  - Single ACTAB (no ACTAB1/ACTAB2 split)
  - No Rank level, no BankGroup → constraints at Channel and Bank only
  - No Activating state
  - RCD is nRCDRD; precharge recovery is nRP; PIM row-to-precharge is nRTPSB
  - Dual row+column bus (HBMControllerBase)
"""
from ramulator.dram.gddr7pim import GDDR7PIM
from ramulator.dram.spec import TimingConstraint

_MAC_CMDS  = ["MACAB", "MACSB"]
_ACTAB_MAC = set(["MACAB"])


def _is_actab_to_macab(tc):
    return tc.preceding == ["ACTAB"] and set(tc.following) == _ACTAB_MAC


_RTP_BASE = [
    tc for tc in GDDR7PIM.timing_constraints
    if not _is_actab_to_macab(tc)
    and not (set(tc.preceding) <= set(_MAC_CMDS)
             and tc.following == ["PREab"])
]

_RTP_EXTRA = [
    TimingConstraint("Channel", ["ACTAB"],    ["CPYSB"],                               "nRCDRD"),
    TimingConstraint("Bank",    ["ACTAB"],    ["CPYSB"],                               "nRCDRD"),
    TimingConstraint("Channel", ["ACTAB"],    ["CPYSB_LA"],                            "nRCDRD"),
    TimingConstraint("Bank",    ["ACTAB"],    ["CPYSB_LA"],                            "nRCDRD"),
    TimingConstraint("Channel", ["CPYSB"],   ["MACAB"],  "nCPYSB"),
    TimingConstraint("Bank",    ["CPYSB"],   ["MACAB"],  "nCPYSB"),
    TimingConstraint("Channel", ["CPYSB_LA"],["MACAB"],  "nCPYSB"),
    TimingConstraint("Bank",    ["CPYSB_LA"],["MACAB"],  "nCPYSB"),
    TimingConstraint("Channel", ["ACTAB"],    ["PREab_LA"],                             "nRAS"),
    TimingConstraint("Channel", ["CPYSB"],    ["PREab_LA"],                             "nRTPSB"),
    TimingConstraint("Channel", ["CPYSB_LA"], ["PREab_LA"],                             "nRTPSB"),
    TimingConstraint("Channel", ["PREab_LA"], ["ACTAB"],                                "nRP"),
    TimingConstraint("Channel", ["PREab_LA"], ["REFab"],                                "nRP"),
    TimingConstraint("Channel", ["MACAB"],    ["CPYSB_LA"],                             "nCCDAB"),
]


class GDDR7PIM_RTP(GDDR7PIM):
    name = "GDDR7PIM_RTP"
    manual_codegen = True

    states        = ["Opened", "Closed",
                     "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"]
    commands      = GDDR7PIM.commands + ["CPYSB", "CPYSB_LA", "PREab_LA"]
    timing_params = GDDR7PIM.timing_params + ["nCPYSB", "nCPYSB_LA"]
    timing_constraints = _RTP_BASE + _RTP_EXTRA

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        super().resolve_secondary_timings(timing_dict, org_dict)
        timing_dict.setdefault("nCPYSB",    1)
        timing_dict.setdefault("nCPYSB_LA", 1)


GDDR7PIM_RTP.org_presets    = GDDR7PIM.org_presets
GDDR7PIM_RTP.timing_presets = GDDR7PIM.timing_presets
