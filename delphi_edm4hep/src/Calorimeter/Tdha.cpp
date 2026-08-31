// TdhaWriter — implementation. Runs in both passes.
//
// PA.TDHA (label 11) layout (longdes §3.04, verified vs the legacy
// delphi_fdst_pad_dump TDHA reader):
//   +2  nlay (number of HCAL layers)
//   per-layer record (variable, first at ofs=ltdha+2):
//     +1  layer_len   +2  lnum   +3  loc (0=barrel,1=endcap)
//     +4  X/R   +5  Y/Rφ   +6  Z   (extrap coords)
//     +9  ntd (n associated TDs in this layer)
//     per-TD (4 words, TD it at base=ofs+9+4*it):
//       base+1 X/R, base+2 Y/Rφ, base+3 Z, base+4 energy
//   next layer at ofs += layer_len.

#include "delphi_edm4hep/Calorimeter/Tdha.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/CalorimeterHitCollection.h>
#include <edm4hep/MutableCalorimeterHit.h>

#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::tdha {

namespace {
constexpr float kCm2Mm = 10.f;
constexpr int   kMaxLayerLen = 200;
constexpr int   kMaxNtd      = 200;
}  // namespace

void TdhaWriter::emit()
{
  edm4hep::CalorimeterHitCollection col;

  pawalk::forEachPA([&](int lpa, int /*paIdx*/) {
    const int ltdha = pawalk::lphpa("TDHA", lpa);
    if (ltdha <= 0) return;
    const int nlay = static_cast<int>(std::lround(ph::Q(ltdha + 2)));
    if (nlay <= 0) return;

    int ofs = ltdha + 2;
    for (int il = 0; il < nlay && ofs > ltdha; ++il) {
      const int layer_len = static_cast<int>(std::lround(ph::Q(ofs + 1)));
      if (layer_len <= 0 || layer_len > kMaxLayerLen) break;
      const int lnum = static_cast<int>(std::lround(ph::Q(ofs + 2)));
      const int loc  = static_cast<int>(std::lround(ph::Q(ofs + 3)));
      const int ntd  = static_cast<int>(std::lround(ph::Q(ofs + 9)));

      if (ntd > 0 && ntd < kMaxNtd) {
        for (int it = 0; it < ntd; ++it) {
          const int   base = ofs + 9 + 4 * it;
          const float c1   = ph::Q(base + 1);   // X (endcap) / R (barrel)
          const float c2   = ph::Q(base + 2);   // Y (endcap) / Rφ (barrel)
          const float z    = ph::Q(base + 3);
          const float e    = ph::Q(base + 4);

          float x = c1, y = c2;
          if (loc == 0 && c1 > 0.f) {            // barrel: R/Rφ → cartesian
            const float phi = c2 / c1;
            x = c1 * std::cos(phi);
            y = c1 * std::sin(phi);
          }

          auto hit = col.create();
          hit.setEnergy(e);
          hit.setEnergyError(0.f);
          hit.setTime(0.f);                      // no per-hit time at DST level
          hit.setType(lnum);                     // HCAL layer number
          hit.setCellID(static_cast<std::uint64_t>(loc));
          hit.setPosition({ x * kCm2Mm, y * kCm2Mm, z * kCm2Mm });
        }
      }
      ofs += layer_len;
    }
  });

  put(std::move(col), "TDHA", "HcalTimeHits", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::tdha
