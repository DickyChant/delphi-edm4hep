// CcalFdstWriter — pass-2 implementation.
//
// PA.CCAL (module 1) layout (dst_content.txt, same per-shower convention
// as PA.EMCA):
//   +2  NS (number of combined showers)
//   per-shower record (first at lccal+2, stride = len):
//     +1 len(=9)  +2 detid(31=CCA)  +3 E  +4 X  +5 Y  +6 Z
//     +7 massID   +8 theta  +9 phi

#include "delphi_edm4hep/Calorimeter/CcalFdst.h"

#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>

#include <cmath>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::ccal_fdst {

namespace {
constexpr float        kCm2Mm     = 10.f;
constexpr std::int32_t kTypeBitCCA = 0x10;   // bit 4
constexpr int          kMaxShowers = 200;
}  // namespace

void CcalFdstWriter::emit()
{
  edm4hep::ClusterCollection col;

  pawalk::forEachPA([&](int lpa, int /*paIdx*/) {
    const int lccal = pawalk::lphpa("CCAL", lpa);
    if (lccal <= 0) return;
    const int nsh = static_cast<int>(std::lround(ph::Q(lccal + 2)));
    if (nsh <= 0 || nsh > kMaxShowers) return;

    int show_ofs = lccal + 2;
    for (int ns = 0; ns < nsh; ++ns) {
      const int len = static_cast<int>(std::lround(ph::Q(show_ofs + 1)));
      if (len <= 0) break;
      auto clu = col.create();
      clu.setType(kTypeBitCCA);
      clu.setEnergy(ph::Q(show_ofs + 3));
      clu.setPosition({
        ph::Q(show_ofs + 4) * kCm2Mm,
        ph::Q(show_ofs + 5) * kCm2Mm,
        ph::Q(show_ofs + 6) * kCm2Mm,
      });
      clu.setITheta(ph::Q(show_ofs + 8));
      clu.setIPhi  (ph::Q(show_ofs + 9));
      show_ofs += len;
    }
  });

  put(std::move(col), "CCAL", "Showers");
}

}  // namespace delphi_edm4hep::ccal_fdst
