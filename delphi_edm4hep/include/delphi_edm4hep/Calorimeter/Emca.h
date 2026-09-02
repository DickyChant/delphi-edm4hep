// Emca domain — runs in both passes: PA.EMCA is on the XSDST as well as the
// fullDST.
//
// Walks fDST PA chain, reads PA.EMCA (the fDST-only per-cluster bank
// — distinct from PA.EMNC, which is the sDST shower summary). Each
// EMCA shower contains either HPC barrel data (idet=9, per-pad PXHGET-
// packed 3-word records) or FEMC endcap data (idet=26, per-LAYER 2-word
// records). We emit:
//
//   <tag>_EMCA_HPCClusters     CalorimeterHitCollection   — per HPC pad
//                              decoded via PXHGET
//   <tag>_EMCA_FEMCLayers      CalorimeterHitCollection   — per FEMC
//                              layer (energy + packed layer/nhits)
//
// The shower→hit cascade (fDST_EMNC_Showers.addToHits → these
// collections) is done by the shower hybrid writer; we emit the hits in
// canonical PA-walk + shower-index + cluster-index order so it can
// re-walk and link.
//

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::emca {

class EmcaWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::emca
