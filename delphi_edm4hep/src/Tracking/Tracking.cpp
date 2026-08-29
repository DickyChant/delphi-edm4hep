// Tracking domain — implementation S3 (pass-1).
//
// Walks the PA chain (LDTOP-1 -> per-PV -> per-PA), emitting:
//   <tag>_TRAC_Tracks       (Track + TrackState[AtIP] + 5x5 helix-basis cov)
//   <tag>_MAIN_Particles    (charged + neutral; 4-mom from sk::VECP)
//   <tag>_VECP_LVLOCK       (UserData int32 parallel; -1 for neutrals)
//   <tag>_TRAC_d0PV / z0PV / d0BS  (UserData float; from sk::QTRAC(38..40))
//
// No shape moments, no sigma calibration, no perigee-momentum fallback —
// bank-truth values only (those custom operations are intentionally
// dropped).

#include "delphi_edm4hep/Tracking/Tracking.h"

#include "delphi_edm4hep/Helix.h"
#include "delphi_edm4hep/internal/PaWalk.h"
#include "skelana/pscvec.hpp"
#include "skelana/psctra.hpp"

#include <edm4hep/ReconstructedParticleCollection.h>
#include <edm4hep/TrackCollection.h>
#include <edm4hep/TrackState.h>
#include <podio/Frame.h>
#include <podio/UserDataCollection.h>

#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>

namespace ph = phdst;
namespace sk = skelana;

