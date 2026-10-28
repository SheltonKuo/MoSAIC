#ifndef RAMULATOR_DRAM_COMMANDS_SETH_H
#define RAMULATOR_DRAM_COMMANDS_SETH_H

#include "ramulator/dram/dram_spec.h"

namespace Ramulator::Cmd {

template <class T>
struct SETH {
  static constexpr DRAMCommandMeta meta = {};
  static constexpr BankTarget bank_target = BankTarget::All;
};

}

#endif
