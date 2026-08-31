// PaPidExtrasWriter — implementation. Runs in both passes.
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

#include "delphi_edm4hep/Pid/PaPidExtras.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>

#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::pa_pid_extras {

namespace {
constexpr std::int32_t kAlgoMu   = 4;
constexpr std::int32_t kAlgoEl   = 5;
constexpr std::int32_t kAlgoTdid = 17;
}  // namespace

void PaPidExtrasWriter::emit()
{
  edm4hep::ParticleIDCollection muCol;
  edm4hep::ParticleIDCollection elCol;
  edm4hep::ParticleIDCollection tdidCol;


  pawalk::forEachPA([&](int lpa, int paIdx) {
    const auto particle = particleForPa(paIdx);
    if (!particle) return;

    // ---- PA.MU (muon-chamber refit summary) ----
    if (const int lmu = pawalk::lphpa("MU", lpa); lmu > 0) {
      auto pid = muCol.create();
      pid.setAlgorithmType(kAlgoMu);
      for (int off = 2; off <= 13; ++off) pid.addToParameters(ph::Q(lmu + off));
      pid.setParticle(*particle);
    }

    // ---- PA.EL (electron extra-module header) ----
    if (const int lel = pawalk::lphpa("EL", lpa); lel > 0) {
      const int det    = static_cast<int>(std::lround(ph::Q(lel + 2))) / 100;
      const int nshow  = static_cast<int>(std::lround(ph::Q(lel + 3))) / 10;
      auto pid = elCol.create();
      pid.setAlgorithmType(kAlgoEl);
      pid.addToParameters(static_cast<float>(det));
      pid.addToParameters(static_cast<float>(nshow));
      pid.setParticle(*particle);
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
      pid.setParticle(*particle);
    }
  });

  put(std::move(muCol),   "MU",   "MuonChambers", Provenance::Transcribed);
  put(std::move(elCol),   "EL",   "ElectronExtra", Provenance::Transcribed);
  put(std::move(tdidCol), "TDID", "DriftCalib", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::pa_pid_extras
