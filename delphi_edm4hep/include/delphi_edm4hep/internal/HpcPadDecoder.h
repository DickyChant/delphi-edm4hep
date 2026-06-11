// C++ transcription of DELPHI's PXHGET subroutine (Fortran source:
// /cvmfs/delphi.cern.ch/.../dstana/161018/src/car/pxdst34.car:17828).
//
// PXHGET unpacks the 3-word per-pad HPC cluster record that PXHPUT packs
// at EMCA bank construction time. Each per-pad record is 3 REAL*4 words
// but the contents are integer bits (Fortran EQUIVALENCE INTG/REAL).
// Decoded outputs: (E, layer, X, Y, Z, sigma_z) in GeV / [1..10] / cm.
//
// Originally lifted verbatim from ild/hpc_pad_decoder.hpp (legacy).

#pragma once

#include <cmath>
#include <cstdint>

namespace delphi_edm4hep::hpc {

inline void padDecode(std::int32_t i1, std::int32_t i2, std::int32_t i3,
                      float w1, float w2, float w3,
                      float& E, int& layer,
                      float& X, float& Y, float& Z, float& sigZ) {
  // PXHGET runtime decision: bit-interpretation if INTG in [0, 1e7];
  // else "old" format with NINT of the REAL value.
  int IPACK1, IPACK2, IPACK3;
  if (i1 < 0 || i1 > 10000000) {
    IPACK1 = static_cast<int>(std::lround(w1));
    IPACK2 = static_cast<int>(std::lround(w2));
    IPACK3 = static_cast<int>(std::lround(w3));
  } else {
    IPACK1 = i1;
    IPACK2 = i2;
    IPACK3 = i3;
  }
  constexpr float FR = 5.f, FP = 512.f, FZ = 8.f;

  const int IE = IPACK1 / 64;
  const int IN = IPACK1 - 64 * IE;
  int N = IN - 30;
  if (N < 1 || N > 10) N = -1;
  layer = N;
  E = IE / 1000.f;

  const int IR = IPACK2 / 4096;
  const int IP = IPACK2 - 4096 * IR;
  const float R   = (IR + 205.f * FR) / FR;
  const float phi = IP / FP;
  X = R * std::cos(phi);
  Y = R * std::sin(phi);

  const int IZ = IPACK3 / 256;
  const int IW = IPACK3 - 256 * IZ;
  Z    = (IZ - 260.f * FZ) / FZ;
  sigZ = IW / 10.f;
}

}  // namespace delphi_edm4hep::hpc
