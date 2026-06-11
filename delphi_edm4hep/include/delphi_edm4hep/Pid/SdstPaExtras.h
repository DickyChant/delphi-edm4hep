// SdstPaExtras domain — pass-1 only.
//
// Two sDST-only PA modules that are genuine per-particle ID / hit
// summaries, so ParticleID is the correct edm4hep home. Bound to the
// owning Particle via ctx_.tracking->pa_to_particle (covers charged and
// neutral PAs — PHOT in particular applies to neutral photon PAs).
//
// Emits (ParticleIDCollection):
//   sDST_PHOT_PhotonID       (algType=30)  PA.PHOT  HPC photon-ID scores
//     parameters = Q(lphot+2 .. ) up to 7 words (native bank units)
//   sDST_ODHI_OuterDetector  (algType=29)  PA.ODHI  OD per-track hit summary
//     parameters = Q(lodhi+2 .. ) up to 7 words
//   sDST_MUFI_RefitMuon      (algType=27)  PA.MUFI  refitted-MU fit summary
//     parameters = Q(lmufi+2 .. +18): det, nlay, ndf, chi2_global, x1, y1,
//     n_miss, chi2_chambers, x/y/theta/phi extrap + 4 errors, hit_pattern
//     (the fixed header; variable per-layer blocks not surfaced)
//
// Raw PA-bank reads (LPHPA + IPHREQ for length) rather than a SKELANA
// common, since no PSCPHO/PSCODHI wrapper is guaranteed populated by the
// pass-1 harness; the bank words are always present when the module is.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::sdst_pa_extras {

class SdstPaExtrasWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::sdst_pa_extras
