#ifndef RAMULATOR_DRAM_COMMANDS_CPYSB_LA_H
#define RAMULATOR_DRAM_COMMANDS_CPYSB_LA_H

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct CPYSB_LA {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    bank->m_state = T::State::SecondaryOpen;
    bank->m_secondary_buffer_ready = true;
    bank->m_row_state.clear();
    bank->m_row_state[addr_vec[T::Level::Row]] = T::State::Opened;
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_CPYSB_LA_H
