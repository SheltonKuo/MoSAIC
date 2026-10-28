/******************************************************************************
 * GDDR7PIM_RTP — Pipelined Row Activation variant. Hand-written; manual_codegen=True.
 ******************************************************************************/
#include "ramulator/dram/dram_spec.h"

#include "ramulator/dram/commands/populate.h"
#include "ramulator/dram/commands/ACT.h"
#include "ramulator/dram/commands/ACTAB_RTP.h"
#include "ramulator/dram/commands/ACT_FUNC.h"
#include "ramulator/dram/commands/BARRIER.h"
#include "ramulator/dram/commands/CPYSB.h"
#include "ramulator/dram/commands/CPYSB_LA.h"
#include "ramulator/dram/commands/MACAB_GDDR_RTP.h"
#include "ramulator/dram/commands/MACSB_GDDR.h"
#include "ramulator/dram/commands/MV_BB.h"
#include "ramulator/dram/commands/MV_RB.h"
#include "ramulator/dram/commands/PREab.h"
#include "ramulator/dram/commands/PREab_LA.h"
#include "ramulator/dram/commands/PREpb.h"
#include "ramulator/dram/commands/RCKSTOP.h"
#include "ramulator/dram/commands/RCKSTRT.h"
#include "ramulator/dram/commands/RD.h"
#include "ramulator/dram/commands/RDA.h"
#include "ramulator/dram/commands/REFab.h"
#include "ramulator/dram/commands/REFpb.h"
#include "ramulator/dram/commands/RFMab.h"
#include "ramulator/dram/commands/RFMpb.h"
#include "ramulator/dram/commands/SETH.h"
#include "ramulator/dram/commands/SETM.h"
#include "ramulator/dram/commands/SFM.h"
#include "ramulator/dram/commands/WR.h"
#include "ramulator/dram/commands/WRA.h"
#include "ramulator/dram/commands/RD_BB.h"
#include "ramulator/dram/commands/RD_RB.h"
#include "ramulator/dram/commands/WR_BB.h"
#include "ramulator/dram/commands/WR_RB.h"

namespace Ramulator {

class GDDR7PIM_RTP : public DRAMSpec {
 public:
  struct Level {
    enum : int { Channel, Bank, Row, Column, COUNT };
  };
  struct Command {
    enum : int { ACT, PREpb, PREab, RD, WR, RDA, WRA, REFab, REFpb, RFMab, RFMpb, RCKSTRT, RCKSTOP, ACTAB, MACAB, MACSB, WR_BB, MV_RB, MV_BB, SFM, ACT_FUNC, SETM, SETH, BARRIER, RD_BB, WR_RB, RD_RB, CPYSB, CPYSB_LA, PREab_LA, COUNT };
  };
  struct State {
    enum : int { Opened, Closed, SecondaryOpen, PrechargedSecondary, Preloading, N_A, COUNT };
  };
  struct Timing {
    enum : int {
    rate, nBL, nRL, nWL, nDQERL, nRCDRD, nRCDWR, nRP, nRAS, nRC, nRRD, nRREFD, nRPD, nRTPSB, nPPD, nWR, nCCD, nCCDSB,
    nWTR, nWTRSB, nRTW, nREFI, nREFIpb, nRFCab, nRFCpb, nRDREFab, nRFMab, nRFMpb, nRCKSTRT2RD, nRD2RCKSTOP,
    nRCKSP2ST, nRCKST2SP, nRCKSTOP_LAT, nRCKEN, nRCK_LS, nRCKPST, tCK_ps, nCCDAB,
    nCCDSB_PIM, nWR_BB, nRD_BB, nWR_RB, nRD_RB, nMV_RB, nMV_BB, nSFM, nACT_FUNC,
    nWR_BB2MAC, nWR_RB2MV_BB, nMV_RB2SFM, nCPYSB, nCPYSB_LA, COUNT
    };
  };

  using CommandImpls = std::tuple<
      Cmd::ACT<GDDR7PIM_RTP>, Cmd::PREpb<GDDR7PIM_RTP>, Cmd::PREab<GDDR7PIM_RTP>, Cmd::RD<GDDR7PIM_RTP>, Cmd::WR<GDDR7PIM_RTP>,
      Cmd::RDA<GDDR7PIM_RTP>, Cmd::WRA<GDDR7PIM_RTP>, Cmd::REFab<GDDR7PIM_RTP>, Cmd::REFpb<GDDR7PIM_RTP>, Cmd::RFMab<GDDR7PIM_RTP>,
      Cmd::RFMpb<GDDR7PIM_RTP>, Cmd::RCKSTRT<GDDR7PIM_RTP>, Cmd::RCKSTOP<GDDR7PIM_RTP>, Cmd::ACTAB_RTP<GDDR7PIM_RTP>,
      Cmd::MACAB_GDDR_RTP<GDDR7PIM_RTP>, Cmd::MACSB_GDDR<GDDR7PIM_RTP>, Cmd::WR_BB<GDDR7PIM_RTP>, Cmd::MV_RB<GDDR7PIM_RTP>, Cmd::MV_BB<GDDR7PIM_RTP>, Cmd::SFM<GDDR7PIM_RTP>,
      Cmd::ACT_FUNC<GDDR7PIM_RTP>, Cmd::SETM<GDDR7PIM_RTP>, Cmd::SETH<GDDR7PIM_RTP>, Cmd::BARRIER<GDDR7PIM_RTP>,
      Cmd::RD_BB<GDDR7PIM_RTP>, Cmd::WR_RB<GDDR7PIM_RTP>, Cmd::RD_RB<GDDR7PIM_RTP>,
      Cmd::CPYSB<GDDR7PIM_RTP>, Cmd::CPYSB_LA<GDDR7PIM_RTP>, Cmd::PREab_LA<GDDR7PIM_RTP>
  >;

