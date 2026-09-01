// SdstPaExtrasWriter — pass-1 implementation.
//
// Per-track sDST PA modules emitted as ParticleID rows linked to their
// particle. PA.PHOT (30), PA.ODHI (29) and PA.MUFI (27) are short lists of
// scalars passed through from Q(l+2 ..), with the bank length from IPHREQ(1)
// bounding the read. PA.HCRO (34) and PA.HCMU (35) are decoded instead: both
// pack a count into a word and HCRO packs its per-plane hit pattern.

#include "delphi_edm4hep/Pid/SdstPaExtras.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace ph = phdst;

namespace delphi_edm4hep::sdst_pa_extras {

namespace {
constexpr std::int32_t kAlgoPhot = 30;
constexpr std::int32_t kAlgoOdhi = 29;
constexpr std::int32_t kAlgoMufi = 27;
constexpr std::int32_t kAlgoHcro = 34;
constexpr std::int32_t kAlgoHcmu = 35;
constexpr int          kMaxParams = 7;
constexpr int          kMufiHeader = 17;   // Q(+2..+18) fixed header words
constexpr std::int32_t kAlgoMric = 6;
constexpr int          kHcroMuonWords = 5; // HATMUID block, Q(+9..+13)
constexpr float        kCm2Mm = 10.f;
constexpr float        kCm2Mm2 = 100.f;   // for a variance in cm^2
constexpr float        kNotMeasured = std::numeric_limits<float>::quiet_NaN();

int nint(float x) { return static_cast<int>(std::lround(x)); }
}  // namespace

void SdstPaExtrasWriter::emit()
{
  edm4hep::ParticleIDCollection photCol;
  edm4hep::ParticleIDCollection odhiCol;
  edm4hep::ParticleIDCollection mufiCol;
  edm4hep::ParticleIDCollection hcroCol;
  edm4hep::ParticleIDCollection hcroMuCol;
  edm4hep::ParticleIDCollection hcmuCol;
  edm4hep::ParticleIDCollection mricCol;

  auto store = [&] {
    put(std::move(photCol),   "PHOT", "PhotonID",      Provenance::Transcribed);
    put(std::move(odhiCol),   "ODHI", "OuterDetector", Provenance::Transcribed);
    put(std::move(mufiCol),   "MUFI", "RefitMuon",     Provenance::Transcribed);
    put(std::move(hcroCol),   "HCRO", "HitPattern",    Provenance::Transcribed);
    put(std::move(hcroMuCol), "HCRO", "MuonTag",       Provenance::Transcribed);
    put(std::move(hcmuCol),   "HCMU", "MuonID",        Provenance::Transcribed);
    put(std::move(mricCol),   "MRIC", "RichExtrapolation", Provenance::Transcribed);
  };

  if (!ctx_.tracking) {
    store();
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

    // PA.HCRO: hadron-calorimeter read-out. Word 2 packs the module length
    // and the total tube count as length + 1000*NHIT. Words 5..8 carry the
    // hits per calorimeter plane, five planes to a word in base 16 with
    // plane 1 in the most significant digit. Words 9..13 are the HATMUID
    // muon block and exist only when the module length is 13.
    if (const int lhcro = pawalk::lphpa("HCRO", lpa); lhcro > 0) {
      const int packed = nint(ph::Q(lhcro + 2));
      auto pid = hcroCol.create();
      pid.setAlgorithmType(kAlgoHcro);
      pid.addToParameters(static_cast<float>(packed / 1000));
      pid.addToParameters(ph::Q(lhcro + 3) * kCm2Mm);
      pid.addToParameters(ph::Q(lhcro + 4) * kCm2Mm);
      for (int w = 0; w < 4; ++w) {
        const int word = nint(ph::Q(lhcro + 5 + w));
        for (int digit = 4; digit >= 0; --digit) {
          pid.addToParameters(static_cast<float>((word >> (4 * digit)) & 0xF));
        }
      }
      pid.setParticle(tracking.particle_handles[p_idx]);

      if (packed % 1000 >= 13) {
        auto mu = hcroMuCol.create();
        mu.setAlgorithmType(kAlgoHcro);
        for (int k = 0; k < kHcroMuonWords; ++k) {
          mu.addToParameters(ph::Q(lhcro + 9 + k));
        }
        mu.setParticle(tracking.particle_handles[p_idx]);
      }
    }

    // PA.HCMU: muon tag derived from that pattern. Word 2 packs the module
    // length and the identification level as length + 1000*ID.
    if (const int lhcmu = pawalk::lphpa("HCMU", lpa); lhcmu > 0) {
      auto pid = hcmuCol.create();
      pid.setAlgorithmType(kAlgoHcmu);
      pid.addToParameters(static_cast<float>(nint(ph::Q(lhcmu + 2)) / 1000));
      pid.addToParameters(ph::Q(lhcmu + 3) * kCm2Mm);
      pid.addToParameters(ph::Q(lhcmu + 4) * kCm2Mm);
      pid.setParticle(tracking.particle_handles[p_idx]);
    }

    // PA.MRIC — the RICH measurement PXDST records for this track: the
    // refractive index of each radiator that fired, where the track entered
    // the RICH and with what uncertainty, and how many ionization hits it
    // left along the way. Distinct from the RICH values in PA.HAID, which is
    // where SKELANA takes its Cherenkov angles from.
    //
    // Coordinates 1 and 2 are R*phi and z for a barrel track and x and y for
    // a forward one; the module carries no flag saying which, so decide from
    // the track's polar angle. The angles, 1/p and the variances mean the
    // same either way.
    if (const int lmric = pawalk::lphpa("MRIC", lpa); lmric > 0) {
      // A radiator contributes four words led by its refractive index, or a
      // single zero word when it did not fire.
      float index[2] = {kNotMeasured, kNotMeasured};
      int w = 2;
      for (int radiator = 0; radiator < 2; ++radiator) {
        const float n = ph::Q(lmric + w);
        if (n == 0.f) { ++w; continue; }
        index[radiator] = n;
        w += 4;
      }
      const int tail = lmric + w - 1;   // tail word k is at tail + k

      auto pid = mricCol.create();
      pid.setAlgorithmType(kAlgoMric);
      pid.addToParameters(index[0]);
      pid.addToParameters(index[1]);
      pid.addToParameters(ph::Q(tail + 1) * kCm2Mm);
      pid.addToParameters(ph::Q(tail + 2) * kCm2Mm);
      pid.addToParameters(ph::Q(tail + 3));
      pid.addToParameters(ph::Q(tail + 4));
      pid.addToParameters(ph::Q(tail + 5));
      pid.addToParameters(ph::Q(tail + 6) * kCm2Mm2);
      pid.addToParameters(ph::Q(tail + 7) * kCm2Mm2);
      pid.addToParameters(ph::Q(tail + 8));
      pid.addToParameters(ph::Q(tail + 9));
      pid.addToParameters(ph::Q(tail + 10));
      pid.addToParameters(ph::Q(tail + 17));
      pid.setParticle(tracking.particle_handles[p_idx]);
    }
  });

  store();
}

}  // namespace delphi_edm4hep::sdst_pa_extras
