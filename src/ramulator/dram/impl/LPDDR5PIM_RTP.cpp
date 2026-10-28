/******************************************************************************
 * LPDDR5PIM_RTP — Look-Ahead Pipelined Row Activation.  Hand-written; do NOT
 * regenerate via codegen (no Python DSL source).
 *
 * Hardware model:
 *   t= 0: ACTAB1[N]
 *   t= 1: ACTAB2[N]    → Opened
 *   t= 2: CPYSB         → SecondaryOpen  (row N safe in secondary buf)
 *   t=34: PREab_LA      → SecondaryOpen  (primary precharged; secondary intact)
 *   t=51: ACTAB1[N+1]   → Activating     (during MACAB execution)
 *   t=52: ACTAB2_LA[N+1]→ Preloading     (row N+1 loading in primary)
 *  t=268: MACAB[63]     ← last MAC of row N
 *  t=269: CPYSB_LA      → SecondaryOpen  (row N+1 now in secondary)
 *  t=270: MACAB[0][N+1]  2 CK dead time
 ******************************************************************************/
#include "ramulator/dram/dram_spec.h"

#include "ramulator/dram/commands/populate.h"
#include "ramulator/dram/commands/ACT1.h"
#include "ramulator/dram/commands/ACT2.h"
#include "ramulator/dram/commands/ACTAB1_LA.h"
#include "ramulator/dram/commands/ACTAB2_LA.h"
#include "ramulator/dram/commands/ACT_FUNC.h"
#include "ramulator/dram/commands/BARRIER.h"
#include "ramulator/dram/commands/CAS_RD.h"
#include "ramulator/dram/commands/CAS_WR.h"
#include "ramulator/dram/commands/CPYSB.h"
#include "ramulator/dram/commands/CPYSB_LA.h"
#include "ramulator/dram/commands/MACAB_LA.h"
#include "ramulator/dram/commands/MACPB.h"
#include "ramulator/dram/commands/MACSB.h"
#include "ramulator/dram/commands/MV_BB.h"
#include "ramulator/dram/commands/MV_RB.h"
#include "ramulator/dram/commands/PREab.h"
#include "ramulator/dram/commands/PREab_LA.h"
#include "ramulator/dram/commands/PREpb.h"
#include "ramulator/dram/commands/RD.h"
#include "ramulator/dram/commands/RDA.h"
#include "ramulator/dram/commands/RD_BB.h"
#include "ramulator/dram/commands/RD_RB.h"
#include "ramulator/dram/commands/REFab.h"
#include "ramulator/dram/commands/REFpb.h"
#include "ramulator/dram/commands/RFMab.h"
#include "ramulator/dram/commands/RFMpb.h"
#include "ramulator/dram/commands/SETH.h"
#include "ramulator/dram/commands/SETM.h"
#include "ramulator/dram/commands/SFM.h"
#include "ramulator/dram/commands/WR.h"
#include "ramulator/dram/commands/WRA.h"
#include "ramulator/dram/commands/WR_BB.h"
#include "ramulator/dram/commands/WR_RB.h"

namespace Ramulator {

class LPDDR5PIM_RTP : public DRAMSpec {
 public:
  struct Level {
    enum : int { Channel, Rank, BankGroup, Bank, Row, Column, COUNT };
  };
  struct Command {
    enum : int {
      ACT1, ACT2, PREpb, PREab, CAS_RD, CAS_WR, RD, WR, RDA, WRA,
      REFab, REFpb, RFMab, RFMpb,
      ACTAB1, ACTAB2,
      MACAB,
      MACSB, MACPB,
      WR_BB, MV_RB, MV_BB, RD_BB, WR_RB, RD_RB,
      SFM, ACT_FUNC, SETM, SETH, BARRIER,
      CPYSB, CPYSB_LA, PREab_LA,
      COUNT
    };
  };
  struct State {
    enum : int { Opened, Closed, Activating, SecondaryOpen, PrechargedSecondary, Preloading, N_A, COUNT };
  };
  struct Timing {
    enum : int {
      rate, nBL_min, nBL_max, nCL, nRCD, nRP, nRPab, nRAS, nRC,
      nWR, nRTP, nCWL, nPPD,
      nCCDS, nCCDL, nCCDS_WR, nCCDL_WR,
      nRRDS, nRRDL, nWTRS, nWTRL, nFAW,
      nRFC, nRFCpb, nREFI, nREFIpb,
      nWCKPST, nCAS, nAAD, nCS, tCK_ps,
      nPBR2PBR, nPBR2ACT,
      nCCDAB, nCCDSB, nCCDPB,
      nWR_BB, nRD_BB, nWR_RB, nRD_RB, nMV_RB, nMV_BB, nSFM, nACT_FUNC,
      nWR_BB2MAC, nWR_RB2MV_BB, nMV_RB2SFM,
      nCPYSB, nCPYSB_LA,
      COUNT
    };
  };

