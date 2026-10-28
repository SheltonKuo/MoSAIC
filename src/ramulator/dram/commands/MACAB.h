#ifndef RAMULATOR_DRAM_COMMANDS_MACAB_H
#define RAMULATOR_DRAM_COMMANDS_MACAB_H

#include "ramulator/dram/commands/ACTAB2.h"
#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct MACAB {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return ACTAB2<T>::preq(bank, cmd, addr_vec, clk);
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_state == T::State::Opened &&
           bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end();
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_state == T::State::Opened;
  }
};

}

#endif
