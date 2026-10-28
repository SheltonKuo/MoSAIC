#ifndef RAMULATOR_DRAM_COMMANDS_RD_RB_H
#define RAMULATOR_DRAM_COMMANDS_RD_RB_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct RD_RB {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_RD_RB_H
