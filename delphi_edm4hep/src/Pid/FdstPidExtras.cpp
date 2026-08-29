// FdstPidExtrasWriter — pass-2 implementation.
//
// Bank layouts (verified against the legacy delphi_fdst_pad_dump readers):
//
//   PA.MU (label 4):
//     +2  detector id (14=MUB, 17=MUS, 30=MUF)
//     +3  nlay        +4  ndof        +5  chi2 (global)
//     +6  x_first     +7  y_first     +8  hit_pattern (MUB bitmask)
//     +9  chi2_alone  +10 x_extrap    +11 y_extrap
//     +12 theta_extrap +13 phi_extrap
//
//   PA.EL (label 5):  header only
//     +2  packed = shower_len + 100*detector_id  -> det = Q(+2)/100
//     +3  packed = shower_num + 10*length        -> nshow = Q(+3)/10
//
//   PA.TDID (label 17):  fixed 26 words
//     +2  jet_sector (signed)
//     +3..+26  24 raw drift times -> aggregate (n_valid>0, sum)

#include "delphi_edm4hep/Pid/FdstPidExtras.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::fdst_pid_extras {

namespace {
constexpr std::int32_t kAlgoMu   = 4;
constexpr std::int32_t kAlgoEl   = 5;
constexpr std::int32_t kAlgoTdid = 17;
}  // namespace

void FdstPidExtrasWriter::emit()
{
  edm4hep::ParticleIDCollection muCol;
  edm4hep::ParticleIDCollection elCol;
  edm4hep::ParticleIDCollection tdidCol;

  if (!ctx_.fdst_pa_to_sdst_particle) {
    put(std::move(muCol),   "MU",   "MuonChambers", Provenance::Transcribed);
    put(std::move(elCol),   "EL",   "ElectronExtra", Provenance::Transcribed);
    put(std::move(tdidCol), "TDID", "DriftCalib", Provenance::Transcribed);
    return;
  }
  const auto& pa_to_particle = *ctx_.fdst_pa_to_sdst_particle;
  // fDST_MAIN_Particles (created by MainHybrid, which runs before this writer;
  // 1:1 with sDST_MAIN_Particles by clone index).
  const auto& fdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>("fDST_MAIN_Particles");

  auto matched_particle = [&](int paIdx) -> int {
    if (paIdx >= static_cast<int>(pa_to_particle.size())) return -1;
    const int p = pa_to_particle[paIdx];
    if (p < 0 || p >= static_cast<int>(fdst_particles.size())) return -1;
    return p;
  };

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int particle_idx = matched_particle(paIdx);
    if (particle_idx < 0) return;   // unmatched fDST PA, drop

    // ---- PA.MU (muon-chamber refit summary) ----
    if (const int lmu = pawalk::lphpa("MU", lpa); lmu > 0) {
      auto pid = muCol.create();
      pid.setAlgorithmType(kAlgoMu);
      for (int off = 2; off <= 13; ++off) pid.addToParameters(ph::Q(lmu + off));
      pid.setParticle(fdst_particles[particle_idx]);
    }

    // ---- PA.EL (electron extra-module header) ----
    if (const int lel = pawalk::lphpa("EL", lpa); lel > 0) {
      const int det    = static_cast<int>(std::lround(ph::Q(lel + 2))) / 100;
      const int nshow  = static_cast<int>(std::lround(ph::Q(lel + 3))) / 10;
      auto pid = elCol.create();
      pid.setAlgorithmType(kAlgoEl);
      pid.addToParameters(static_cast<float>(det));
      pid.addToParameters(static_cast<float>(nshow));
      pid.setParticle(fdst_particles[particle_idx]);
    }

    // ---- PA.TDID (ID drift-time calibration) ----
    if (const int ltdid = pawalk::lphpa("TDID", lpa); ltdid > 0) {
      const float jet_sector = ph::Q(ltdid + 2);
      int   n_valid = 0;
      float drift_sum = 0.f;
      for (int k = 0; k < 24; ++k) {
        const float d = ph::Q(ltdid + 3 + k);
        if (d > 0.f) { ++n_valid; drift_sum += d; }
      }
      auto pid = tdidCol.create();
      pid.setAlgorithmType(kAlgoTdid);
      pid.addToParameters(jet_sector);
      pid.addToParameters(static_cast<float>(n_valid));
      pid.addToParameters(drift_sum);
      pid.setParticle(fdst_particles[particle_idx]);
    }
  });

  put(std::move(muCol),   "MU",   "MuonChambers", Provenance::Transcribed);
  put(std::move(elCol),   "EL",   "ElectronExtra", Provenance::Transcribed);
  put(std::move(tdidCol), "TDID", "DriftCalib", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::fdst_pid_extras
