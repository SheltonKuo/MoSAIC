#ifndef RAMULATOR_DRAM_COMMANDS_SETM_H
#define RAMULATOR_DRAM_COMMANDS_SETM_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct SETM {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}

#endif
