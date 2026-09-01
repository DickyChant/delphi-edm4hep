// SticShowerWriter — runs in both passes.
//
// Reads the SKELANA PSCSTC common (skelana/pscemf_hpc_hac_stic.hpp). The
// common is a fixed table with one row per VECP track, not a list of showers:
//   QSTIC(1..3, i)  energy, theta, phi                     (real)
//   KSTIC(4..9, i)  towers, large-veto tag, combined-veto tag,
//                   veto multiplicity A and B, Si-strip vertex   (integer)
// It is zeroed every event, so a track whose row is all zero has no shower.
// NSTIC counts the rows that were filled; it is not an array length.
//
// SKELANA fills the common from either STIC(19), the fullDST module, when the
// PA carries it, or SSTC(33), the shortDST condensation, otherwise (PSHSTC,
// skelana.car:6394). On the SSTC path words 1..3 are the track's MAIN-module
// kinematics rather than STIC measurements, word 4 uses a different scale,
// word 5 is a photon/electron code, and 7..8 stay zero.
//
// The collection name follows the pass (SSTC on sDST, STIC on fDST), not the
// module that supplied the values.

#include "delphi_edm4hep/Calorimeter/SticShower.h"

#include "skelana/pscemf_hpc_hac_stic.hpp"   // NSTIC, KSTIC, QSTIC, LENSTC
#include "skelana/pscvec.hpp"                // LVPART, NVECP

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>

#include <algorithm>
#include <cstdint>

namespace sk = skelana;

namespace delphi_edm4hep::stic_shower {

namespace {
constexpr std::int32_t kTypeBitStic = 0x8;   // bit 3 (0=HPC,1=EMF,2=HCAL,3=STIC)
}  // namespace

void SticShowerWriter::emit()
{
  edm4hep::ClusterCollection col;

  // Pass 1 reads the shortDST module SSTC; the fullDST carries STIC.
  const char* bank = fromFullDst() ? "STIC" : "SSTC";

  const int last = std::min(sk::NVECP, sk::MTRACK);
  for (int i = sk::LVPART; i <= last; ++i) {
    bool filled = false;
    for (int k = 1; k <= sk::LENSTC; ++k) filled = filled || sk::KSTIC(k, i) != 0;
    if (!filled) continue;

    auto clu = col.create();
    clu.setType(kTypeBitStic);
    clu.setEnergy(sk::QSTIC(1, i));
    clu.setITheta(sk::QSTIC(2, i));
    clu.setIPhi  (sk::QSTIC(3, i));
    // Words 4..9, integer throughout.
    for (int k = 4; k <= sk::LENSTC; ++k) {
      clu.addToShapeParameters(static_cast<float>(sk::KSTIC(k, i)));
    }

    // Attach the shower to the particle built from the same VECP slot. Only
    // pass 1 carries that map; pass-2 clusters are left unattached.
    if (ctx_.tracking) {
      auto& tracking = *ctx_.tracking;
      if (i < static_cast<int>(tracking.vecp_to_particle.size())) {
        const int p = tracking.vecp_to_particle[i];
        if (p >= 0) tracking.particle_handles[p].addToClusters(clu);
      }
    }
  }

  put(std::move(col), bank, "Showers", Provenance::Derived);
}

}  // namespace delphi_edm4hep::stic_shower
