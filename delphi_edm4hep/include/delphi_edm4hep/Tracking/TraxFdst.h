// TraxFdst domain — pass-2 only.
//
// PA.TRAX (label 20) carries a track's extrapolation points (one per
// detector surface) — each a helix-parameter snapshot (c1,c2,c3,θ,φ,1/P)
// with a 5x5 covariance. These are extrapolation (not measurement)
// surfaces; conceptually TrackStates, but appending to the already-put,
// immutable fDST_TRAC_Tracks is not possible from a separate writer, and
// mixing extrapolated states into the measured-TE trackStates vector
// would mislead consumers. So we emit one structured ParticleID entry
// PER POINT (not one flat per-track blob), which keeps the per-point
// cardinality + the particle association.
//
// Emits:
//   fDST_TRAX_ExtrapPoints   ParticleIDCollection (algType=20)
//     one entry per extrapolation point, setParticle -> matched Particle
//     parameters[0..22] =
//       [det_id, meas_code, c1_mm, c2_mm, c3_mm, theta, phi, invP,
//        cov[0..14]]   (cov in the TE 5x5 lower-tri basis)

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::trax_fdst {

class TraxFdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::trax_fdst
