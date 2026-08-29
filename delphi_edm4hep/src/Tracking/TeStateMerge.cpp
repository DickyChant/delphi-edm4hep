// TeStateMergeWriter — pass-2 implementation.
//
// Bank format decoding (descriptor, variable-length cov, ndf/chi2/length)
// is handled by te_bank::decode; see TeBank.h for the layout reference.
//
// Sign convention note: DELPHI stores 1/R with sign OPPOSITE to charge.
// To keep TE-state omega consistent with the existing sDST_TRAC_Tracks
// AtIP omega (which is invR_dp/10, also opposite-of-charge), we pass
// NEGATED charge_signed to BasisConversion::teToHelix. The resulting
// omega has the same sign convention as the AtIP state.

#include "delphi_edm4hep/Tracking/TeStateMerge.h"

#include "delphi_edm4hep/Helix.h"
#include "delphi_edm4hep/TeBank.h"
#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/Constants.h>
#include <edm4hep/MutableParticleID.h>
#include <edm4hep/MutableTrack.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <edm4hep/TrackCollection.h>
#include <edm4hep/TrackState.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <string_view>
#include <vector>

namespace ph = phdst;

namespace delphi_edm4hep::te_merge {

namespace {

constexpr float kCm2Mm = 10.0f;

// The TE PA-sub-bank names + their DST module-label IDs. TERF (21,
// "TE from Forward RICH") shares the identical TE bank layout decoded by
// te_bank::decode, so it is handled exactly like the inner-five: one
// TrackState (location=Other) + one FitQuality companion (algType=21).
// Ordered ascending by label so the TrackState ordering stays monotonic.
struct TeDetector { const char* name; std::int32_t label; };
constexpr std::array<TeDetector, 6> kTeDetectors{{
  {"TEID", 12},
  {"TETP", 13},
  {"TEOD", 14},
  {"TEFA", 15},
  {"TEFB", 16},
  {"TERF", 21},
}};

// Clone the scalar / vector fields of a Track (chi2, ndf, etc.) and
// its existing TrackStates into the output Track. Cross-collection
// relations (hits, tracks, dxQuantities) are skipped — they're empty
// on our sDST output and not yet wired for pass-2.
void cloneTrackShallow(edm4hep::MutableTrack dst,
                       const edm4hep::Track& src) {
  dst.setType   (src.getType());
  dst.setChi2   (src.getChi2());
  dst.setNdf    (src.getNdf());
  dst.setNholes (src.getNholes());
  for (auto n : src.getSubdetectorHitNumbers())  dst.addToSubdetectorHitNumbers(n);
  for (auto n : src.getSubdetectorHoleNumbers()) dst.addToSubdetectorHoleNumbers(n);
  for (auto ts : src.getTrackStates())           dst.addToTrackStates(ts);
}

}  // namespace

void TeStateMergeWriter::emit()
{
  edm4hep::TrackCollection      trk_out;
  edm4hep::ParticleIDCollection fq_out;

  if (!ctx_.fdst_pa_to_sdst_track || !ctx_.fdst_pa_to_sdst_particle) {
    put(std::move(trk_out), "TRAC", "Tracks", Provenance::Derived);
    put(std::move(fq_out),  "TRAC", "Tracks_FitQuality", Provenance::Transcribed);
    return;
  }
  const auto& pa_to_track    = *ctx_.fdst_pa_to_sdst_track;
  const auto& pa_to_particle = *ctx_.fdst_pa_to_sdst_particle;
  const auto& sdst_tracks =
    frame_.get<edm4hep::TrackCollection>("sDST_TRAC_Tracks");
  const auto& sdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>("sDST_MAIN_Particles");

  // B field from the intermediate's Frame parameters. Falls back to 0
  // (which yields zero omega) if missing.
  const auto B_param = frame_.getParameter<float>("sDST_EVT_BField");
  const double B_tesla = static_cast<double>(B_param.value_or(0.f));

  // First pass: record lpa per paIdx so the per-Track loop below can
  // find the bank address for each fDST PA matched to a given sDST
  // Track (without re-walking the PA chain per track).
  std::vector<int> lpa_by_pa;
  pawalk::forEachPA([&](int lpa, int paIdx) {
    if (paIdx >= static_cast<int>(lpa_by_pa.size())) {
      lpa_by_pa.resize(static_cast<std::size_t>(paIdx + 1), 0);
    }
    lpa_by_pa[paIdx] = lpa;
  });

  // Inverse map: sDST Track idx -> list of fDST paIdx's matching it.
  // (Usually 1:1 but we tolerate many-to-1 in case the perigee match
  // happens to resolve multiple fDST PAs to the same sDST Track.)
  std::vector<std::vector<int>> track_to_pas(sdst_tracks.size());
  for (int paIdx = 0; paIdx < static_cast<int>(pa_to_track.size()); ++paIdx) {
    const int t = pa_to_track[paIdx];
    if (t >= 0 && t < static_cast<int>(sdst_tracks.size())) {
      track_to_pas[t].push_back(paIdx);
    }
  }

  // Build each output Track in sDST order. Clone the sDST scalars +
  // existing AtIP TrackState, then append per-TE TrackStates from
  // the matched fDST PA(s).
  for (std::size_t i = 0; i < sdst_tracks.size(); ++i) {
    auto out = trk_out.create();
    cloneTrackShallow(out, sdst_tracks[i]);

    for (int paIdx : track_to_pas[i]) {
      const int lpa = lpa_by_pa[paIdx];
      if (lpa <= 0) continue;

      // Charge for omega sign. PA.MAIN+8 is the charge code; we negate
      // so Helix::fromTrackElement's "standard" omega formula yields the
      // DELPHI sign convention (opposite to charge) that the sDST AtIP
      // state already uses.
      const int lmain = pawalk::lphpa("MAIN", lpa);
      int charge_signed = 0;
      if (lmain > 0) {
        const int code = static_cast<int>(std::lround(ph::Q(lmain + 8)));
        if      (code == 1) charge_signed = +1;
        else if (code == 2) charge_signed = -1;
      }
      const int conv_charge = -charge_signed;   // DELPHI sign convention

      // AtFirstHit TrackState (PA.MAIN+22..+24 = X/Y/Z of first measured
      // point on the track, cm). Helix invariants (omega, tanLambda) are
      // copied from the existing AtIP state; phi is approximated by the
      // AtIP phi (true value would require helix propagation through
      // arc-length to this point — out of scope here). D0, Z0, time set
      // to 0 by construction (track passes through the reference point).
      // Cov is zero — Q(LMAIN+25) is the chi^2 of the TK fit, not a
      // per-state covariance.
      if (lmain > 0) {
        const float fx = ph::Q(lmain + 22);
        const float fy = ph::Q(lmain + 23);
        const float fz = ph::Q(lmain + 24);
        // Find the AtIP state on the cloned output to source omega/phi/tanLambda.
        edm4hep::TrackState fh{};
        fh.location = edm4hep::TrackState::AtFirstHit;
        for (auto ts : out.getTrackStates()) {
          if (ts.location == edm4hep::TrackState::AtIP) {
            fh.phi       = ts.phi;
            fh.omega     = ts.omega;
            fh.tanLambda = ts.tanLambda;
            break;
          }
        }
        fh.D0   = 0.f;
        fh.Z0   = 0.f;
        fh.time = 0.f;
        fh.referencePoint = {
          fx * static_cast<float>(kCm2Mm),
          fy * static_cast<float>(kCm2Mm),
          fz * static_cast<float>(kCm2Mm),
        };
        out.addToTrackStates(fh);
      }

      // Walk the five TE sub-banks for this PA.
      for (const auto& det : kTeDetectors) {
        const int lte = pawalk::lphpa(det.name, lpa);
        if (lte <= 0) continue;
        const int blen = pawalk::iphreq(1);

        const double c1    = ph::Q(lte + 3);
        const double c2    = ph::Q(lte + 4);
        const double c3    = ph::Q(lte + 5);
        const double theta = ph::Q(lte + 6);
        const double phi   = ph::Q(lte + 7);
        const double invP  = ph::Q(lte + 8);

        // Decode the descriptor + variable-length cov + ndf/chi2/length.
        // For TEID multi-TER stacks (blen != 11+m), te.ok=false; we still
        // emit a TrackState with the cov from the first TER's measured
        // fields but skip ndf/chi2/length (their offsets are ambiguous).
        const auto te = te_bank::decode(lte, blen);
        // te.invPt (descriptor bit 11) tells Helix whether `invP` is 1/|p_T|
        // or 1/|p| so it forms omega = transverse curvature correctly.
        const auto helix = Helix::fromTrackElement(
          c1, c2, c3, theta, phi, invP, te.invPt, te.cov, conv_charge, B_tesla);
        out.addToTrackStates(helix.toTrackState(edm4hep::TrackState::AtOther));

        // FitQuality companion ParticleID. Parameter layout:
        //   [0] charge_signed (+1/-1/0)
        //   [1] B_tesla
        //   [2] descriptor (raw int from bank +2)
        //   [3] ndf
        //   [4] chi^2
        //   [5] length (cm)
        //   [6] n_cov (= m, number of stored cov entries for this TER)
        //
        // n_cov also serves as a "well-formed" flag: 0 → first TER had
        // no measured fields OR blen mismatch (multi-TER stack); in that
        // case ndf/chi2/length are emitted as 0 to avoid reading garbage.
        const int particle_idx =
          (paIdx < static_cast<int>(pa_to_particle.size()))
            ? pa_to_particle[paIdx] : -1;
        if (particle_idx >= 0 &&
            particle_idx < static_cast<int>(sdst_particles.size())) {
          auto fq = fq_out.create();
          fq.setAlgorithmType(det.label);
          fq.addToParameters(static_cast<float>(charge_signed));
          fq.addToParameters(static_cast<float>(B_tesla));
          fq.addToParameters(static_cast<float>(te.descriptor));
          fq.addToParameters(te.ndf);
          fq.addToParameters(te.chi2);
          fq.addToParameters(te.length);
          fq.addToParameters(static_cast<float>(te.m_cov_entries));
          // Links to sDST_MAIN_Particles (pass-1), not fDST: TeStateMerge MUST
          // run before MainHybrid (it produces the fDST_TRAC_Tracks MainHybrid
          // consumes), so fDST_MAIN_Particles does not exist yet. The two are
          // 1:1 by clone index, so this resolves to the same logical particle.
          // (The pure-fDST PID writers TOF/MTPC/MU/EL/TDID were moved after
          // MainHybrid so they link fDST_MAIN_Particles directly.)
          fq.setParticle(sdst_particles[particle_idx]);
        }
      }
    }
  }

  put(std::move(trk_out), "TRAC", "Tracks", Provenance::Derived);
  put(std::move(fq_out),  "TRAC", "Tracks_FitQuality", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::te_merge
