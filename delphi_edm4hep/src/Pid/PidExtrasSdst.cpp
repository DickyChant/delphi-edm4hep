// PidExtrasSdstWriter — pass-1 implementation.
//
// Headers (skelana/*.hpp): pschdn (KHAIDN 1..4 + KHAIDT 1..4),
// pschdr (KHAIDR 1..6), pschde (KHAIDE 1..6), pschdc (KHAIDC 1..6),
// pscdex (QDEDX(6)=VD dE/dx, KDEDX(7)=n VD hits), pscpi0 (26 fields,
// int at 5/6/20/21/23, float elsewhere).

#include "delphi_edm4hep/Pid/PidExtrasSdst.h"

#include "skelana/pscdex.hpp"
#include "skelana/pschdc.hpp"
#include "skelana/pschde.hpp"
#include "skelana/pschdn.hpp"
#include "skelana/pschdr.hpp"
#include "skelana/pscpi0.hpp"
#include "skelana/pscvec.hpp"   // LVPART, NVECP, NCVECP

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>

#include <cstdint>

namespace sk = skelana;

namespace delphi_edm4hep::pid_extras_sdst {

namespace {
constexpr std::int32_t kAlgoAltTags = 40;
constexpr std::int32_t kAlgoDedxVD  = 7;
constexpr std::int32_t kAlgoPi0     = 111;

// PSCPI0 fields stored as integers (1-based field index); the rest float.
bool pi0FieldIsInt(int f) {
  return f == 5 || f == 6 || f == 20 || f == 21 || f == 23;
}
}  // namespace

void PidExtrasSdstWriter::emit()
{
  edm4hep::ParticleIDCollection altCol;
  edm4hep::ParticleIDCollection dedxVdCol;
  edm4hep::ParticleIDCollection pi0Col;

  if (!ctx_.tracking) {
    put(std::move(altCol),    "HAID", "AltTags", Provenance::Derived);
    put(std::move(dedxVdCol), "HAID", "dEdxVD", Provenance::Transcribed);
    put(std::move(pi0Col),    "PHOT", "Pi0ID", Provenance::Transcribed);
    return;
  }
  const auto& tracking = *ctx_.tracking;

  auto bind = [&](edm4hep::MutableParticleID pid, int i) -> bool {
    if (i >= static_cast<int>(tracking.vecp_to_particle.size())) return false;
    const int p = tracking.vecp_to_particle[i];
    if (p < 0) return false;
    pid.setParticle(tracking.particle_handles[p]);
    return true;
  };

  // Charged-track commons: alternate hadron tags + VD-only dE/dx.
  for (int i = sk::LVPART; i <= sk::NCVECP; ++i) {
    if (i >= static_cast<int>(tracking.vecp_to_particle.size())) break;
    if (tracking.vecp_to_particle[i] < 0) continue;

    // Alternate hadron-ID tag tables (emit if any table has info).
    const bool anyTag =
      sk::NHAIDN > 0 || sk::NHAIDR > 0 || sk::NHAIDE > 0 || sk::NHAIDC > 0;
    if (anyTag) {
      auto pid = altCol.create();
      pid.setAlgorithmType(kAlgoAltTags);
      for (int k = 1; k <= 4; ++k) pid.addToParameters(static_cast<float>(sk::KHAIDN(k, i)));
      for (int k = 1; k <= 4; ++k) pid.addToParameters(static_cast<float>(sk::KHAIDT(k, i)));
      for (int k = 1; k <= 6; ++k) pid.addToParameters(static_cast<float>(sk::KHAIDR(k, i)));
      for (int k = 1; k <= 6; ++k) pid.addToParameters(static_cast<float>(sk::KHAIDE(k, i)));
      for (int k = 1; k <= 6; ++k) pid.addToParameters(static_cast<float>(sk::KHAIDC(k, i)));
      bind(pid, i);
    }

    // VD-only dE/dx (distinct from the TPC dE/dx in sDST_HAID_dEdx).
    const int nVD = sk::KDEDX(7, i);
    if (nVD > 0) {
      auto pid = dedxVdCol.create();
      pid.setAlgorithmType(kAlgoDedxVD);
      pid.addToParameters(sk::QDEDX(6, i));            // VD dE/dx
      pid.addToParameters(static_cast<float>(nVD));    // n VD hits
      bind(pid, i);
    }
  }

  // π⁰→γγ HPCANA fit — scan the full VECP range; emit where a fit exists.
  if (sk::NPI0 > 0) {
    for (int i = sk::LVPART; i <= sk::NVECP; ++i) {
      if (i >= static_cast<int>(tracking.vecp_to_particle.size())) break;
      if (tracking.vecp_to_particle[i] < 0) continue;
      if (sk::QPI0(1, i) <= 0.f) continue;             // no fit mass
      auto pid = pi0Col.create();
      pid.setAlgorithmType(kAlgoPi0);
      for (int f = 1; f <= 26; ++f) {
        pid.addToParameters(pi0FieldIsInt(f)
                              ? static_cast<float>(sk::KPI0(f, i))
                              : sk::QPI0(f, i));
      }
      bind(pid, i);
    }
  }

  put(std::move(altCol),    "HAID", "AltTags", Provenance::Derived);
  put(std::move(dedxVdCol), "HAID", "dEdxVD", Provenance::Transcribed);
  put(std::move(pi0Col),    "PHOT", "Pi0ID", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::pid_extras_sdst
