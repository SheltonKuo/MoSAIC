#ifndef RAMULATOR_DRAM_COMMANDS_WR_BB_H
#define RAMULATOR_DRAM_COMMANDS_WR_BB_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct WR_BB {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::Single;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_WR_BB_H
