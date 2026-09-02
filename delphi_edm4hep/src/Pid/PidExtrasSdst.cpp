// PidExtrasSdstWriter — pass-1 implementation.
//
// Headers (skelana/*.hpp): pschdn (KHAIDN 1..4 + KHAIDT 1..4),
// pschdr (KHAIDR 1..6), pschde (KHAIDE 1..6), pschdc (KHAIDC 1..6),
// pscdex (QDEDX(6)=VD dE/dx, KDEDX(7)=n VD hits), pscpi0 (26 fields,
// int at 5/6/20/21/23, float elsewhere).

#include "delphi_edm4hep/Pid/PidExtrasSdst.h"

#include "phdst/uxcom.hpp"      // IQ
#include "phdst/uxlink.hpp"     // LDTOP
#include "skelana/pscdex.hpp"
#include "skelana/pschdc.hpp"
#include "skelana/pschde.hpp"
#include "skelana/pschdn.hpp"
#include "skelana/pschdr.hpp"
#include "skelana/pscpi0.hpp"
#include "skelana/pscvec.hpp"   // LVPART, NVECP, NCVECP

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/ParticleIDCollection.h>

#include <algorithm>
#include <cstdint>
#include <initializer_list>

namespace ph = phdst;
namespace sk = skelana;

namespace delphi_edm4hep::pid_extras_sdst {

namespace {

// algorithmType constants; 1..7 and 111 are assigned in ParticleId.cpp.
constexpr std::int32_t kAlgoDedxVD  = 7;
constexpr std::int32_t kAlgoXnewtag = 41;
constexpr std::int32_t kAlgoXnewpro = 42;
constexpr std::int32_t kAlgoRprodo  = 43;
constexpr std::int32_t kAlgoRprode  = 44;
constexpr std::int32_t kAlgoRproco  = 45;
constexpr std::int32_t kAlgoPi0     = 111;

// Value left in a tag SKELANA had no information for.
constexpr int kNoTag = -1;

// PXDST version at or above which SKELANA runs RPRODE in place of RPRODO.
constexpr int kRprodeMinPxdst = 333;

// PSCPI0 fields stored as integers (1-based field index); the rest float.
bool pi0FieldIsInt(int f) {
  return f == 5 || f == 6 || f == 20 || f == 21 || f == 23;
}

}  // namespace

void PidExtrasSdstWriter::emit()
{
  // RPRODE superseded RPRODO at PXDST version 333. Both fill KHAIDE; SKELANA
  // runs whichever matches the version word of the event, so the collection is
  // named for the one that ran.
  const bool rprode = ph::LDTOP > 0
                   && ph::IQ(ph::LDTOP + 3) >= kRprodeMinPxdst;

  edm4hep::ParticleIDCollection xnewtagCol, xnewproCol, dedxCol, rprocoCol,
                                dedxVdCol, pi0Col;

  // Emitted on every event, filled or not, so that the collection set of the
  // output is the same in every event.
  auto putAll = [&] {
    put(std::move(xnewtagCol), "XNEWTAG", "RichTags",     Provenance::Derived);
    put(std::move(xnewproCol), "XNEWPRO", "RichTags",     Provenance::Derived);
    put(std::move(dedxCol), rprode ? "RPRODE" : "RPRODO", "DedxTags",
        Provenance::Derived);
    put(std::move(rprocoCol),  "RPROCO",  "CombinedTags", Provenance::Derived);
    put(std::move(dedxVdCol),  "HAID",    "dEdxVD",       Provenance::Transcribed);
    put(std::move(pi0Col),     "PHOT",    "Pi0ID",        Provenance::Transcribed);
  };

  if (!ctx_.tracking) { putAll(); return; }
  const auto& tracking = *ctx_.tracking;

  // Attach a PID row to the Particle built from the same VECP slot.
  auto bind = [&](edm4hep::MutableParticleID pid, int i) {
    if (i >= static_cast<int>(tracking.vecp_to_particle.size())) return;
    const int p = tracking.vecp_to_particle[i];
    if (p >= 0) pid.setParticle(tracking.particle_handles[p]);
  };

  // Add one row of tags for track i. SKELANA leaves -1 in every tag it had no
  // information for, so a row with nothing but -1 carries no result and is
  // dropped.
  auto putTags = [&](edm4hep::ParticleIDCollection& coll, std::int32_t algo,
                     std::initializer_list<int> tags, int i) {
    if (std::all_of(tags.begin(), tags.end(),
                    [](int t) { return t == kNoTag; })) return;
    auto pid = coll.create();
    pid.setAlgorithmType(algo);
    for (int t : tags) pid.addToParameters(static_cast<float>(t));
    bind(pid, i);
  };

  // PSCVEC orders charged particles first; these commons are charged-only.
  for (int i = sk::LVPART; i <= sk::NCVECP; ++i) {
    if (i >= static_cast<int>(tracking.vecp_to_particle.size())) break;
    if (tracking.vecp_to_particle[i] < 0) continue;

    // RICH gas and liquid tags from the Cherenkov angle, photon count and
    // quality flag, with no outer-detector or FCB requirement. KHAIDT holds
    // the track-quality acceptance belonging to each KHAIDN tag.
    putTags(xnewtagCol, kAlgoXnewtag,
            {sk::KHAIDN(1, i), sk::KHAIDN(2, i), sk::KHAIDN(3, i), sk::KHAIDN(4, i),
             sk::KHAIDT(1, i), sk::KHAIDT(2, i), sk::KHAIDT(3, i), sk::KHAIDT(4, i)}, i);

    // RICH tags from the RIBMEAN gas and liquid probabilities, with no
    // tracking requirement. KHAIDR(6) is a selection flag: bit 1 liquid OK,
    // bit 2 gas OK.
    putTags(xnewproCol, kAlgoXnewpro,
            {sk::KHAIDR(1, i), sk::KHAIDR(2, i), sk::KHAIDR(3, i),
             sk::KHAIDR(4, i), sk::KHAIDR(5, i), sk::KHAIDR(6, i)}, i);

    // Tags from the TPC dE/dx probabilities. KHAIDE(6) is 1 when the track had
    // more than 30 TPC wires and sat within 2.5 s.d. of a hypothesis.
    putTags(dedxCol, rprode ? kAlgoRprode : kAlgoRprodo,
            {sk::KHAIDE(1, i), sk::KHAIDE(2, i), sk::KHAIDE(3, i),
             sk::KHAIDE(4, i), sk::KHAIDE(5, i), sk::KHAIDE(6, i)}, i);

    // Tags from the RICH and dE/dx probabilities combined. KHAIDC(6) is the
    // selection flag of both: bit 1 liquid OK, bit 2 gas OK, bit 3 TPC OK.
    putTags(rprocoCol, kAlgoRproco,
            {sk::KHAIDC(1, i), sk::KHAIDC(2, i), sk::KHAIDC(3, i),
             sk::KHAIDC(4, i), sk::KHAIDC(5, i), sk::KHAIDC(6, i)}, i);

    // VD-only dE/dx, distinct from the TPC dE/dx in sDST_HAID_dEdx.
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

  putAll();
}

}  // namespace delphi_edm4hep::pid_extras_sdst
