// TofFdstWriter — pass-2 implementation.
//
// Per dst_content.txt p.30 + dstana/.../toflibxx.car (verified ground
// truth from the legacy delphi_fdst_pad_dump): PA.TOF layout is
//   Q(ltof+1)  module label (= 9)
//   Q(ltof+2)  counter number             (raw, not exported here)
//   Q(ltof+3)  NDSTCO                     (not used)
//   Q(ltof+4)  R coordinate               (raw; semantics flagged)
//   Q(ltof+5)  Z coordinate               (cm, physical)
//   Q(ltof+6)  Time of flight (XTOF, ns)  <-- exported as param[0]
//   Q(ltof+7)  Error on time  (ETOF, ns)  <-- exported as param[1]
//   Q(ltof+10) ZXTOF extrapolated Z       (cm, since v2.55; raw)

#include "delphi_edm4hep/Pid/TofFdst.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::tof_fdst {

namespace {
constexpr std::int32_t kAlgoTof = 5;
}

void TofFdstWriter::emit()
{
  edm4hep::ParticleIDCollection col;

  // Need the PA -> sDST Particle map (built by MatchProvenanceWriter
  // upstream) and the sDST_MAIN_Particles collection (loaded by the
  // harness). Emit empty collection if upstream isn't ready.
  if (!ctx_.fdst_pa_to_sdst_particle) {
    put(std::move(col), "TOF", "TimeOfFlight");
    return;
  }
  const auto& pa_to_particle = *ctx_.fdst_pa_to_sdst_particle;
  // fDST_MAIN_Particles (created by MainHybrid, which runs before this writer;
  // 1:1 with sDST_MAIN_Particles by clone index) so the PID->particle relation
  // targets the pass-2 particle collection.
  const auto& fdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>("fDST_MAIN_Particles");

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int ltof = pawalk::lphpa("TOF", lpa);
    if (ltof <= 0) return;
    if (paIdx >= static_cast<int>(pa_to_particle.size())) return;
    const int particle_idx = pa_to_particle[paIdx];
    if (particle_idx < 0) return;   // unmatched fDST PA, drop

    const float time_ns  = ph::Q(ltof + 6);
    const float sigma_ns = ph::Q(ltof + 7);

    auto pid = col.create();
    pid.setAlgorithmType(kAlgoTof);
    pid.addToParameters(time_ns);
    pid.addToParameters(sigma_ns);
    pid.setParticle(fdst_particles[particle_idx]);
  });

  put(std::move(col), "TOF", "TimeOfFlight");
}

}  // namespace delphi_edm4hep::tof_fdst
