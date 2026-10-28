#ifndef RAMULATOR_DRAM_COMMANDS_PREAB_LA_H
#define RAMULATOR_DRAM_COMMANDS_PREAB_LA_H

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct PREab_LA {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;

  static void action(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    bank->m_state = T::State::PrechargedSecondary;
  }
};

}

#endif
