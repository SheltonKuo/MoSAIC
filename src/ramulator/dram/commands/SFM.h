#ifndef RAMULATOR_DRAM_COMMANDS_SFM_H
#define RAMULATOR_DRAM_COMMANDS_SFM_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct SFM {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_SFM_H
