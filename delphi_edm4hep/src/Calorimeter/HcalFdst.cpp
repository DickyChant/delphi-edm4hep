// HcalFdstWriter — pass-2 implementation.
//
// PA.HCAL bank (hacfixxx.car line 805), per shower at show_ofs:
//   +1   len
//   +3   E    (shower-level, GeV)
//   +4..+6  X, Y, Z (shower-level centroid, cm)
//   +10  NLAY      (number of layers with hits)
//   +11  LAYPAT    (layer-hit-pattern bits)
//   +11+1..+11+2*NLAY  per-layer (E + ncells+1000*layer)
//   locw = +11+NLAY*2  start of tower block:
//     locw+1            NTD (number of towers)
//     locw+2*k+2        TDAM   (tower energy, GeV)
//     locw+2*k+3        LAYLUV (LAY*10000 + JU*100 + JV)

#include "delphi_edm4hep/Calorimeter/HcalFdst.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/CalorimeterHitCollection.h>
#include <edm4hep/MutableCalorimeterHit.h>

#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::hcal_fdst {

namespace {
constexpr float kCm2Mm = 10.f;
}

void HcalFdstWriter::emit()
{
  edm4hep::CalorimeterHitCollection tow_col;

  pawalk::forEachPA([&](int lpa, int /*paIdx*/) {
    const int lhcal = pawalk::lphpa("HCAL", lpa);
    if (lhcal <= 0) return;
    const int nsh = static_cast<int>(std::lround(ph::Q(lhcal + 2)));
    if (nsh <= 0) return;

    int show_ofs = lhcal + 2;
    for (int ish = 0; ish < nsh; ++ish) {
      const int len  = static_cast<int>(std::lround(ph::Q(show_ofs + 1)));
      const float X  = ph::Q(show_ofs + 4);
      const float Y  = ph::Q(show_ofs + 5);
      const float Z  = ph::Q(show_ofs + 6);
      const int nlay = static_cast<int>(std::lround(ph::Q(show_ofs + 10)));

      if (nlay < 1 || nlay > 10 || len < 11 + 2 * nlay + 1) {
        if (len <= 0) break;
        show_ofs += len;
        continue;
      }

      const int locw = show_ofs + 11 + nlay * 2;
      const int ntd  = static_cast<int>(std::lround(ph::Q(locw + 1)));
      if (ntd > 0 && ntd < 1000 &&
          len >= (locw - show_ofs) + 1 + 2 * ntd) {
        for (int k = 0; k < ntd; ++k) {
          const float tdam = ph::Q(locw + 2 + 2 * k);
          const int   pkd  = static_cast<int>(std::lround(ph::Q(locw + 3 + 2 * k)));
          const int   lay  = pkd / 10000;
          auto hit = tow_col.create();
          hit.setEnergy(tdam);
          hit.setEnergyError(0.f);
          hit.setTime(0.f);
          hit.setType(lay);                                 // LAY (1..7)
          hit.setCellID(static_cast<std::uint64_t>(pkd));   // full packed
          hit.setPosition({
            X * kCm2Mm, Y * kCm2Mm, Z * kCm2Mm,
          });
        }
      }

      if (len <= 0) break;
      show_ofs += len;
    }
  });

  put(std::move(tow_col), "HCAL", "Towers", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::hcal_fdst
