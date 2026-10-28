#ifndef RAMULATOR_DRAM_COMMANDS_ACTAB1_RTP_H
#define RAMULATOR_DRAM_COMMANDS_ACTAB1_RTP_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACTAB1_RTP {
  static constexpr DRAMCommandMeta meta = {.is_opening = true};
  static constexpr BankTarget bank_target = BankTarget::All;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    bank->m_state = T::State::Activating;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::Closed:
        return T::Command::ACTAB1;
      case T::State::Activating:
        return T::Command::ACTAB2;
      case T::State::Opened:
        if (bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end()) {
          return cmd;
        }
        return T::Command::PREab;
      case T::State::SecondaryOpen:
        return T::Command::PREab_LA;
      case T::State::PrechargedSecondary:
        return T::Command::ACTAB1;
      default:
        throw std::runtime_error("[ACTAB1_RTP] Invalid bank state!");
    }
  }
};

}

#endif
