// TeBank.h
//
// Decoder for the PA.TE{ID,TP,OD,FA,FB} sub-bank layout (DELPHI
// "TANAGRA" track-element format). Translates the variable-length
// per-measurement-code cov matrix into the fixed 6x6 TE-basis cov
// consumed by Helix::fromTrackElement, and extracts ndf/chi2/length.
//
// Bank layout (Q(LTE+i), i=1-based; verified empirically against
// longdes.pdf + qq sample):
//
//   +1            label + 0.1*stage  (label = 12..16 for TEID/TP/OD/FA/FB)
//   +2            descriptor (raw integer, bits 1..15)
//   +3..+5        coord1, coord2, coord3 (cm)
//   +6, +7, +8    theta, phi, (1/P or 1/Pt) at TE reference point
//   +9..+8+m      error matrix lower-tri row-major over the n MEASURED
//                 fields; m = n*(n+1)/2
//   +9+m          ndf
//   +10+m         chi^2
//   +11+m         track length (cm)
//
// Total bank length = 11 + m words (single TER).
//
// Descriptor bit encoding (1-indexed):
//   bit 1   coord frame: 0 = (x,y,z), 1 = (R, R*phi, z) [cylindrical]
//   bit 2   non-standard (u,v,z) coords  (we don't handle that here)
//   bits 3-5  coord1/2/3 are "measured" (we ignore — coords are always
//             present at +3..+5; bits don't contribute to the cov)
//   bit 6   t1 (= x or R) measured  → maps to TE-basis idx 0 (c1)
//   bit 7   t2 (= y or z) measured  → idx 2 if cylindrical, else idx 1
//   bit 8   theta measured          → idx 3
//   bit 9   phi   measured          → idx 4
//   bit 10  1/P  measured           → idx 5
//   bit 11  1/Pt measured           → idx 5  (invPt flag set)
//   bits 12-15  E, beta?, dE/dx, time — not in the 6-component helix
//             push-forward; ignored.
//
// TEID can hold MULTIPLE stacked TER's in one PA sub-bank. We decode
// only the first TER and set `ok=false` if the predicted 11+m doesn't
// match blen (the caller can treat the cov as best-effort).

#pragma once

#include "delphi_edm4hep/Helix.h"

namespace delphi_edm4hep::te_bank {

struct Decoded {
  int   descriptor      = 0;
  int   n_measured      = 0;
  int   m_cov_entries   = 0;     // m = n(n+1)/2
  bool  is_cylindrical  = false; // bit 1 set
  bool  invPt           = false; // bit 11 set (Q(+8) is 1/Pt)
  bool  has_meas[6]     = {};    // per TE-basis field 0..5
  CovMatrix6 cov{};              // zero outside measured rows/cols
  float ndf             = 0.f;
  float chi2            = 0.f;
  float length          = 0.f;   // cm
  bool  ok              = false; // false if blen != 11 + m (e.g. multi-TER)
};

// Decode the first TER at L-address `lte` with bank length `blen` (from
// IPHREQ(1) immediately after the LPHPA call). Returns a Decoded struct
// — partially populated if ok=false.
Decoded decode(int lte, int blen);

}  // namespace delphi_edm4hep::te_bank
