// TraxWriter — implementation. Runs in both passes.
//
// PA.TRAX (label 20) layout (longdes §3.04, verified vs the legacy
// delphi_fdst_pad_dump TRAX reader):
//   +2  N_points
//   per-point record (starts at ltrax+3, stride = n_words):
//     +0 n_words   +1 det_id   +2 meas_code (0=plane,1=cylinder)
//     +3..+5 c1,c2,c3   +6 θ   +7 φ   +8 1/P
//     +9..+(8+min(15,n_words-9))  cov (5x5 lower-tri)
//   bank length from IPHREQ(1) bounds the walk.
//
// The detector each extrapolation point belongs to is a TANAGRA detector ID,
// written by PXTRAX from a fixed list (pxdst34.car:15991-15994):
//
//     0  first measured point (the TKR itself, one per track)
//     9  HPC     13  HAB (HCAL barrel)     22  HAF (HCAL endcap)
//    11  TOF     14  MUB                   26  EMF (FEMC)
//                17  MUS                   30  MUF
//
// The names come from TANAGRA's own table, tanagra322.car:12164-12176 -- note
// NMCFL and IDMFL there are parallel by array index, not by ID, so the ID is
// IDMOD(index). Points are ordered by increasing R in the barrel and |Z| in
// the endcap.

#include "delphi_edm4hep/Tracking/Trax.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::trax {

namespace {
constexpr std::int32_t kAlgoTrax  = 20;
constexpr float        kCm2Mm     = 10.f;
constexpr int          kMaxPoints = 12;   // generous; realistic ~5
}  // namespace

void TraxWriter::emit()
{
  edm4hep::ParticleIDCollection col;


  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int ltrax = pawalk::lphpa("TRAX", lpa);
    if (ltrax <= 0) return;
    const auto particle = particleForPa(paIdx);
    if (!particle) return;

    const int blen   = pawalk::iphreq(1);
    const int lend   = ltrax + blen;
    const int npts   = static_cast<int>(std::lround(ph::Q(ltrax + 2)));
    int lpt = ltrax + 3;
    for (int ip = 0; ip < npts && ip < kMaxPoints && lpt < lend; ++ip) {
      const int n_words = static_cast<int>(std::lround(ph::Q(lpt + 0)));
      if (n_words <= 0 || n_words > 100) break;     // malformed
      if (lpt + n_words - 1 > lend) break;          // bank-end guard (lend = last valid word; allow exact-fit)

      auto pid = col.create();
      pid.setAlgorithmType(kAlgoTrax);
      pid.addToParameters(ph::Q(lpt + 1));            // det_id
      pid.addToParameters(ph::Q(lpt + 2));            // meas_code
      pid.addToParameters(ph::Q(lpt + 3) * kCm2Mm);   // c1 (mm)
      pid.addToParameters(ph::Q(lpt + 4) * kCm2Mm);   // c2 (mm)
      pid.addToParameters(ph::Q(lpt + 5) * kCm2Mm);   // c3 (mm)
      pid.addToParameters(ph::Q(lpt + 6));            // theta
      pid.addToParameters(ph::Q(lpt + 7));            // phi
      pid.addToParameters(ph::Q(lpt + 8));            // 1/P
      const int ncov = std::max(0, std::min(15, n_words - 9));
      for (int k = 0; k < 15; ++k)
        pid.addToParameters(k < ncov ? ph::Q(lpt + 9 + k) : 0.f);
      pid.setParticle(*particle);

      lpt += n_words;
    }
  });

  put(std::move(col), "TRAX", "ExtrapPoints", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::trax
