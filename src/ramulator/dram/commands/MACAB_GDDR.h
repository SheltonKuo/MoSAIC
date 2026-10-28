#ifndef RAMULATOR_DRAM_COMMANDS_MACAB_GDDR_H
#define RAMULATOR_DRAM_COMMANDS_MACAB_GDDR_H

#include "ramulator/dram/node.h"

namespace Ramulator::Cmd {

template <class T>
struct MACAB_GDDR {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;

  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    switch (bank->m_state) {
      case T::State::Closed:
        return T::Command::ACTAB;
      case T::State::Opened:
        if (bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end()) {
          return cmd;
        }
        return T::Command::PREab;
      default:
        return T::Command::PREab;
    }
  }

  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_state == T::State::Opened &&
           bank->m_row_state.find(addr_vec[T::Level::Row]) != bank->m_row_state.end();
  }

  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return bank->m_state == T::State::Opened;
  }
};

template <class T>
struct MACAB_GDDR_2 {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;
  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::preq(bank, cmd, addr_vec, clk);
  }
  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowhit(bank, cmd, addr_vec, clk);
  }
  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowopen(bank, cmd, addr_vec, clk);
  }
};

template <class T>
struct MACAB_GDDR_4 {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;
  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::preq(bank, cmd, addr_vec, clk);
  }
  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowhit(bank, cmd, addr_vec, clk);
  }
  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowopen(bank, cmd, addr_vec, clk);
  }
};

template <class T>
struct MACAB_GDDR_8 {
  static constexpr DRAMCommandMeta meta = {.is_accessing = true};
  static constexpr BankTarget bank_target = BankTarget::All;
  static int preq(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::preq(bank, cmd, addr_vec, clk);
  }
  static bool rowhit(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowhit(bank, cmd, addr_vec, clk);
  }
  static bool rowopen(DRAMNode* bank, int cmd, const AddrVec_t& addr_vec, Clk_t clk) {
    return MACAB_GDDR<T>::rowopen(bank, cmd, addr_vec, clk);
  }
};

}

#endif
