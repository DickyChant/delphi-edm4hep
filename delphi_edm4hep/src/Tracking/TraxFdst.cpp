// TraxFdstWriter — pass-2 implementation.
//
// PA.TRAX (label 20) layout (longdes §3.04, verified vs the legacy
// delphi_fdst_pad_dump TRAX reader):
//   +2  N_points
//   per-point record (starts at ltrax+3, stride = n_words):
//     +0 n_words   +1 det_id   +2 meas_code (0=plane,1=cylinder)
//     +3..+5 c1,c2,c3   +6 θ   +7 φ   +8 1/P
//     +9..+(8+min(15,n_words-9))  cov (5x5 lower-tri)
//   bank length from IPHREQ(1) bounds the walk.

#include "delphi_edm4hep/Tracking/TraxFdst.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::trax_fdst {

namespace {
constexpr std::int32_t kAlgoTrax  = 20;
constexpr float        kCm2Mm     = 10.f;
constexpr int          kMaxPoints = 12;   // generous; realistic ~5
}  // namespace

void TraxFdstWriter::emit()
{
  edm4hep::ParticleIDCollection col;

  if (!ctx_.fdst_pa_to_sdst_particle) {
    put(std::move(col), "TRAX", "ExtrapPoints");
    return;
  }
  const auto& pa_to_particle = *ctx_.fdst_pa_to_sdst_particle;
  // fDST_MAIN_Particles (created by MainHybrid, which now runs BEFORE this
  // writer): link the relation to the fDST clones, 1:1 by particle_idx with
  // sDST_MAIN_Particles. (TraxFdstWriter moved after MainHybrid for this.)
  const auto& fdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>("fDST_MAIN_Particles");

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int ltrax = pawalk::lphpa("TRAX", lpa);
    if (ltrax <= 0) return;
    if (paIdx >= static_cast<int>(pa_to_particle.size())) return;
    const int particle_idx = pa_to_particle[paIdx];
    if (particle_idx < 0 ||
        particle_idx >= static_cast<int>(fdst_particles.size())) return;

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
      pid.setParticle(fdst_particles[particle_idx]);

      lpt += n_words;
    }
  });

  put(std::move(col), "TRAX", "ExtrapPoints");
}

}  // namespace delphi_edm4hep::trax_fdst
