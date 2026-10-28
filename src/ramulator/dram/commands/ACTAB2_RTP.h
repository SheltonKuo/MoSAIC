#ifndef RAMULATOR_DRAM_COMMANDS_ACTAB2_RTP_H
#define RAMULATOR_DRAM_COMMANDS_ACTAB2_RTP_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACTAB2_RTP {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    if (bank->m_secondary_buffer_ready) {
      bank->m_state = T::State::Preloading;
    } else {
      bank->m_row_state.clear();
      bank->m_state = T::State::Opened;
    }
    bank->m_row_state[addr_vec[T::Level::Row]] = T::State::Opened;
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
      case T::State::Preloading:
        if (bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end())
          return cmd;
        return T::Command::ACTAB1;
      default:
        throw std::runtime_error("[ACTAB2_RTP] Invalid bank state!");
    }
  }
};

}

#endif
