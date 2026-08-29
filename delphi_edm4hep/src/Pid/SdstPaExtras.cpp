// SdstPaExtrasWriter — pass-1 implementation.
//
// PA.PHOT (label 30) and PA.ODHI (label 29) are variable-length sDST
// modules whose content is a short list of per-track ID / hit scalars.
// We pass through Q(l+2 ..) up to a 7-word cap, with the bank length
// from IPHREQ(1) bounding the read.

#include "delphi_edm4hep/Pid/SdstPaExtras.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>

#include <algorithm>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::sdst_pa_extras {

namespace {
constexpr std::int32_t kAlgoPhot = 30;
constexpr std::int32_t kAlgoOdhi = 29;
constexpr std::int32_t kAlgoMufi = 27;
constexpr int          kMaxParams = 7;
constexpr int          kMufiHeader = 17;   // Q(+2..+18) fixed header words
}  // namespace

void SdstPaExtrasWriter::emit()
{
  edm4hep::ParticleIDCollection photCol;
  edm4hep::ParticleIDCollection odhiCol;
  edm4hep::ParticleIDCollection mufiCol;

  if (!ctx_.tracking) {
    put(std::move(photCol), "PHOT", "PhotonID", Provenance::Transcribed);
    put(std::move(odhiCol), "ODHI", "OuterDetector", Provenance::Transcribed);
    put(std::move(mufiCol), "MUFI", "RefitMuon", Provenance::Transcribed);
    return;
  }
  const auto& tracking = *ctx_.tracking;

  // Emit Q(l+2 ..) up to `cap` words, bounded by the bank length.
  auto emitParams = [&](edm4hep::MutableParticleID pid, int lbank, int cap) {
    const int blen = pawalk::iphreq(1);          // words in this sub-bank
    const int n = std::min(cap, std::max(0, blen - 1));   // skip label
    for (int k = 0; k < n; ++k) pid.addToParameters(ph::Q(lbank + 2 + k));
  };

  auto particleAt = [&](int paIdx) -> int {
    if (paIdx < 0 || paIdx >= static_cast<int>(tracking.pa_to_particle.size()))
      return -1;
    return tracking.pa_to_particle[paIdx];
  };

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int p_idx = particleAt(paIdx);
    if (p_idx < 0) return;

    if (const int lphot = pawalk::lphpa("PHOT", lpa); lphot > 0) {
      auto pid = photCol.create();
      pid.setAlgorithmType(kAlgoPhot);
      emitParams(pid, lphot, kMaxParams);
      pid.setParticle(tracking.particle_handles[p_idx]);
    }

    if (const int lodhi = pawalk::lphpa("ODHI", lpa); lodhi > 0) {
      auto pid = odhiCol.create();
      pid.setAlgorithmType(kAlgoOdhi);
      emitParams(pid, lodhi, kMaxParams);
      pid.setParticle(tracking.particle_handles[p_idx]);
    }

    // PA.MUFI (refitted-MU): emit the fixed header (det, nlay, ndf, chi2,
    // extrap pos/dir + errors). Variable per-layer blocks not surfaced.
    if (const int lmufi = pawalk::lphpa("MUFI", lpa); lmufi > 0) {
      auto pid = mufiCol.create();
      pid.setAlgorithmType(kAlgoMufi);
      emitParams(pid, lmufi, kMufiHeader);
      pid.setParticle(tracking.particle_handles[p_idx]);
    }
  });

  put(std::move(photCol), "PHOT", "PhotonID", Provenance::Transcribed);
  put(std::move(odhiCol), "ODHI", "OuterDetector", Provenance::Transcribed);
  put(std::move(mufiCol), "MUFI", "RefitMuon", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::sdst_pa_extras
