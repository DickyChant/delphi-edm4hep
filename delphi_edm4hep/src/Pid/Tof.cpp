// TofWriter — implementation. Runs in both passes.
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

#include "delphi_edm4hep/Pid/Tof.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::tof {

namespace {
constexpr std::int32_t kAlgoTof = 5;
}

void TofWriter::emit()
{
  edm4hep::ParticleIDCollection col;

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int ltof = pawalk::lphpa("TOF", lpa);
    if (ltof <= 0) return;
    const auto particle = particleForPa(paIdx);
    if (!particle) return;

    const float time_ns  = ph::Q(ltof + 6);
    const float sigma_ns = ph::Q(ltof + 7);

    auto pid = col.create();
    pid.setAlgorithmType(kAlgoTof);
    pid.addToParameters(time_ns);
    pid.addToParameters(sigma_ns);
    pid.setParticle(*particle);
  });

  put(std::move(col), "TOF", "TimeOfFlight", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::tof
