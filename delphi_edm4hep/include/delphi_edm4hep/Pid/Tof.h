// Tof domain — runs in both passes: PA.TOF is on the XSDST as well as the
// fullDST.
//
// Walks the fDST PA chain, extracts per-track TOF time + sigma from
// PA.TOF (module 9), and emits a ParticleID collection linked to the
// matching sDST Particle via ctx_.fdst_pa_to_sdst_particle.
//
// Emits:
//   <tag>_TOF_TimeOfFlight   ParticleIDCollection (algoType=5)
//     parameters = [time_ns, sigma_ns]
//     setParticle() -> matched sDST_MAIN_Particles entry
//
// Raw counter, R, Z, Z_extrap are intentionally NOT surfaced — their
// semantics in this DST version need verification (deferred).

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::tof {

class TofWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::tof
