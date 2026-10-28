#ifndef RAMULATOR_DRAM_COMMANDS_ACT2_H
#define RAMULATOR_DRAM_COMMANDS_ACT2_H

#include <stdexcept>

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT2 {
  static constexpr DRAMCommandMeta meta = {};  // NOT is_opening
  static constexpr BankTarget bank_target = BankTarget::Single;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    bank->m_state = T::State::Opened;
    bank->m_row_state[addr_vec[T::Level::Row]] = T::State::Opened;
  }

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    // RTP may leave a bank backed by its secondary row buffer when normal
    // RD/WR traffic resumes. Standard LPDDR split activation cannot consume
    // those states directly: close the bank first, then restart ACT1/ACT2.
    if constexpr (requires {
                    T::State::SecondaryOpen;
                    T::State::PrechargedSecondary;
                    T::State::Preloading;
                  }) {
      if (bank->m_state == T::State::SecondaryOpen ||
          bank->m_state == T::State::PrechargedSecondary ||
          bank->m_state == T::State::Preloading) {
        return T::Command::PREpb;
      }
    }

    switch (bank->m_state) {
      case T::State::Closed:
        return T::Command::ACT1;
      case T::State::Activating:
        return T::Command::ACT2;
      case T::State::Opened:
        if (bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end()) {
          return cmd;
        }
        return T::Command::PREpb;
      default:
        throw std::runtime_error("[ACT2] Invalid bank state!");
    }
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_ACT2_H
