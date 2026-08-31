// TeBank.h
//
// Decoder for the PA.TE* sub-bank layout (DELPHI "TANAGRA" track-element
// format), shared by all eight track-element modules:
//
//   TEID 12  inner detector      TEFB 16  forward chamber B
//   TETP 13  TPC                 TERF 21  forward RICH
//   TEOD 14  outer detector      TEST 41  straw tubes
//   TEFA 15  forward chamber A   TEVF 42  very forward tracker
//
// A module stores its label once, then one or more track-element records
// (TERs). Word offsets are 1-based from the LPHPA address:
//
//   +1                  label + 0.1*stage
//   then per TER, the first starting at +2:
//     +0                descriptor (raw integer, bits 1..15)
//     +1..+3            coord1, coord2, coord3 (cm)
//     +4, +5, +6        theta, phi, (1/P or 1/Pt) at the TE reference point
//     +7..+6+m          error matrix, lower-tri row-major over the n measured
//                       fields; m = n*(n+1)/2
//     +7+m, +8+m, +9+m  ndf, chi^2, track length (cm)
//
// so a TER occupies 10 + m words and a module 1 + sum over its TERs.
//
// Descriptor bit encoding (1-indexed):
//   bit 1     coord frame: 0 = (x,y,z), 1 = (R, R*phi, z) [cylindrical]
//   bit 2     non-standard (u,v,z) coords (not handled here)
//   bits 3-5  coord1/2/3 "measured" — ignored: the coordinates are always
//             present at +1..+3 and these bits do not size the cov
//   bit 6     t1 (= x or R) measured  -> TE-basis idx 0 (c1)
//   bit 7     t2 (= y or z) measured  -> idx 2 if cylindrical, else idx 1
//   bit 8     theta measured          -> idx 3
//   bit 9     phi   measured          -> idx 4
//   bit 10    1/P  measured           -> idx 5
//   bit 11    1/Pt measured           -> idx 5  (invPt flag set)
//   bits 12-15  E, beta, dE/dx, time — not in the 6-component helix
//             push-forward; ignored.
//
// A module may carry more than one record. Which modules do depends on the
// detector and on the processing, so a caller must handle any count.
//
// Lengths stay in bank units (cm). Helix::fromTrackElement takes coordinates
// in cm and converts internally, so callers convert only what they emit.

#pragma once

#include "delphi_edm4hep/Helix.h"

#include <vector>

namespace delphi_edm4hep::te_bank {

// One track-element record.
struct Decoded {
  int   descriptor      = 0;
  int   n_measured      = 0;
  int   m_cov_entries   = 0;     // m = n(n+1)/2
  bool  is_cylindrical  = false; // bit 1
  bool  invPt           = false; // bit 11 (word +6 of the TER is 1/Pt)
  bool  has_meas[6]     = {};    // per TE-basis field 0..5
  float coord[3]        = {};    // coordinates 1..3, cm
  float theta           = 0.f;   // rad; zero where the descriptor says
  float phi             = 0.f;   // rad; the field was not measured
  float invP            = 0.f;   // 1/GeV, 1/Pt when invPt
  CovMatrix6 cov{};              // zero outside measured rows/cols
  float ndf             = 0.f;
  float chi2            = 0.f;
  float length          = 0.f;   // cm
};

// One TE module: its label and every record it carries.
struct Module {
  int label = 0;                  // 12..16, 21, 41, 42
  int stage = 0;                  // 0 before the label + 0.1*stage encoding
  std::vector<Decoded> elements;  // in bank order
  bool ok = false;                // the walk accounted for every bank word
};

// Decode the module at L-address `lte` with bank length `blen` (from
// IPHREQ(1) immediately after the LPHPA call).
Module decodeModule(int lte, int blen);

}  // namespace delphi_edm4hep::te_bank
