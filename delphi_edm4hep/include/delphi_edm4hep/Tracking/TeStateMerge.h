// TeStateMerge domain — pass-2 hybrid writer.
//
// Walks fDST PA chain, reads PA.TE{ID,TP,OD,FA,FB} (labels 12..16),
// calls BasisConversion::teToHelix per TE, and produces:
//
//   <tag>_TRAC_Tracks                TrackCollection (one per sDST Track;
//                                    cloned with sDST AtIP state +
//                                    appended per-TE TrackStates
//                                    location=Other from the matched
//                                    fDST PA)
//   <tag>_TRAC_Tracks_FitQuality     ParticleIDCollection (companion)
//                                    one entry per (Particle, TE detector)
//                                    parameters[0..6] =
//                                      [charge_signed, B_tesla, descriptor,
//                                       ndf, chi2, length_cm, n_cov]
//
// Bank-format decoding (descriptor bits, variable-length cov layout,
// ndf/chi2/length offsets) lives in te_bank::decode (TeBank.h). The
// TE-basis cov is pushed forward through teToHelix to fill the helix
// covariance on each appended TrackState.
//
// Known limitation: TEID can hold multiple stacked TER's in one PA
// sub-bank. We decode only the first TER; for stacks, te_bank::decode
// returns ok=false and ndf/chi2/length are emitted as 0. The first
// TER's cov is still used for the helix push-forward.
//

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::te_merge {

class TeStateMergeWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::te_merge
