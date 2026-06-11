// Calorimeter domain — implementation S6.
//
// Walks the PA chain, reads PA.EMNC (label 22) and PA.HCNC (label 23)
// for each PA, and emits one Cluster per shower. Cluster.type bits
// encode the physical sub-detector:
//   bit 0 = HPC   (EMNC idet = 9)
//   bit 1 = EMF   (EMNC idet = 26)
//   bit 2 = HCAL  (HCNC)
//
// One collection per source bank (no charged/neutral split — that's
// inferable from the owning Particle's `clusters` relation).
//
// Layouts per shortdes.txt p.45-47:
//   EMNC shower stride:
//     header (E, X, Y, Z)            4 words
//     HPC continuation (idet=9):     +5=nlay, +6=pattern, +7..+6+nlay = per-layer E   -> stride = 6 + nlay
//     EMF continuation (idet=26):    no layer detail at this DST level -> stride = 4
//   HCNC shower stride:
//     header (E, X, Y, Z)            4 words
//     +5 = nlay
//     per-layer: +5+2*nl - 1 = E_layer; +5+2*nl = 1000*layer + nChannels
//     -> stride = 5 + 2*nlay
//
// NO shape moments, NO sibling proxies (both deferred),
// NO HPC per-cluster PXHGET decode (that's fDST and lives in S8/step-2).

#include "delphi_edm4hep/Calorimeter/Calorimeter.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <podio/Frame.h>

#include <cmath>
#include <cstdint>
#include <string>

namespace ph = phdst;

