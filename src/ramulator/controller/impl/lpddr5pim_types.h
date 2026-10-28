#ifndef RAMULATOR_CONTROLLER_IMPL_LPDDR5PIM_TYPES_H
#define RAMULATOR_CONTROLLER_IMPL_LPDDR5PIM_TYPES_H

#include "ramulator/base/request.h"

namespace Ramulator {

struct PIMRequestType {
  enum : int {
    Read      = Request::Type::Read,
    Write     = Request::Type::Write,
    MAC_AB    = 2,
    MAC_SB    = 6,
    MAC_PB    = 7,
    WR_BB     = 8,
    MV_RB     = 9,
    MV_BB     = 10,
    SFM       = 11,
    ACT_FUNC  = 12,
    SET_MODEL = 13,
    SET_HEAD  = 14,
    BARRIER   = 15,
    RD_BB     = 16,
    WR_RB     = 17,
    RD_RB     = 18,
    COUNT     = 19,
  };

  static int from_string(const std::string& op) {
    if (op == "R")          return Read;
    if (op == "W")          return Write;
    if (op == "MAC_AB")     return MAC_AB;
    if (op == "MAC_SB")     return MAC_SB;
    if (op == "MAC_PB")     return MAC_PB;
    if (op == "WR_BB")      return WR_BB;
    if (op == "MV_RB")      return MV_RB;
    if (op == "MV_BB")      return MV_BB;
    if (op == "SFM")        return SFM;
    if (op == "ACT_FUNC")   return ACT_FUNC;
    if (op == "SET_MODEL")  return SET_MODEL;
    if (op == "SET_HEAD")   return SET_HEAD;
    if (op == "BARRIER")    return BARRIER;
    if (op == "RD_BB")      return RD_BB;
    if (op == "WR_RB")      return WR_RB;
    if (op == "RD_RB")      return RD_RB;
    return -1;
  }
};

}

#endif
