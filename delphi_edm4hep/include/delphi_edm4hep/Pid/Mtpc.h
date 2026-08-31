// Mtpc domain — runs in both passes: PA.MTPC is on the shortDST, the XSDST
// and the fullDST alike.
//
// Reads PA.MTPC (module 7) v1.04+ extended format from the fDST PA
// chain. Emits TWO collections:
//   <tag>_MTPC_dEdxExtended    ParticleIDCollection (algoType=6)
//     parameters[10] = [dEdx80, sigma80, dEdx65, sigma65,
//                       dEdx_integrated80, nPads, nWires, nSat,
//                       nEmpty, padRowPattern]
//   <tag>_MTPC_dEdx_RecDqdx    RecDqdxCollection (parallel)
//     headline value = dEdx80, error = sigma80, type = 1 (TPC trunc-mean)
//
// Both link to the matched sDST Particle via
// ctx_.fdst_pa_to_sdst_particle.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::mtpc {

class MtpcWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::mtpc
