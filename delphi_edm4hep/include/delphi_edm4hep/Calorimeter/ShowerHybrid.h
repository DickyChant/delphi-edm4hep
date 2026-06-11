// ShowerHybrid domain — pass-2 hybrid cascade writer.
//
// Re-emits the per-shower summary collections from sDST under the
// fDST tag (scalars, subdetectorEnergies, shapeParameters, type).
// These clones are value-identical to the sDST versions.
//
//   sDST_EMNC_Showers → fDST_EMNC_Showers
//   sDST_HCNC_Showers → fDST_HCNC_Showers
//
// Per §4.2, the showers were also to gain `addToHits` references into
// the per-pad fDST_EMCA_HPCClusters / fDST_HCAL_Towers. That link is
// NOT wired here — the PA-walk ordering needed to align sDST shower
// indices with per-pad hit indices is non-trivial and the per-pad
// detail is already exposed as standalone collections (offline join
// on PA index recovers the link). Tracked as a follow-up.
//
// fDST_MAIN_Particles.clusters relation also stays pointing at the
// sDST_EMNC/HCNC_Showers collections (the clones are byte-identical;
// no re-point needed unless the shower→hit link is filled in).

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::shower_hybrid {

class ShowerHybridWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::shower_hybrid