namespace delphi_edm4hep::calorimeter {

namespace {

// DELPHI cm -> EDM4hep mm.
constexpr double kCm2Mm = 10.0;

// Cluster.type bit encoding (see file header).
constexpr std::int32_t kTypeBitHPC  = 0x01;
constexpr std::int32_t kTypeBitEMF  = 0x02;
constexpr std::int32_t kTypeBitHCAL = 0x04;

// Detector-identifier values inside EMNC's "+2 = nshowr + 100*idet" word.
constexpr int kIdetHPC = 9;
constexpr int kIdetEMF = 26;

// Set Cluster's energy + position from a 4-word header. `base` is the
// L-address such that Q(base+1) = E, Q(base+2..+4) = X/Y/Z (cm).
void setHeaderEnergyPosition(edm4hep::MutableCluster clu, int base) {
  clu.setEnergy(ph::Q(base + 1));
  clu.setPosition({
    static_cast<float>(ph::Q(base + 2) * kCm2Mm),
    static_cast<float>(ph::Q(base + 3) * kCm2Mm),
    static_cast<float>(ph::Q(base + 4) * kCm2Mm),
  });
}

// EMNC walk for a single PA. Emits one Cluster per shower into `cluCol`
// and attaches each to the owning `pfo` via addToClusters.
void walkEMNC(int lpa,
              edm4hep::MutableReconstructedParticle pfo,
              edm4hep::ClusterCollection& cluCol)
{
  const int lemnc = pawalk::lphpa("EMNC", lpa);
  if (lemnc <= 0) return;

  // +2 = nshowr + 100 * idet. idet is uniform within one EMNC bank.
  const int nsidet = static_cast<int>(std::lround(ph::Q(lemnc + 2)));
  const int nshowr = nsidet % 100;
  const int idet   = nsidet / 100;
  if (nshowr <= 0) return;

  const std::int32_t type_bit =
      (idet == kIdetHPC) ? kTypeBitHPC :
      (idet == kIdetEMF) ? kTypeBitEMF :
                           0;          // unknown detector — emit anyway

  // Bound nlay walk: HPC has up to 10 layers per shortdes.txt.
  constexpr int kMaxHpcLayers = 10;

  int lshowr = lemnc + 2;   // first shower starts here
  for (int ns = 0; ns < nshowr; ++ns) {
    auto clu = cluCol.create();
    clu.setType(type_bit);
    setHeaderEnergyPosition(clu, lshowr);

    int stride = 4;          // default = EMF (no layer detail)

    if (idet == kIdetHPC) {
      // HPC: NLAY at +5, layer pattern at +6, per-layer E at +7..+6+nlay.
      // We expand to a DENSE 10-element profile (zeros for layers not in
      // the pattern) so subdetectorEnergies is fixed-length per HPC
      // cluster — easier for downstream ML / shape-moment consumers.
      const int nlay = static_cast<int>(std::lround(ph::Q(lshowr + 5)));
      const int patt = static_cast<int>(std::lround(ph::Q(lshowr + 6)));
      if (nlay > 0 && nlay <= kMaxHpcLayers) {
        int filled = 0;
        for (int nl = 1; nl <= kMaxHpcLayers && filled < nlay; ++nl) {
          const bool hit = ((patt >> (nl - 1)) & 1) != 0;
          float layerE = 0.f;
          if (hit) {
            ++filled;
            layerE = ph::Q(lshowr + 6 + filled);
          }
          clu.addToSubdetectorEnergies(layerE);
        }
      }
      stride = 6 + nlay;
    }
    // (EMF currently emits header only; per-block detail is in PA.EL
    //  module 5 which is fDST-only and not yet wired.)

    pfo.addToClusters(clu);
    lshowr += stride;
  }
}

// HCNC walk for a single PA. Per-shower header + per-layer (E, layer-id)
// emitted into subdetectorEnergies (energies) and shapeParameters
// (layer indices, NOT shape moments — keeps the per-layer correspondence
// indexable without a second collection).
void walkHCNC(int lpa,
              edm4hep::MutableReconstructedParticle pfo,
              edm4hep::ClusterCollection& cluCol)
{
  const int lhcnc = pawalk::lphpa("HCNC", lpa);
  if (lhcnc <= 0) return;

  const int nshowr = static_cast<int>(std::lround(ph::Q(lhcnc + 2)));
  if (nshowr <= 0) return;

  int lshowr = lhcnc + 2;
  for (int ns = 0; ns < nshowr; ++ns) {
    auto clu = cluCol.create();
    clu.setType(kTypeBitHCAL);
    setHeaderEnergyPosition(clu, lshowr);

    // +5 = number of layer-hits. Per-layer record: 2 words each:
    //   +5+2*nl-1 = E_layer
    //   +5+2*nl   = 1000*layer + nChannels
    const int nlay = static_cast<int>(std::lround(ph::Q(lshowr + 5)));
    if (nlay > 0 && nlay < 200) {   // 200 is a defensive upper bound
      for (int nl = 1; nl <= nlay; ++nl) {
        const float hitE   = ph::Q(lshowr + 5 + 2 * nl - 1);
        const int   packed = static_cast<int>(std::lround(ph::Q(lshowr + 5 + 2 * nl)));
        const int   layer  = packed / 1000;
        clu.addToSubdetectorEnergies(hitE);
        clu.addToShapeParameters(static_cast<float>(layer));
      }
    }

    pfo.addToClusters(clu);
    lshowr += 5 + 2 * std::max(0, nlay);
  }
}

}  // namespace

void CalorimeterWriter::emit()
{
  edm4hep::ClusterCollection emncCol;
  edm4hep::ClusterCollection hcncCol;

  if (ctx_.tracking) {
    const auto& tracking = *ctx_.tracking;
    pawalk::forEachPA([&](int lpa, int paIdx) {
      if (paIdx >= static_cast<int>(tracking.pa_to_particle.size())) return;
      const int particle_idx = tracking.pa_to_particle[paIdx];
      if (particle_idx < 0) return;
      auto pfo = tracking.particle_handles[particle_idx];

      walkEMNC(lpa, pfo, emncCol);
      walkHCNC(lpa, pfo, hcncCol);
    });
  }

  // Push collections through the base helper, including the empty
  // case (schema stability when tracking didn't run).
  put(std::move(emncCol), "EMNC", "Showers");
  put(std::move(hcncCol), "HCNC", "Showers");
}

}  // namespace delphi_edm4hep::calorimeter
