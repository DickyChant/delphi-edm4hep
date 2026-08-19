// Btag.cpp — b-tagging domain implementation.
//
// Reads PSCBTG (event/hemisphere probabilities) and, when AABTAG was
// actually rerun, the AAMAIN / AAMNVX commons (per-track impact
// parameters, per-track probabilities, VD quality, and AABTAG's own
// primary vertex).

#include "delphi_edm4hep/Btag/Btag.h"

#include "delphi_edm4hep/internal/AabtagCommons.h"
#include "delphi_edm4hep/internal/PaWalk.h"

#include "skelana/pscbtg.hpp"

#include <edm4hep/VertexCollection.h>
#include <podio/UserDataCollection.h>

#include <algorithm>
#include <cstdint>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

namespace sk = skelana;
namespace aa = delphi_edm4hep::aabtag;

namespace delphi_edm4hep::btag {

namespace {

constexpr double kCm2Mm    = 10.0;
constexpr float  kCm2Mm2_f = static_cast<float>(kCm2Mm * kCm2Mm);
constexpr float  kNaN      = std::numeric_limits<float>::quiet_NaN();

// algorithmType tag for AABTAG's primary vertex. Distinct from the values
// Vertex.cpp uses (0 primary, 1 secondary, 2 beamspot, 4 simulation,
// 10 V0, 11 photon conversion) so the two PVs are never confused.
constexpr int kAlgoBtagPV = 3;

// PSFBTG pre-fills the PSCBTG probabilities with 2.0 (CALL VFILL(...,2.))
// and only overwrites them if the beamspot is usable. 2.0 is therefore a
// "not computed" marker, not a probability -- map it to NaN so a consumer
// that forgets to check cannot silently average it in.
float prob(float v) { return (v >= 1.999f) ? kNaN : v; }

}  // namespace

void BtagWriter::emit()
{
  // Record the configuration unconditionally, so a consumer can tell a
  // b-tag-PV file from a DELANA-PV file (and a no-b-tag file from one
  // where AABTAG simply produced nothing) without guessing from which
  // collections happen to be present.
  putParameter("BTAGCFG", "Mode",
               std::string(mode_ == BtagMode::Off    ? "off"
                         : mode_ == BtagMode::Bank   ? "bank"
                                                     : "recalc"));
  putParameter("BTAGCFG", "Recalculated", recalculated() ? 1 : 0);

  if (mode_ == BtagMode::Off) return;

  const std::string_view bank = mnemonic();

  // ---- Event / hemisphere probabilities (PSCBTG; both modes) ----------
  // Index order within each triplet is (hemisphere 1, hemisphere 2, whole
  // event), matching QBTPRN/QBTPRP/QBTPRS(1..3).
  putParameter(bank, "ProbNegIP",
               std::vector<float>{prob(sk::QBTPRN(1)), prob(sk::QBTPRN(2)),
                                  prob(sk::QBTPRN(3))});
  putParameter(bank, "ProbPosIP",
               std::vector<float>{prob(sk::QBTPRP(1)), prob(sk::QBTPRP(2)),
                                  prob(sk::QBTPRP(3))});
  putParameter(bank, "ProbAllIP",
               std::vector<float>{prob(sk::QBTPRS(1)), prob(sk::QBTPRS(2)),
                                  prob(sk::QBTPRS(3))});
  putParameter(bank, "ThrustAxis",
               std::vector<float>{sk::QBTTHR(1), sk::QBTTHR(2), sk::QBTTHR(3)});
  // QBTTHR(4) is the thrust VALUE, not an axis component. (delphi-nanoaod
  // drops it; we keep it -- it is free and the axis alone is not enough to
  // reproduce a thrust-based hemisphere split.)
  putParameter(bank, "ThrustValue", prob(sk::QBTTHR(4)));

  if (!recalculated()) return;

  // ---- AABTAG primary vertex (AAMNVX) --------------------------------
  // Emitted as its own collection rather than replacing the DELANA PV.
  // With IFLPVT = Keep (the default) SKELANA never overwrites QVTX, so a
  // consumer gets both vertices and picks; nothing is destroyed.
  edm4hep::VertexCollection btagPv;
  {
    auto pv = btagPv.create();
    pv.setPrimary(true);
    pv.setAlgorithmType(kAlgoBtagPV);
    pv.setPosition({static_cast<float>(aa::POSVX(1) * kCm2Mm),
                    static_cast<float>(aa::POSVX(2) * kCm2Mm),
                    static_cast<float>(aa::POSVX(3) * kCm2Mm)});
    pv.setChi2(aa::CHI2VX());
    pv.setNdf(aa::NDOFVX());
    pv.setCovMatrix({aa::COVVX(1) * kCm2Mm2_f, aa::COVVX(2) * kCm2Mm2_f,
                     aa::COVVX(3) * kCm2Mm2_f, aa::COVVX(4) * kCm2Mm2_f,
                     aa::COVVX(5) * kCm2Mm2_f, aa::COVVX(6) * kCm2Mm2_f});
  }
  put(std::move(btagPv), bank, "PrimaryVertex");

  // ---- Per-track quantities (AAMAIN + AAMNVX) ------------------------
  // AABTAG's arrays are dimensioned kMaxTracks; a busier event is
  // truncated by AABTAG itself. Clamp and record the fact rather than
  // reading past the end or pretending the coverage was complete.
  const int ntrk_raw = aa::NTRK();
  const int ntrk     = std::clamp(ntrk_raw, 0, aa::kMaxTracks);
  putParameter(bank, "NTracks",         ntrk);
  putParameter(bank, "NTracksAttached", aa::NATTVX());
  putParameter(bank, "Truncated",       ntrk_raw > aa::kMaxTracks ? 1 : 0);

  // lpa -> PA-walk index, so IADTR (a ZEBRA L-address) can be resolved to
  // the Particle the Tracking domain emitted for that PA.
  std::unordered_map<int, int> lpa_to_pa;
  pawalk::forEachPA([&](int lpa, int paIdx) { lpa_to_pa.emplace(lpa, paIdx); });

  const std::vector<int>* pa_to_particle =
      ctx_.tracking ? &ctx_.tracking->pa_to_particle : nullptr;

  podio::UserDataCollection<std::int32_t> particleIdx;
  podio::UserDataCollection<float>        impRPhi, impRPhiErr;
  podio::UserDataCollection<float>        impZ,    impZErr;
  podio::UserDataCollection<float>        probRPhi, probZ;
  podio::UserDataCollection<std::int32_t> usedForTag, attachedToPv;
  podio::UserDataCollection<std::int32_t> nHitsRPhi, nHitsZ;
  podio::UserDataCollection<std::int32_t> nLayersRPhi, nLayersZ;
  podio::UserDataCollection<float>        chi2Vd, chi2Pv, momentum;

  for (int i = 1; i <= ntrk; ++i) {
    int p_idx = -1;
    if (pa_to_particle) {
      if (auto it = lpa_to_pa.find(aa::IADTR(i)); it != lpa_to_pa.end()) {
        const int paIdx = it->second;
        if (paIdx >= 0 && paIdx < static_cast<int>(pa_to_particle->size())) {
          p_idx = (*pa_to_particle)[paIdx];
        }
      }
    }
    particleIdx.push_back(p_idx);

    // PARIMP is the SIGNED r-phi impact parameter wrt AABTAG's POSVX, in
    // DELPHI cm and DELPHI sign convention -- NOT the LCIO D0 sign used by
    // the Track collections. Converted to mm, sign left as AABTAG set it,
    // because the sign is the physics here (the negative-IP side is the
    // mistag control sample). Do not mix with sDST_TRAC_d0PV or
    // sDST_PV_trackD0PV; see Vertex.cpp / Tracking.cpp on those.
    impRPhi   .push_back(static_cast<float>(aa::PARIMP(i) * kCm2Mm));
    impRPhiErr.push_back(static_cast<float>(aa::SIGIMP(i) * kCm2Mm));
    impZ      .push_back(static_cast<float>(aa::EZED  (i) * kCm2Mm));
    impZErr   .push_back(static_cast<float>(aa::SIGZED(i) * kCm2Mm));

    // AATPRB leaves these at 1.0 for tracks it could not use.
    probRPhi.push_back(aa::TRPR (i));
    probZ   .push_back(aa::TRPRZ(i));

    usedForTag  .push_back(aa::ISRT(i));      // 0 = not used, > 0 = used
    attachedToPv.push_back(aa::INMVX(i) ? 1 : 0);
    nHitsRPhi   .push_back(aa::NVDP (i));
    nHitsZ      .push_back(aa::NVDPZ(i));
    nLayersRPhi .push_back(aa::NLAY (i));
    nLayersZ    .push_back(aa::NLAYZ(i));
    chi2Vd      .push_back(aa::CHI2VD(i));
    chi2Pv      .push_back(aa::CHI2TR(i));
    momentum    .push_back(aa::PMOM  (i));
  }

  put(std::move(particleIdx),  bank, "Tracks_ParticleIndex");
  put(std::move(impRPhi),      bank, "Tracks_ImpactParRPhi");
  put(std::move(impRPhiErr),   bank, "Tracks_ImpactParRPhiError");
  put(std::move(impZ),         bank, "Tracks_ImpactParZ");
  put(std::move(impZErr),      bank, "Tracks_ImpactParZError");
  put(std::move(probRPhi),     bank, "Tracks_ProbRPhi");
  put(std::move(probZ),        bank, "Tracks_ProbZ");
  put(std::move(usedForTag),   bank, "Tracks_UsedForTag");
  put(std::move(attachedToPv), bank, "Tracks_AttachedToPV");
  put(std::move(nHitsRPhi),    bank, "Tracks_NVDHitsRPhi");
  put(std::move(nHitsZ),       bank, "Tracks_NVDHitsZ");
  put(std::move(nLayersRPhi),  bank, "Tracks_NVDLayersRPhi");
  put(std::move(nLayersZ),     bank, "Tracks_NVDLayersZ");
  put(std::move(chi2Vd),       bank, "Tracks_Chi2VD");
  put(std::move(chi2Pv),       bank, "Tracks_Chi2PV");
  put(std::move(momentum),     bank, "Tracks_Momentum");
}

}  // namespace delphi_edm4hep::btag
