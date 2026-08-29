// Calorimeter domain — shower clusters from the PA calorimeter modules.
//
// Walks the PA chain and emits one Cluster per shower. Cluster.type bits
// encode the sub-detector:
//   bit 0 = HPC   (EMNC, idet 9)
//   bit 1 = FEMC  (EMNC, idet 26)
//   bit 2 = HCAL  (HCNC)
//
// One collection per source module. Charged/neutral is not split here — it
// is inferable from the owning Particle's `clusters` relation.
//
// Module layouts are documented in the ShortDST content note, DELPHI 97-146
// PROG-221, doi:10.7483/OPENDATA.DELPHI.LJAQ.LMZ0, under "PA extra-module
// EMNC(22)" and "HCNC(23)". Word numbers below refer to those tables.

#include "delphi_edm4hep/Calorimeter/Calorimeter.h"

#include "delphi_edm4hep/internal/BankReader.h"

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <podio/Frame.h>

#include <algorithm>
#include <cstdint>
#include <string>

namespace delphi_edm4hep::calorimeter {

namespace {

// DELPHI cm -> EDM4hep mm.
constexpr double kCm2Mm = 10.0;

// Cluster.type bit encoding (see file header).
constexpr std::int32_t kTypeBitHPC  = 0x01;
constexpr std::int32_t kTypeBitEMF  = 0x02;
constexpr std::int32_t kTypeBitHCAL = 0x04;

// Detector identifiers carried in EMNC word +2.
constexpr int kIdetHPC = 9;
constexpr int kIdetEMF = 26;

// Shower header, words +1..+4: energy (GeV), then x, y, z (cm).
void setHeaderEnergyPosition(edm4hep::MutableCluster clu,
                             const banks::Record& shower) {
  clu.setEnergy(shower.real(1));
  clu.setPosition({
    static_cast<float>(shower.real(2) * kCm2Mm),
    static_cast<float>(shower.real(3) * kCm2Mm),
    static_cast<float>(shower.real(4) * kCm2Mm),
  });
}

// Electromagnetic showers for one PA. Emits one Cluster per shower and
// attaches each to the owning particle.
void walkEMNC(int lpa,
              edm4hep::MutableReconstructedParticle pfo,
              edm4hep::ClusterCollection& cluCol)
{
  const auto emnc = banks::find(lpa, "EMNC");
  if (!emnc) return;

  // Module word +2 packs both counts: nshowr + 100 * idet. idet is uniform
  // within one module.
  const int nsidet = emnc->integer(2);
  const int nshowr = nsidet % 100;
  const int idet   = nsidet / 100;
  if (nshowr <= 0) return;

  const std::int32_t type_bit =
      (idet == kIdetHPC) ? kTypeBitHPC :
      (idet == kIdetEMF) ? kTypeBitEMF :
                           0;          // unknown detector — emit anyway

  // The HPC has ten layers.
  constexpr int kMaxHpcLayers = 10;

  auto shower = emnc->subRecord(2);
  for (int ns = 0; ns < nshowr; ++ns) {
    auto clu = cluCol.create();
    clu.setType(type_bit);
    setHeaderEnergyPosition(clu, shower);

    int stride = 4;               // FEMC carries no layer detail here

    if (idet == kIdetHPC) {
      // HPC continuation: +5 = layers hit, +6 = layer bit pattern,
      // +7.. = energy of each layer present, in pattern order.
      const int nlay = shower.integer(5);
      const int patt = shower.integer(6);
      if (nlay > 0 && nlay <= kMaxHpcLayers) {
        // Expanded to a dense ten-element profile, zero for layers absent
        // from the pattern, so subdetectorEnergies has a fixed length per
        // HPC cluster.
        int filled = 0;
        for (int nl = 1; nl <= kMaxHpcLayers && filled < nlay; ++nl) {
          const bool hit = ((patt >> (nl - 1)) & 1) != 0;
          float layerE = 0.f;
          if (hit) {
            ++filled;
            layerE = shower.real(6 + filled);
          }
          clu.addToSubdetectorEnergies(layerE);
        }
      }
      stride = 6 + nlay;
    }
    // FEMC per-block detail lives in PA module EL(5), which is fullDST only.

    pfo.addToClusters(clu);
    shower = shower.subRecord(stride);
  }
}

// Hadronic showers for one PA. Per-layer energies go to
// subdetectorEnergies and the matching layer indices to shapeParameters,
// so the two stay index-parallel without a second collection.
void walkHCNC(int lpa,
              edm4hep::MutableReconstructedParticle pfo,
              edm4hep::ClusterCollection& cluCol)
{
  const auto hcnc = banks::find(lpa, "HCNC");
  if (!hcnc) return;

  // Module word +2 = number of showers.
  const int nshowr = hcnc->integer(2);
  if (nshowr <= 0) return;

  // Defensive bound on the per-shower layer count.
  constexpr int kMaxHcalLayers = 200;

  auto shower = hcnc->subRecord(2);
  for (int ns = 0; ns < nshowr; ++ns) {
    auto clu = cluCol.create();
    clu.setType(kTypeBitHCAL);
    setHeaderEnergyPosition(clu, shower);

    // +5 = layer hits. Each hit is two words:
    //   +5 + 2n - 1   energy
    //   +5 + 2n       1000 * layer + channels in that layer
    const int nlay = shower.integer(5);
    if (nlay > 0 && nlay < kMaxHcalLayers) {
      for (int nl = 1; nl <= nlay; ++nl) {
        const float hitE  = shower.real(5 + 2 * nl - 1);
        const int   layer = shower.integer(5 + 2 * nl) / 1000;
        clu.addToSubdetectorEnergies(hitE);
        clu.addToShapeParameters(static_cast<float>(layer));
      }
    }

    pfo.addToClusters(clu);
    shower = shower.subRecord(5 + 2 * std::max(0, nlay));
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

  // Emitted even when empty, so the schema does not depend on whether
  // tracking ran.
  put(std::move(emncCol), "EMNC", "Showers", Provenance::Transcribed);
  put(std::move(hcncCol), "HCNC", "Showers", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::calorimeter
