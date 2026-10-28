add_library(ramulator-dram OBJECT)

target_sources(
  ramulator-dram PRIVATE
  node.h  node.cpp
  device.h  device.cpp
  dram_spec.h  dram_spec.cpp
  func_types.h

  commands/ACT.h  commands/ACT1.h  commands/ACT2.h
  commands/PREpb.h  commands/PREab.h  commands/PREsb.h
  commands/RD.h   commands/WR.h
  commands/RDA.h  commands/WRA.h
  commands/RD_S.h   commands/WR_S.h
  commands/RDA_S.h  commands/WRA_S.h
  commands/RD_L.h   commands/WR_L.h
  commands/RDA_L.h  commands/WRA_L.h
  commands/REFab.h  commands/REFpb.h  commands/REFsb.h
  commands/RFMab.h  commands/RFMpb.h  commands/RFMsb.h
  commands/RCKSTRT.h  commands/RCKSTOP.h
  commands/CAS.h  commands/CAS_RD.h  commands/CAS_WR.h
  commands/VRR.h
  commands/populate.h
  commands/ACTAB.h
  commands/ACTAB1.h
  commands/ACTAB2.h
  commands/ACTAB1_RTP.h
  commands/ACTAB2_RTP.h
  commands/MACAB_RTP.h
  commands/CPYSB.h
  commands/CPYSB_LA.h
  commands/ACTAB1_LA.h
  commands/ACTAB2_LA.h
  commands/MACAB_LA.h
  commands/PREab_LA.h
  commands/MACAB.h
  commands/MACAB_GDDR.h
  commands/ACTAB_RTP.h
  commands/MACAB_GDDR_RTP.h
  commands/MACSB_GDDR.h
  commands/MACSB.h
  commands/MACPB.h
  commands/PIM_CTRL.h
  commands/WR_BB.h
  commands/RD_BB.h
  commands/WR_RB.h
  commands/RD_RB.h
  commands/MV_RB.h
  commands/MV_BB.h
  commands/SFM.h
  commands/ACT_FUNC.h
  commands/SETM.h
  commands/SETH.h
  commands/BARRIER.h

  impl/DDR3.cpp
  impl/DDR4.cpp
  impl/DDR4_VRR.cpp
  impl/DDR5.cpp
  impl/DDR5_VRR.cpp
  impl/HBM1.cpp
  impl/HBM2.cpp
  impl/HBM3.cpp
  impl/HBM4.cpp
  impl/LPDDR5.cpp
  impl/LPDDR5PIM.cpp
  impl/LPDDR5PIM_RTP.cpp
  impl/LPDDR6.cpp
  impl/LPDDR6PIM.cpp
  impl/LPDDR6PIM_RTP.cpp
  impl/GDDR6.cpp
  impl/GDDR7.cpp
  impl/GDDR7PIM.cpp
  impl/GDDR7PIM_RTP.cpp
)

target_link_libraries(
  ramulator
  PRIVATE
  ramulator-dram
)