  GDDR7PIM_RTP(const ConfigNode& config) {
    level_count = Level::COUNT;
    command_count = Command::COUNT;
    state_count = State::COUNT;
    timing_count = Timing::COUNT;

    set_names(levels, level_names, {"Channel", "Bank", "Row", "Column"});
    set_names(commands, command_names, {"ACT", "PREpb", "PREab", "RD", "WR", "RDA", "WRA", "REFab", "REFpb", "RFMab", "RFMpb", "RCKSTRT", "RCKSTOP", "ACTAB", "MACAB", "MACSB", "WR_BB", "MV_RB", "MV_BB", "SFM", "ACT_FUNC", "SETM", "SETH", "BARRIER", "RD_BB", "WR_RB", "RD_RB", "CPYSB", "CPYSB_LA", "PREab_LA"});
    set_names(states, state_names, {"Opened", "Closed", "SecondaryOpen", "PrechargedSecondary", "Preloading", "N_A"});
    set_names(timings, timing_names, {
        "rate", "nBL", "nRL", "nWL", "nDQERL", "nRCDRD", "nRCDWR", "nRP", "nRAS", "nRC", "nRRD", "nRREFD", "nRPD",
        "nRTPSB", "nPPD", "nWR", "nCCD", "nCCDSB", "nWTR", "nWTRSB", "nRTW", "nREFI", "nREFIpb", "nRFCab", "nRFCpb",
        "nRDREFab", "nRFMab", "nRFMpb", "nRCKSTRT2RD", "nRD2RCKSTOP", "nRCKSP2ST", "nRCKST2SP", "nRCKSTOP_LAT",
        "nRCKEN", "nRCK_LS", "nRCKPST", "tCK_ps", "nCCDAB", "nCCDSB_PIM",
        "nWR_BB", "nRD_BB", "nWR_RB", "nRD_RB", "nMV_RB", "nMV_BB", "nSFM", "nACT_FUNC",
        "nWR_BB2MAC", "nWR_RB2MV_BB", "nMV_RB2SFM", "nCPYSB", "nCPYSB_LA"
    });

    internal_prefetch_size = 32;
    init_states = {
        State::N_A,
        State::Closed,
        State::Closed,
        State::N_A,
    };
    supported_requests = {
        Command::RD,
        Command::WR,
    };

    load_config(config);

    populate_commands(CommandImpls{}, *this);

      command_meta[Command::ACT].is_row_command = true;
      command_meta[Command::PREpb].is_row_command = true;
      command_meta[Command::PREab].is_row_command = true;
      command_meta[Command::REFab].is_row_command = true;
      command_meta[Command::REFpb].is_row_command = true;
      command_meta[Command::RFMab].is_row_command = true;
      command_meta[Command::RFMpb].is_row_command = true;
      command_meta[Command::ACTAB].is_row_command = true;
      command_meta[Command::RD].is_column_command = true;
      command_meta[Command::WR].is_column_command = true;
      command_meta[Command::RDA].is_column_command = true;
      command_meta[Command::WRA].is_column_command = true;
      command_meta[Command::RCKSTRT].is_column_command = true;
      command_meta[Command::RCKSTOP].is_column_command = true;
      command_meta[Command::MACAB].is_column_command = true;
      command_meta[Command::MACSB].is_column_command = true;
      command_meta[Command::WR_BB].is_column_command = true;
      command_meta[Command::RD_BB].is_column_command = true;
      command_meta[Command::WR_RB].is_column_command = true;
      command_meta[Command::RD_RB].is_column_command = true;
      command_meta[Command::MV_RB].is_column_command = true;
      command_meta[Command::MV_BB].is_column_command = true;
      command_meta[Command::SFM].is_column_command = true;
      command_meta[Command::ACT_FUNC].is_column_command = true;
      command_meta[Command::SETM].is_column_command = true;
      command_meta[Command::SETH].is_column_command = true;
      command_meta[Command::BARRIER].is_column_command = true;
  }
};

static bool _dram_gddr7pim_rtp = DRAMSpec::register_standard(
    "GDDR7PIM_RTP", [](const ConfigNode& config) { return std::make_unique<GDDR7PIM_RTP>(config); });

}
