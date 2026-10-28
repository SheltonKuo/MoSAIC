#ifndef RAMULATOR_DRAM_COMMANDS_BARRIER_H
#define RAMULATOR_DRAM_COMMANDS_BARRIER_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct BARRIER {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;
};

}

#endif
