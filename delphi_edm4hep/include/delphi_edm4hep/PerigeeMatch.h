// PerigeeMatch.h
//
// Identity-binding between sDST and fDST tracks via PA.TRAC perigee
// geometry. Used by the pass-2 binary.
//
// Why perigee-geometric matching: paIdx and vecp_i are PSCEVT-rebuilt
// per DST level and NOT invariant across sDST/fDST for the same
// physical track. The PA.TRAC perigee parameters (d0, z0, theta, phi,
// 1/R) are stored identically on both DST levels for the same physical
// track — float-precision identity, modulo any postDST re-fit. This is
// the only reliable identity key.
//
// The cost formula and tolerance are kept compatible with the legacy
// SDST converter's fdst-sidecar matcher, which has been validated to
// ~97% match rate on the qq sample.

#pragma once

#include <edm4hep/TrackCollection.h>

namespace delphi_edm4hep::perigee_match {

// Given the sDST Track collection (helix basis, mm) and one fDST
// candidate track's perigee parameters (also helix basis, mm),
// find the best-matching sDST Track index within tolerance.
// Returns -1 if no match.
//
// The cost is computed in DELPHI cm-units internally so the
// `tolerance_cm2` default matches the legacy converter's threshold
// exactly. Cost formula:
//   cost = (dd0[cm])² + (dz0[cm])² + (1000·d_invR[1/cm])²
//   tolerance: 1e-4 cm² (~ 100 μm radial match)
//
// Charge gate: implicit via the sign of omega (= sign of q·B·sin(θ)·invP;
// the B-field is uniform per event so sign(omega) == sign(q)).
int findMatch(
  const edm4hep::TrackCollection& sdst_tracks,
  double fdst_D0_mm,
  double fdst_Z0_mm,
  double fdst_omega_per_mm,
  int    fdst_charge_signed,
  double tolerance_cm2 = 1.0e-4);

}  // namespace delphi_edm4hep::perigee_match
