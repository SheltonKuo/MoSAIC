/******************************************************************************
 * LPDDR6PIM_RTP — Pipelined Row Activation variant. Hand-written; manual_codegen=True.
 ******************************************************************************/
#include "ramulator/dram/dram_spec.h"

#include "ramulator/dram/commands/populate.h"
#include "ramulator/dram/commands/ACT1.h"
#include "ramulator/dram/commands/ACT2.h"
#include "ramulator/dram/commands/ACTAB1_RTP.h"
#include "ramulator/dram/commands/ACTAB2_RTP.h"
#include "ramulator/dram/commands/ACT_FUNC.h"
#include "ramulator/dram/commands/BARRIER.h"
#include "ramulator/dram/commands/CAS.h"
#include "ramulator/dram/commands/CPYSB.h"
#include "ramulator/dram/commands/CPYSB_LA.h"
#include "ramulator/dram/commands/MACAB_RTP.h"
#include "ramulator/dram/commands/MACPB.h"
#include "ramulator/dram/commands/MACSB.h"
#include "ramulator/dram/commands/MV_BB.h"
#include "ramulator/dram/commands/MV_RB.h"
#include "ramulator/dram/commands/PREab.h"
#include "ramulator/dram/commands/PREab_LA.h"
#include "ramulator/dram/commands/PREpb.h"
#include "ramulator/dram/commands/RDA_S.h"
#include "ramulator/dram/commands/RD_BB.h"
#include "ramulator/dram/commands/RD_RB.h"
#include "ramulator/dram/commands/RD_S.h"
#include "ramulator/dram/commands/REFab.h"
#include "ramulator/dram/commands/SETH.h"
#include "ramulator/dram/commands/SETM.h"
#include "ramulator/dram/commands/SFM.h"
#include "ramulator/dram/commands/WRA_S.h"
#include "ramulator/dram/commands/WR_BB.h"
#include "ramulator/dram/commands/WR_RB.h"
#include "ramulator/dram/commands/WR_S.h"

namespace Ramulator {

class LPDDR6PIM_RTP : public DRAMSpec {
 public:
  struct Level {
    enum : int { Channel, Rank, BankGroup, Bank, Row, Column, COUNT };
  };
  struct Command {
    enum : int { ACT1, ACT2, PREpb, PREab, CAS, RD_S, WR_S, RDA_S, WRA_S, REFab, ACTAB1, ACTAB2, MACAB, MACSB, MACPB, WR_BB, MV_RB, MV_BB, RD_BB, WR_RB, RD_RB, SFM, ACT_FUNC, SETM, SETH, BARRIER, CPYSB, CPYSB_LA, PREab_LA, COUNT };
  };
  struct State {
    enum : int { Opened, Closed, Activating, SecondaryOpen, PrechargedSecondary, Preloading, N_A, COUNT };
  };
  struct Timing {
    enum : int {
    rate, nBL_min, nBL_max, nRL, nWL, nRCDr, nRCDw, nRP, nRPab, nRAS, nRC, nWTP, nRTP, nPPD, nCCDS, nCCDL, nCCDS_WR,
    nCCDL_WR, nRRD, nWTRS, nWTRL, nRTW_S, nRTW_L, nFAW, nRFC, nREFI, nWCKPST, nCAS, nAAD, nCS, tCK_ps, nACU, nCCDAB,
    nCCDSB, nCCDPB, nWR_BB, nRD_BB, nWR_RB, nRD_RB, nMV_RB, nMV_BB, nSFM, nACT_FUNC,
    nWR_BB2MAC, nWR_RB2MV_BB, nMV_RB2SFM, nCPYSB, nCPYSB_LA, COUNT
    };
  };

