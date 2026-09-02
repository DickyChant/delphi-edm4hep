// PidHybrid domain — pass-2 hybrid cascade writer.
//
// Re-emits the per-particle ID + dE/dx collections from sDST under the
// fDST tag, with the setParticle() / setTrack() relations re-pointed
// at fDST_MAIN_Particles / fDST_TRAC_Tracks. Scalar contents (algorithm
// type, likelihood, parameter vector) are copied verbatim.
//
//   sDST_HAID_HadronID       → fDST_HAID_HadronID
//   sDST_MUID_MuonID         → fDST_MUID_MuonID
//   sDST_ELID_ElectronID     → fDST_ELID_ElectronID
//   sDST_<algo>_Dedx         → fDST_<algo>_Dedx
//   sDST_<algo>_DedxRecDqdx  → fDST_<algo>_DedxRecDqdx
//
// <algo> is BBDXGET or GETDEDX, whichever pass 1 wrote (ParticleId.cpp).
//
// Uses the identity 1:1 mapping (sDST_MAIN_Particles[i] ↔
// fDST_MAIN_Particles[i]).
//

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::pid_hybrid {

class PidHybridWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::pid_hybrid
