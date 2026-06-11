#include "delphi_edm4hep/TeBank.h"

#include "phdst/uxcom.hpp"

#include <cmath>

namespace ph = phdst;

namespace delphi_edm4hep::te_bank {

namespace {

// Map from descriptor bit (1-indexed) to TE-basis field index (0..5).
// Returns -1 if the bit doesn't contribute to the 6-component basis.
//   bit 6  → 0 (c1)
//   bit 7  → 2 if cylindrical else 1   (c3 or c2)
//   bit 8  → 3 (theta)
//   bit 9  → 4 (phi)
//   bit 10 → 5 (1/P)
//   bit 11 → 5 (1/Pt — alias)
int basisIndexForBit(int bit, bool cylindrical) {
  switch (bit) {
    case 6:  return 0;
    case 7:  return cylindrical ? 2 : 1;
    case 8:  return 3;
    case 9:  return 4;
    case 10: return 5;
    case 11: return 5;
    default: return -1;
  }
}

inline int lowerTriOffset(int i, int j) {
  return i * (i + 1) / 2 + j;
}

}  // namespace

Decoded decode(int lte, int blen) {
  Decoded d;
  if (lte <= 0 || blen < 12) return d;  // bank too small for any TER

  const float w2 = ph::Q(lte + 2);
  const int descriptor = static_cast<int>(std::lround(w2));
  d.descriptor = descriptor;
  d.is_cylindrical = (descriptor & 0x1) != 0;
  d.invPt = ((descriptor >> 10) & 0x1) != 0;   // bit 11

  // Collect measured bits in ascending order, mapped to TE-basis idx.
  int meas_basis_idx[6];
  int n = 0;
  for (int bit = 6; bit <= 11; ++bit) {
    if ((descriptor >> (bit - 1)) & 0x1) {
      const int idx = basisIndexForBit(bit, d.is_cylindrical);
      if (idx >= 0) {
        meas_basis_idx[n++] = idx;
        d.has_meas[idx] = true;
      }
    }
  }
  d.n_measured = n;
  d.m_cov_entries = n * (n + 1) / 2;

  const int expected_blen = 11 + d.m_cov_entries;
  d.ok = (blen == expected_blen);

  // Read cov entries in measured-field order (lower-tri row-major),
  // mapping back to TE-basis 6x6 sparse storage. Each entry lives at
  // Q(lte + 9 + slot); the bank's last valid word is Q(lte + blen), so
  // skip any slot that would fall past the bank end and leave that cov
  // element at 0. This guards a truncated/malformed bank (blen < 11 + m,
  // already flagged ok=false): without it the loop would read into the
  // neighbouring ZEBRA bank and store garbage covariances. For a
  // multi-TER stack (blen > 11 + m) every slot is in-bounds, so nothing
  // is skipped and the behaviour is unchanged.
  for (int i = 0; i < n; ++i) {
    for (int j = 0; j <= i; ++j) {
      const int slot = lowerTriOffset(i, j);   // 0-based slot within m
      if (9 + slot > blen) continue;           // past bank end leave 0
      const float v  = ph::Q(lte + 9 + slot);
      const int bi = meas_basis_idx[i];
      const int bj = meas_basis_idx[j];
      d.cov[covOffset(bi, bj)] = v;
    }
  }

  // ndf / chi2 / length at +9+m, +10+m, +11+m. Only safe to read if
  // expected blen matches actual (multi-TER stacks would put garbage
  // here for the first TER's predicted offsets).
  if (d.ok) {
    d.ndf    = ph::Q(lte + 9  + d.m_cov_entries);
    d.chi2   = ph::Q(lte + 10 + d.m_cov_entries);
    d.length = ph::Q(lte + 11 + d.m_cov_entries);
  }

  return d;
}

}  // namespace delphi_edm4hep::te_bank
