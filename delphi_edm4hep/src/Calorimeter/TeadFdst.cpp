// TeadFdstWriter — pass-2 implementation.
//
// LDTOP-10 chain (unassociated TE BANK 10), sub-banks 5 = TOF barrel,
// 11 = HOF forward. Walk via LQ links: ltead = LQ(LDTOP-10);
// lcur     = LQ(ltead - 5)  for the first TOF hit, then lcur = LQ(lcur)
// until lcur=0.
//
// TOF barrel layout (sub-bank 5):
//   Q(+5)  = R     (constant 311.25 cm)
//   Q(+6)  = R*phi (cm)  → phi = R*phi / R
//   Q(+7)  = Z     (cm) ∈ [-347, +347]
//   Q(+10) = time  (ns)
//
// HOF forward layout (sub-bank 11): standard TE format, (X, Y, Z)
// direct; time NOT decoded at this DST level.

#include "delphi_edm4hep/Calorimeter/TeadFdst.h"

#include "phdst/uxcom.hpp"
#include "phdst/uxlink.hpp"

#include <edm4hep/CalorimeterHitCollection.h>
#include <edm4hep/MutableCalorimeterHit.h>

#include <cmath>

namespace ph = phdst;

namespace delphi_edm4hep::tead_fdst {

namespace {
constexpr float kCm2Mm = 10.f;
}

void TeadFdstWriter::emit()
{
  edm4hep::CalorimeterHitCollection tof_col;
  edm4hep::CalorimeterHitCollection hof_col;

  const int LDTOP = ph::LDTOP;
  if (LDTOP <= 0) {
    put(std::move(tof_col), "TEAD", "TOFHits");
    put(std::move(hof_col), "TEAD", "HOFHits");
    return;
  }

  const int ltead = ph::LQ(LDTOP - 10);
  if (ltead <= 0) {
    put(std::move(tof_col), "TEAD", "TOFHits");
    put(std::move(hof_col), "TEAD", "HOFHits");
    return;
  }

  // sub-bank 5 = TOF barrel.
  for (int lcur = ph::LQ(ltead - 5); lcur > 0; lcur = ph::LQ(lcur)) {
    const float R    = ph::Q(lcur + 5);
    const float Rphi = ph::Q(lcur + 6);
    const float Z    = ph::Q(lcur + 7);
    const float t_ns = ph::Q(lcur + 10);
    const float phi  = (R > 0.f) ? (Rphi / R) : 0.f;
    const float X    = R * std::cos(phi);
    const float Y    = R * std::sin(phi);
    auto hit = tof_col.create();
    hit.setEnergy(0.f);          // TOF: no energy at this DST level
    hit.setEnergyError(0.f);
    hit.setTime(t_ns);
    hit.setType(0);
    hit.setPosition({ X * kCm2Mm, Y * kCm2Mm, Z * kCm2Mm });
  }

  // sub-bank 11 = HOF forward.
  for (int lcur = ph::LQ(ltead - 11); lcur > 0; lcur = ph::LQ(lcur)) {
    const float X = ph::Q(lcur + 5);
    const float Y = ph::Q(lcur + 6);
    const float Z = ph::Q(lcur + 7);
    auto hit = hof_col.create();
    hit.setEnergy(0.f);
    hit.setEnergyError(0.f);
    hit.setTime(0.f);            // HOF time not decoded — see header
    hit.setType(0);
    hit.setPosition({ X * kCm2Mm, Y * kCm2Mm, Z * kCm2Mm });
  }

  put(std::move(tof_col), "TEAD", "TOFHits");
  put(std::move(hof_col), "TEAD", "HOFHits");
}

}  // namespace delphi_edm4hep::tead_fdst