namespace delphi_edm4hep::tracking {

namespace {

// The DELPHI perigee -> EDM4hep helix conversion (Jacobian push-forward,
// weight-matrix inversion, TrackState emit) lives in the shared
// delphi_edm4hep::Helix class (Helix.h) so PA.TRAC and PA.ELTR use one
// definition.

// Look up the SKELANA VECP index for a given PA's lpa, using the LVECP
// back-link. The `want_charged` flag gates: a charged-track PA wants
// VECP(7,*) != 0; a neutral PA wants VECP(7,*) == 0. (PSHCTRECOVER
// can reclassify mid-PSCEVT; the gate defends against that.)
// Returns 0 if no match.
int find_vecp_index(int lpa, bool want_charged)
{
  for (int i = sk::LVPART; i <= sk::NVECP; ++i) {
    if (sk::LVECP(i) != lpa) continue;
    const int q = static_cast<int>(std::lround(sk::VECP(7, i)));
    if (want_charged && q != 0) return i;
    if (!want_charged && q == 0) return i;
  }
  return 0;
}

}  // namespace

void TrackingWriter::emit()
{
  // Storage that will be moved into the Frame at the end. Handles taken
  // before the move remain valid (podio guarantees handle stability
  // across the collection move).
  edm4hep::TrackCollection                 trkCol;
  edm4hep::ReconstructedParticleCollection pfoCol;
  podio::UserDataCollection<std::int32_t>  lvlockCol;
  podio::UserDataCollection<float>         d0PvCol;
  podio::UserDataCollection<float>         z0PvCol;
  podio::UserDataCollection<float>         d0BsCol;

  Output result;
  result.particle_handles.reserve(static_cast<std::size_t>(sk::NVECP + 1));
  // VECP-index map: size sk::NVECP + 1, all -1 initially. Index 0 unused.
  result.vecp_to_particle.assign(static_cast<std::size_t>(sk::NVECP + 1), -1);
  // PA-index map: sized lazily as we walk; -1 entries for PAs we skip.
  // Reserve a reasonable upper bound to avoid mid-walk reallocation.
  result.pa_to_particle.reserve(static_cast<std::size_t>(sk::NVECP + 16));

  // Helper: register a freshly-created particle handle in the output
  // metadata. vecp_i = 0 means "no VECP match" (the handle still goes
  // into particle_handles, but vecp_to_particle is not updated).
  // The current paIdx is taken from the surrounding forEachPA scope.
  auto record_particle = [&](edm4hep::MutableReconstructedParticle pfo,
                              int vecp_i, int paIdx) {
    const int new_idx = static_cast<int>(result.particle_handles.size());
    result.particle_handles.push_back(pfo);
    if (vecp_i >= 1 && vecp_i < static_cast<int>(result.vecp_to_particle.size())) {
      result.vecp_to_particle[vecp_i] = new_idx;
    }
    if (paIdx >= static_cast<int>(result.pa_to_particle.size())) {
      result.pa_to_particle.resize(static_cast<std::size_t>(paIdx + 1), -1);
    }
    result.pa_to_particle[paIdx] = new_idx;
  };

  // Helper: push the BS/PV-corrected impact-parameter triplet for a
  // VECP-matched track, or NaN sentinels if vecp_i is 0.
  //
  // CONVENTION / FOOTGUN (sDST_TRAC_d0PV / z0PV / d0BS): sk::QTRAC values
  // converted cm -> **mm**, DELPHI sign (rho = Vx sinphi - Vy cosphi), parallel
  // to TRAC_Tracks (charged-only). These are EMPTY (0 / -999) in real DATA --
  // the SKELANA QTRAC common is only filled in MC. For a data-usable impact
  // parameter use sDST_PV_trackD0PV (Vertex.cpp): geometric, also **mm** but
  // LCIO sign, so sDST_PV_trackD0PV ~= -1 * sDST_TRAC_d0PV. Same units and
  // parallel collection now; they still differ in SIGN -- do not mix them.
  static constexpr float kNaN = std::numeric_limits<float>::quiet_NaN();
  auto push_qtrac_or_nan = [&](int vecp_i) {
    if (vecp_i >= 1) {
      d0PvCol.push_back(sk::QTRAC(38, vecp_i) * 10.f);  // cm -> mm
      z0PvCol.push_back(sk::QTRAC(39, vecp_i) * 10.f);  // cm -> mm
      d0BsCol.push_back(sk::QTRAC(40, vecp_i) * 10.f);  // cm -> mm
    } else {
      d0PvCol.push_back(kNaN);
      z0PvCol.push_back(kNaN);
      d0BsCol.push_back(kNaN);
    }
  };

  using namespace delphi_edm4hep::pawalk;

  // Helper: extend pa_to_particle with -1 so the map stays parallel to
  // the PA-walk index even when we return early for a skipped PA.
  auto mark_pa_skipped = [&](int paIdx) {
    if (paIdx >= static_cast<int>(result.pa_to_particle.size())) {
      result.pa_to_particle.resize(static_cast<std::size_t>(paIdx + 1), -1);
    }
  };

  // Charged PAs whose VECP momentum lookup failed (emitted with zero
  // 4-momentum). Logged once per event below so the degradation is loud.
  int n_zero_mom_charged = 0;

  forEachPA([&](int lpa, int paIdx) {
    // PA.MAIN: per-track summary. Charge code at Q(LMAIN+8):
    //   0 = neutral, 1 = positive, 2 = negative, 3 = undefined.
    const int lmain = lphpa("MAIN", lpa);
    if (lmain <= 0) { mark_pa_skipped(paIdx); return; }
    const int charge_code = static_cast<int>(std::lround(ph::Q(lmain + 8)));

    if (charge_code == 0) {
      // ------- Neutral path -------
      // No PA.TRAC. 4-momentum from VECP. Emit only the Particle.
      const int vecp_i = find_vecp_index(lpa, /*want_charged=*/false);
      if (vecp_i < 1) { mark_pa_skipped(paIdx); return; }

      auto npfo = pfoCol.create();
      npfo.setMomentum({sk::VECP(1, vecp_i),
                        sk::VECP(2, vecp_i),
                        sk::VECP(3, vecp_i)});
      npfo.setEnergy(sk::VECP(4, vecp_i));
      npfo.setMass  (sk::VECP(5, vecp_i));
      npfo.setCharge(0.f);
      record_particle(npfo, vecp_i, paIdx);
      // Neutrals have no Track. LVLOCK is parallel to Particles (so it gets
      // the -1 sentinel here); d0PV/z0PV/d0BS are parallel to Tracks
      // (charged-only), so they are intentionally NOT pushed for neutrals.
      lvlockCol.push_back(-1);
      return;
    }

    // ------- Charged path -------
    // PA.TRAC: perigee (d0, z0, theta, phi, 1/R) at +2..+6;
    // 15-element lower-tri weight matrix at +7..+21.
    const int ltrac = lphpa("TRAC", lpa);
    if (ltrac <= 0) { mark_pa_skipped(paIdx); return; }
    const float D0_dp    = ph::Q(ltrac + 2);    // cm
    const float Z0_dp    = ph::Q(ltrac + 3);    // cm
    const float theta_dp = ph::Q(ltrac + 4);    // rad
    const float phi_dp   = ph::Q(ltrac + 5);    // rad
    const float invR_dp  = ph::Q(ltrac + 6);    // 1/cm (signed)
    std::array<float, 15> Wraw{};
    for (int k = 0; k < 15; ++k) Wraw[k] = ph::Q(ltrac + 7 + k);

    const auto helix = Helix::fromPerigee(D0_dp, Z0_dp, theta_dp, phi_dp,
                                          invR_dp, &Wraw);
    if (!helix.valid()) {
      mark_pa_skipped(paIdx);
      return;   // degenerate sin(theta) -> skip
    }

    auto trk = trkCol.create();
    trk.addToTrackStates(helix.toTrackState(edm4hep::TrackState::AtIP));

    // chi2 / ndf from PA.MAIN. +26/+27 (with VD) preferred, fallback to
    // +16/+17 (without VD). SKELANA sanitises ndf to [0, 1000].
    float chi2_vd = ph::Q(lmain + 26);
    int   ndf_vd  = static_cast<int>(std::lround(ph::Q(lmain + 27)));
    if (ndf_vd < 0 || ndf_vd > 1000) ndf_vd = 0;
    if (ndf_vd > 0 && chi2_vd > 0.f) {
      trk.setChi2(chi2_vd);
      trk.setNdf(ndf_vd);
    } else {
      float chi2_no_vd = ph::Q(lmain + 16);
      int   ndf_no_vd  = static_cast<int>(std::lround(ph::Q(lmain + 17)));
      if (ndf_no_vd < 0 || ndf_no_vd > 1000) ndf_no_vd = 0;
      if (ndf_no_vd > 0) {
        trk.setChi2(chi2_no_vd);
        trk.setNdf(ndf_no_vd);
      }
    }

    // VECP-matched index: required for VECP 4-momentum, LVLOCK, and
    // QTRAC reads. If no match, fall back to perigee-derived momentum
    // (with pion mass) — same fallback the current converter uses.
    const int vecp_i = find_vecp_index(lpa, /*want_charged=*/true);

    // Charge sign from PA.MAIN. Code 3 ("undefined") -> 0 (we preserve
    // the ambiguity rather than mapping to +1 like the current code does).
    int sign = 0;
    if      (charge_code == 1) sign = +1;
    else if (charge_code == 2) sign = -1;
    // else: sign = 0 (undefined)

    float px = 0.f, py = 0.f, pz = 0.f, E = 0.f, mass = 0.f;
    if (vecp_i >= 1) {
      px   = sk::VECP(1, vecp_i);
      py   = sk::VECP(2, vecp_i);
      pz   = sk::VECP(3, vecp_i);
      E    = sk::VECP(4, vecp_i);
      mass = sk::VECP(5, vecp_i);
    } else {
      // No VECP match -> this charged Particle keeps zero 4-momentum (the
      // perigee-momentum fallback is intentionally not implemented; VECP is
      // authoritative). Count it so the job degrades loudly (logged per event
      // below) instead of silently emitting an unphysical zero-momentum track.
      ++n_zero_mom_charged;
    }

    auto pfo = pfoCol.create();
    pfo.setMomentum({px, py, pz});
    pfo.setEnergy(E);
    pfo.setMass(mass);
    pfo.setCharge(static_cast<float>(sign));
    pfo.addToTracks(trk);
    record_particle(pfo, vecp_i, paIdx);

    // LVLOCK: per-VECP track-quality bitmask. -1 sentinel if no VECP
    // match. Stored as int32 so bit 32 (REMCLU overlap) is preserved.
    lvlockCol.push_back(vecp_i >= 1 ? sk::LVLOCK(vecp_i) : -1);

    // BS/PV-corrected impact parameters from sk::QTRAC(38..40, vecp_i).
    // PSCTRA indexes by the charged-VECP ordinal which matches vecp_i
    // when IFLODR=1 (charged-first ordering).
    push_qtrac_or_nan(vecp_i);
  });

  if (n_zero_mom_charged > 0) {
    std::cerr << "delphi_edm4hep::tracking: WARNING: " << n_zero_mom_charged
              << " charged PFO(s) had no VECP momentum match and were emitted"
              << " with zero 4-momentum in this event\n";
  }

  // Push all collections into the Frame via the base class's put().
  // Handles in `result` remain valid afterwards.
  put(std::move(trkCol),    "TRAC", "Tracks", Provenance::Derived);
  put(std::move(pfoCol),    "MAIN", "Particles", Provenance::Derived);
  put(std::move(lvlockCol), "VECP", "LVLOCK", Provenance::Derived);
  put(std::move(d0PvCol),   "TRAC", "d0PV", Provenance::Derived);
  put(std::move(z0PvCol),   "TRAC", "z0PV", Provenance::Derived);
  put(std::move(d0BsCol),   "TRAC", "d0BS", Provenance::Derived);

  // Hand off to downstream writers via the shared context.
  ctx_.tracking = std::move(result);
}

}  // namespace delphi_edm4hep::tracking
