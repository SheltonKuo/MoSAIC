"""LPDDR5PIM_RTP — Look-Ahead RTP. C++ source is hand-written; codegen skips it.

Timeline (n_k_cols=64, K=4096):
  CK   0  ACTAB1[N]
  CK   1  ACTAB2[N]             → Opened
  CK   2  CPYSB                 → SecondaryOpen  (row N in 2nd buf)
  CK  16  MACAB[0]              reads 2nd buf
  CK  34  PREab_LA              → PrechargedSecondary  (nRAS from ACTAB1, nRTP from CPYSB)
           ↑ fires at first available CA bus slot after CK 34, during MAC execution
           ↑ higher CA bus priority than MACAB — fits in one nCCDAB gap
  CK  51  ACTAB1[N+1]           nRPab after PREab_LA — fires during MACAB[8]
  CK  52  ACTAB2[N+1]           → Preloading  (N+1 in primary, N still in secondary)
 CK 268  MACAB[63]             last MAC of row N
 CK 272  CPYSB_LA              nCCDAB after last MACAB; N+1 now in 2nd buf
 CK 273  MACAB[0][N+1]         nCPYSB after copy; 5 CK dead time total

nRPab and nRCD are fully hidden inside the row-N MAC execution. The remaining
dead time is nCCDAB (4 CK) from the last MACAB to CPYSB_LA plus nCPYSB (1 CK).
"""

from ramulator.dram.lpddr5pim import LPDDR5PIM
from ramulator.dram.spec import TimingConstraint

_MAC_CMDS = ["MACAB", "MACSB", "MACPB"]
_ACTAB2_MACAB = set(["MACAB"])

def _is_actab2_to_macab(tc):
    return (tc.preceding == ["ACTAB2"] and set(tc.following) == _ACTAB2_MACAB)

_LA_BASE_CONSTRAINTS = [
    tc for tc in LPDDR5PIM.timing_constraints
    if not _is_actab2_to_macab(tc)
    and not (
        tc.level == "Rank"
        and set(tc.preceding) == set(_MAC_CMDS)
        and tc.following == ["PREab"]
    )
]

_LA_EXTRA_CONSTRAINTS = [
    TimingConstraint(level="Rank",    preceding=["ACTAB2"], following=["CPYSB"],    latency="nRCD"),
    TimingConstraint(level="Channel", preceding=["ACTAB2"], following=["CPYSB"],    latency="nRCD"),
    TimingConstraint(level="Bank",    preceding=["ACTAB2"], following=["CPYSB"],    latency="nRCD"),
    TimingConstraint(level="Rank",    preceding=["ACTAB2"], following=["CPYSB_LA"], latency="nRCD"),
    TimingConstraint(level="Channel", preceding=["ACTAB2"], following=["CPYSB_LA"], latency="nRCD"),
    TimingConstraint(level="Bank",    preceding=["ACTAB2"], following=["CPYSB_LA"], latency="nRCD"),
    TimingConstraint(level="Rank",    preceding=["CPYSB"],
                     following=["MACAB"],         latency="nCPYSB"),
    TimingConstraint(level="Channel", preceding=["CPYSB"],
                     following=["MACAB"],         latency="nCPYSB"),
    TimingConstraint(level="Rank",    preceding=["ACTAB1"], following=["PREab_LA"], latency="nRAS"),
    TimingConstraint(level="Rank",    preceding=["CPYSB"],  following=["PREab_LA"], latency="nRTP"),
    TimingConstraint(level="Rank",    preceding=["CPYSB_LA"], following=["PREab_LA"], latency="nRTP"),
    TimingConstraint(level="Rank",    preceding=["PREab_LA"], following=["ACTAB1"], latency="nRPab"),
    TimingConstraint(level="Rank",    preceding=["PREab_LA"], following=["REFab"],  latency="nRPab"),
    TimingConstraint(level="Rank", preceding=["MACAB"],
                     following=["CPYSB_LA"], latency="nCCDAB"),
    TimingConstraint(level="Rank",    preceding=["CPYSB_LA"],
                     following=["MACAB"],         latency="nCPYSB"),
    TimingConstraint(level="Channel", preceding=["CPYSB_LA"],
                     following=["MACAB"],         latency="nCPYSB"),
]


class LPDDR5PIM_RTP(LPDDR5PIM):
    name = "LPDDR5PIM_RTP"
    manual_codegen = True

    states        = ["Opened", "Closed", "Activating",
                     "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"]
    commands      = LPDDR5PIM.commands + ["CPYSB", "CPYSB_LA", "PREab_LA"]
    timing_params = LPDDR5PIM.timing_params + ["nCPYSB", "nCPYSB_LA"]
    timing_constraints = _LA_BASE_CONSTRAINTS + _LA_EXTRA_CONSTRAINTS

    @classmethod
    def resolve_secondary_timings(cls, timing_dict, org_dict):
        super().resolve_secondary_timings(timing_dict, org_dict)
        timing_dict.setdefault("nCPYSB",    1)
        timing_dict.setdefault("nCPYSB_LA", 1)


LPDDR5PIM_RTP.org_presets    = LPDDR5PIM.org_presets
LPDDR5PIM_RTP.timing_presets = LPDDR5PIM.timing_presets
