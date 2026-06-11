// MainHybrid domain — pass-2 hybrid cascade writer (the central
// "particle + vertex" re-wire).
//
// Clones sDST_MAIN_Particles → fDST_MAIN_Particles with `tracks`
// re-pointed at the fDST track collection (built by TeStateMerge).
// Then cascades through every vertex collection that references
// particles:
//
//   sDST_PV_PrimaryVertex      → fDST_PV_PrimaryVertex
//   sDST_PV_Vertices           → fDST_PV_Vertices
//   sDST_V0_V0Candidates       → fDST_V0_V0Candidates
//   sDST_PHC_PhotonConversions → fDST_PHC_PhotonConversions
//
// — each cloned vertex's addToParticles relation is re-pointed to the
// matching fDST_MAIN_Particles entry.
//
// Cluster + ParticleID relations on the particles are intentionally
// NOT re-wired here. The shower-hybrid writer rewrites clusters to
// fDST_EMNC_Showers/HCNC_Showers; the PID-hybrid writer rewrites
// particleIDs to fDST_HAID/MUID/ELID. They use the same identity-1:1
// mapping (fDST_MAIN_Particles[i] ↔ sDST_MAIN_Particles[i]) so no
// shared state through EventContext is required.
//

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::main_hybrid {

class MainHybridWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::main_hybrid
