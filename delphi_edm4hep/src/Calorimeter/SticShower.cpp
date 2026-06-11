// SticShowerWriter — runs in both passes.
//
// Reads the SKELANA PSCSTC common (skelana/pscemf_hpc_hac_stic.hpp):
//   NSTIC          number of STIC showers this event
//   QSTIC(1..6, j) E, θ, φ, nTowers, vetoTag, Si-vertex position
// and emits one Cluster per shower. The bank mnemonic in the collection
// name follows the pass (SSTC on sDST, STIC on fDST); the data source is
// the same common.

#include "delphi_edm4hep/Calorimeter/SticShower.h"

#include "skelana/pscemf_hpc_hac_stic.hpp"   // NSTIC, QSTIC

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>

#include <algorithm>
#include <cstdint>

namespace sk = skelana;

namespace delphi_edm4hep::stic_shower {

namespace {
constexpr std::int32_t kTypeBitStic = 0x8;   // bit 3 (0=HPC,1=EMF,2=HCAL,3=STIC)
constexpr int          kMaxStic     = 200;
}  // namespace

void SticShowerWriter::emit()
{
  edm4hep::ClusterCollection col;

  const bool is_sdst = (source_tag_ == "sDST");
  const char* bank   = is_sdst ? "SSTC" : "STIC";

  const int n = std::min(sk::NSTIC, kMaxStic);
  for (int j = 1; j <= n; ++j) {
    auto clu = col.create();
    clu.setType(kTypeBitStic);
    clu.setEnergy(sk::QSTIC(1, j));
    clu.setITheta(sk::QSTIC(2, j));
    clu.setIPhi  (sk::QSTIC(3, j));
    clu.addToShapeParameters(sk::QSTIC(4, j));   // nTowers
    clu.addToShapeParameters(sk::QSTIC(5, j));   // vetoTag
    clu.addToShapeParameters(sk::QSTIC(6, j));   // Si-vertex position
  }

  put(std::move(col), bank, "Showers");
}

}  // namespace delphi_edm4hep::stic_shower