  using CommandImpls = std::tuple<
      Cmd::ACT1<LPDDR5PIM_RTP>,     Cmd::ACT2<LPDDR5PIM_RTP>,
      Cmd::PREpb<LPDDR5PIM_RTP>,    Cmd::PREab<LPDDR5PIM_RTP>,
      Cmd::CAS_RD<LPDDR5PIM_RTP>,   Cmd::CAS_WR<LPDDR5PIM_RTP>,
      Cmd::RD<LPDDR5PIM_RTP>,       Cmd::WR<LPDDR5PIM_RTP>,
      Cmd::RDA<LPDDR5PIM_RTP>,      Cmd::WRA<LPDDR5PIM_RTP>,
      Cmd::REFab<LPDDR5PIM_RTP>,    Cmd::REFpb<LPDDR5PIM_RTP>,
      Cmd::RFMab<LPDDR5PIM_RTP>,    Cmd::RFMpb<LPDDR5PIM_RTP>,
      Cmd::ACTAB1_LA<LPDDR5PIM_RTP>, Cmd::ACTAB2_LA<LPDDR5PIM_RTP>,
      Cmd::MACAB_LA<LPDDR5PIM_RTP>,
      Cmd::MACSB<LPDDR5PIM_RTP>,    Cmd::MACPB<LPDDR5PIM_RTP>,
      Cmd::WR_BB<LPDDR5PIM_RTP>,    Cmd::MV_RB<LPDDR5PIM_RTP>,    Cmd::MV_BB<LPDDR5PIM_RTP>,
      Cmd::RD_BB<LPDDR5PIM_RTP>,    Cmd::WR_RB<LPDDR5PIM_RTP>,    Cmd::RD_RB<LPDDR5PIM_RTP>,
      Cmd::SFM<LPDDR5PIM_RTP>,      Cmd::ACT_FUNC<LPDDR5PIM_RTP>,
      Cmd::SETM<LPDDR5PIM_RTP>,     Cmd::SETH<LPDDR5PIM_RTP>,
      Cmd::BARRIER<LPDDR5PIM_RTP>,
      Cmd::CPYSB<LPDDR5PIM_RTP>,
      Cmd::CPYSB_LA<LPDDR5PIM_RTP>,
      Cmd::PREab_LA<LPDDR5PIM_RTP>
  >;

  LPDDR5PIM_RTP(const ConfigNode& config) {
    level_count   = Level::COUNT;
    command_count = Command::COUNT;
    state_count   = State::COUNT;
    timing_count  = Timing::COUNT;

    set_names(levels, level_names,
        {"Channel", "Rank", "BankGroup", "Bank", "Row", "Column"});
    set_names(commands, command_names,
        {"ACT1", "ACT2", "PREpb", "PREab", "CAS_RD", "CAS_WR",
         "RD", "WR", "RDA", "WRA",
         "REFab", "REFpb", "RFMab", "RFMpb",
         "ACTAB1", "ACTAB2",
         "MACAB",
         "MACSB", "MACPB",
         "WR_BB", "MV_RB", "MV_BB", "RD_BB", "WR_RB", "RD_RB",
         "SFM", "ACT_FUNC", "SETM", "SETH", "BARRIER",
         "CPYSB", "CPYSB_LA", "PREab_LA"});
    set_names(states, state_names,
        {"Opened", "Closed", "Activating", "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"});
    set_names(timings, timing_names, {
        "rate", "nBL_min", "nBL_max", "nCL", "nRCD", "nRP", "nRPab", "nRAS", "nRC",
        "nWR", "nRTP", "nCWL", "nPPD",
        "nCCDS", "nCCDL", "nCCDS_WR", "nCCDL_WR",
        "nRRDS", "nRRDL", "nWTRS", "nWTRL", "nFAW",
        "nRFC", "nRFCpb", "nREFI", "nREFIpb",
        "nWCKPST", "nCAS", "nAAD", "nCS", "tCK_ps",
        "nPBR2PBR", "nPBR2ACT",
        "nCCDAB", "nCCDSB", "nCCDPB",
        "nWR_BB", "nRD_BB", "nWR_RB", "nRD_RB", "nMV_RB", "nMV_BB",
        "nSFM", "nACT_FUNC",
        "nWR_BB2MAC", "nWR_RB2MV_BB", "nMV_RB2SFM",
        "nCPYSB", "nCPYSB_LA"
    });

    internal_prefetch_size = 16;
    init_states = {
        State::N_A, State::N_A, State::N_A,
        State::Closed, State::Closed, State::N_A,
    };
    supported_requests = { Command::RD, Command::WR };

    load_config(config);
    populate_commands(CommandImpls{}, *this);

    command_meta[Command::MACAB].is_column_command     = true;
    command_meta[Command::MACSB].is_column_command     = true;
    command_meta[Command::WR_BB].is_column_command     = true;
    command_meta[Command::RD_BB].is_column_command     = true;
    command_meta[Command::WR_RB].is_column_command     = true;
    command_meta[Command::RD_RB].is_column_command     = true;
    command_meta[Command::MV_RB].is_column_command     = true;
    command_meta[Command::MV_BB].is_column_command     = true;
    command_meta[Command::SFM].is_column_command       = true;
    command_meta[Command::ACT_FUNC].is_column_command  = true;
    command_meta[Command::SETM].is_column_command      = true;
    command_meta[Command::SETH].is_column_command      = true;
    command_meta[Command::BARRIER].is_column_command   = true;
  }
};

static bool _dram_lpddr5pim_rtp = DRAMSpec::register_standard(
    "LPDDR5PIM_RTP",
    [](const ConfigNode& config) { return std::make_unique<LPDDR5PIM_RTP>(config); });

}
