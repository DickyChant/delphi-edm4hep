#include "delphi_edm4hep/TeBank.h"

#include "phdst/uxcom.hpp"

#include <cmath>

namespace ph = phdst;

namespace delphi_edm4hep::te_bank {

namespace {

// A TER occupies 10 + m words: descriptor, three coordinates, theta, phi,
// 1/P, m covariance entries, then ndf, chi2 and track length.
constexpr int kTerFixedWords = 10;

// Map from descriptor bit (1-indexed) to TE-basis field index (0..5).
// Returns -1 if the bit doesn't contribute to the 6-component basis.
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

// Number of error-matrix words this descriptor implies: the lower triangle
// over the fields it flags as measured.
int covEntries(int descriptor, bool cylindrical) {
  int n = 0;
  for (int bit = 6; bit <= 11; ++bit) {
    if (((descriptor >> (bit - 1)) & 0x1) &&
        basisIndexForBit(bit, cylindrical) >= 0) {
      ++n;
    }
  }
  return n * (n + 1) / 2;
}

// Decode the record whose descriptor sits at word `w`. The caller has already
// checked that the whole record lies inside the bank.
Decoded decodeElement(int lte, int w, int descriptor) {
  Decoded d;
  d.descriptor     = descriptor;
  d.is_cylindrical = (descriptor & 0x1) != 0;
  d.invPt          = ((descriptor >> 10) & 0x1) != 0;   // bit 11

  // Measured fields in ascending bit order; the error matrix rows follow the
  // same order.
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
  d.n_measured    = n;
  d.m_cov_entries = n * (n + 1) / 2;

  d.coord[0] = ph::Q(lte + w + 1);
  d.coord[1] = ph::Q(lte + w + 2);
  d.coord[2] = ph::Q(lte + w + 3);
  d.theta    = ph::Q(lte + w + 4);
  d.phi      = ph::Q(lte + w + 5);
  d.invP     = ph::Q(lte + w + 6);

  // Lower-tri row-major over the measured fields, scattered into the sparse
  // 6x6 TE-basis storage.
  for (int i = 0; i < n; ++i) {
    for (int j = 0; j <= i; ++j) {
      d.cov[covOffset(meas_basis_idx[i], meas_basis_idx[j])] =
        ph::Q(lte + w + 7 + lowerTriOffset(i, j));
    }
  }

  d.ndf    = ph::Q(lte + w + 7 + d.m_cov_entries);
  d.chi2   = ph::Q(lte + w + 8 + d.m_cov_entries);
  d.length = ph::Q(lte + w + 9 + d.m_cov_entries);
  return d;
}

}  // namespace

Module decodeModule(int lte, int blen) {
  Module mod;
  if (lte <= 0 || blen < 1 + kTerFixedWords) return mod;

  // From PXDST 2.87 the label carries the reconstruction stage as its first
  // decimal: 42.1 is the very forward tracker, stage 1.
  const double label_word = ph::Q(lte + 1);
  mod.label = static_cast<int>(label_word);
  mod.stage = static_cast<int>(std::lround(label_word * 10)) - mod.label * 10;

  for (int w = 2; w <= blen; ) {
    // Each record sizes itself, so the stride is only known once its
    // descriptor is read and a module may mix measurement codes.
    const int descriptor =
      static_cast<int>(std::lround(ph::Q(lte + w)));
    const int last =
      w + kTerFixedWords - 1 +
      covEntries(descriptor, (descriptor & 0x1) != 0);

    // Stop rather than read into the neighbouring ZEBRA bank. `ok` then stays
    // false, recording that the walk did not account for every word.
    if (last > blen) break;

    mod.elements.push_back(decodeElement(lte, w, descriptor));
    w = last + 1;              // the next descriptor, or blen + 1 when done
    mod.ok = (w == blen + 1);
  }
  return mod;
}

}  // namespace delphi_edm4hep::te_bank
