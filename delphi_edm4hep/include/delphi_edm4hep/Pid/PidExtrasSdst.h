// PidExtrasSdst domain — pass-1 only.
//
// VECP-track-indexed SKELANA PID commons that carry information beyond
// the four standard pass-1 PID collections. Bound to the Particle via
// ctx_.tracking->vecp_to_particle (same idiom as ParticleIdWriter).
//
// Emits (ParticleIDCollection, setParticle -> sDST_MAIN_Particles):
//   sDST_HAID_AltTags   (algType=40)  alternate hadron-ID tag tables
//     params = KHAIDN(1..4) KHAIDT(1..4) KHAIDR(1..6) KHAIDE(1..6)
//              KHAIDC(1..6)   [26 integer tags, −1=no info / 0..3 tightness]
//   sDST_HAID_dEdxVD    (algType=7)   VD-only dE/dx (PSCDEX VD slots)
//     params = [QDEDX(6)=VD dE/dx, KDEDX(7)=n VD hits]; emitted if nVD>0
//   sDST_PHOT_Pi0ID     (algType=111) π⁰→γγ HPCANA fit (PSCPI0, 26 fields)
//     params = QPI0/KPI0(1..26); emitted if the fit mass QPI0(1)>0
//
// All three are charged-track commons except Pi0 which is scanned over
// the full VECP range (π⁰ candidates can sit on neutral PAs).

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::pid_extras_sdst {

class PidExtrasSdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::pid_extras_sdst
