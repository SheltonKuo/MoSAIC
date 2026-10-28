#ifndef RAMULATOR_DRAM_COMMANDS_WR_RB_H
#define RAMULATOR_DRAM_COMMANDS_WR_RB_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct WR_RB {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_WR_RB_H
