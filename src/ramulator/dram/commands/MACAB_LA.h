#ifndef RAMULATOR_DRAM_COMMANDS_MACAB_LA_H
#define RAMULATOR_DRAM_COMMANDS_MACAB_LA_H

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct MACAB_LA {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::Closed:
        return T::Command::ACTAB1;
      case T::State::Activating:
        if (bank->m_secondary_buffer_ready &&
            bank->m_row_state.count(addr_vec[T::Level::Row]))
          return cmd;
        return T::Command::ACTAB2;
      case T::State::Opened:
        if (!bank->m_secondary_buffer_ready)
          return T::Command::CPYSB;
        if (bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end())
          return cmd;
        return T::Command::PREab;
      case T::State::SecondaryOpen:
      case T::State::PrechargedSecondary:
      case T::State::Preloading:
        if (!bank->m_secondary_buffer_ready)
          return T::Command::CPYSB;
        if (bank->m_row_state.count(addr_vec[T::Level::Row]))
          return cmd;
        return T::Command::PREab;
      default:
        throw std::runtime_error("[MACAB_LA] Invalid bank state!");
    }
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_secondary_buffer_ready &&
           (bank->m_state == T::State::Opened            ||
            bank->m_state == T::State::SecondaryOpen      ||
            bank->m_state == T::State::PrechargedSecondary ||
            bank->m_state == T::State::Preloading) &&
           bank->m_row_state.count(addr_vec[T::Level::Row]);
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_state == T::State::Opened            ||
           bank->m_state == T::State::SecondaryOpen      ||
           bank->m_state == T::State::PrechargedSecondary ||
           bank->m_state == T::State::Preloading;
  }
};

}

#endif
