#ifndef RAMULATOR_DRAM_COMMANDS_MACPB_H
#define RAMULATOR_DRAM_COMMANDS_MACPB_H

#include "ramulator/dram/commands/MACSB.h"

namespace Ramulator::Cmd {

template <class T>
struct MACPB {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::Single;
  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACSB<T>::preq(bank, cmd, addr_vec, clk);
  }
  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACSB<T>::rowhit(bank, cmd, addr_vec, clk);
  }
  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACSB<T>::rowopen(bank, cmd, addr_vec, clk);
  }
};

}  // namespace Ramulator::Cmd

#endif  // RAMULATOR_DRAM_COMMANDS_MACPB_H
