#ifndef RAMULATOR_DRAM_COMMANDS_ACT_FUNC_H
#define RAMULATOR_DRAM_COMMANDS_ACT_FUNC_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct ACT_FUNC {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;
};

}

#endif