  using CommandImpls = std::tuple<
      Cmd::ACT1<LPDDR6PIM_RTP>, Cmd::ACT2<LPDDR6PIM_RTP>, Cmd::PREpb<LPDDR6PIM_RTP>, Cmd::PREab<LPDDR6PIM_RTP>, Cmd::CAS<LPDDR6PIM_RTP>,
      Cmd::RD_S<LPDDR6PIM_RTP>, Cmd::WR_S<LPDDR6PIM_RTP>, Cmd::RDA_S<LPDDR6PIM_RTP>, Cmd::WRA_S<LPDDR6PIM_RTP>,
      Cmd::REFab<LPDDR6PIM_RTP>, Cmd::ACTAB1_RTP<LPDDR6PIM_RTP>, Cmd::ACTAB2_RTP<LPDDR6PIM_RTP>, Cmd::MACAB_RTP<LPDDR6PIM_RTP>,
      Cmd::MACSB<LPDDR6PIM_RTP>,
      Cmd::MACPB<LPDDR6PIM_RTP>, Cmd::WR_BB<LPDDR6PIM_RTP>, Cmd::MV_RB<LPDDR6PIM_RTP>, Cmd::MV_BB<LPDDR6PIM_RTP>,
      Cmd::RD_BB<LPDDR6PIM_RTP>, Cmd::WR_RB<LPDDR6PIM_RTP>, Cmd::RD_RB<LPDDR6PIM_RTP>, Cmd::SFM<LPDDR6PIM_RTP>,
      Cmd::ACT_FUNC<LPDDR6PIM_RTP>, Cmd::SETM<LPDDR6PIM_RTP>, Cmd::SETH<LPDDR6PIM_RTP>, Cmd::BARRIER<LPDDR6PIM_RTP>,
      Cmd::CPYSB<LPDDR6PIM_RTP>, Cmd::CPYSB_LA<LPDDR6PIM_RTP>, Cmd::PREab_LA<LPDDR6PIM_RTP>
  >;

  LPDDR6PIM_RTP(const ConfigNode& config) {
    level_count = Level::COUNT;
    command_count = Command::COUNT;
    state_count = State::COUNT;
    timing_count = Timing::COUNT;

    set_names(levels, level_names, {"Channel", "Rank", "BankGroup", "Bank", "Row", "Column"});
    set_names(commands, command_names, {"ACT1", "ACT2", "PREpb", "PREab", "CAS", "RD_S", "WR_S", "RDA_S", "WRA_S", "REFab", "ACTAB1", "ACTAB2", "MACAB", "MACSB", "MACPB", "WR_BB", "MV_RB", "MV_BB", "RD_BB", "WR_RB", "RD_RB", "SFM", "ACT_FUNC", "SETM", "SETH", "BARRIER", "CPYSB", "CPYSB_LA", "PREab_LA"});
    set_names(states, state_names, {"Opened", "Closed", "Activating", "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"});
    set_names(timings, timing_names, {
        "rate", "nBL_min", "nBL_max", "nRL", "nWL", "nRCDr", "nRCDw", "nRP", "nRPab", "nRAS", "nRC", "nWTP", "nRTP",
        "nPPD", "nCCDS", "nCCDL", "nCCDS_WR", "nCCDL_WR", "nRRD", "nWTRS", "nWTRL", "nRTW_S", "nRTW_L", "nFAW",
        "nRFC", "nREFI", "nWCKPST", "nCAS", "nAAD", "nCS", "tCK_ps", "nACU", "nCCDAB", "nCCDSB", "nCCDPB",
        "nWR_BB", "nRD_BB", "nWR_RB", "nRD_RB", "nMV_RB", "nMV_BB", "nSFM",
        "nACT_FUNC", "nWR_BB2MAC", "nWR_RB2MV_BB", "nMV_RB2SFM", "nCPYSB", "nCPYSB_LA"
    });

    internal_prefetch_size = 16;
    init_states = {
        State::N_A,
        State::N_A,
        State::N_A,
        State::Closed,
        State::Closed,
        State::N_A,
    };
    supported_requests = {
        Command::RD_S,
        Command::WR_S,
    };

    load_config(config);

    populate_commands(CommandImpls{}, *this);
  }
};

static bool _dram_lpddr6pim_rtp = DRAMSpec::register_standard(
    "LPDDR6PIM_RTP", [](const ConfigNode& config) { return std::make_unique<LPDDR6PIM_RTP>(config); });

}
