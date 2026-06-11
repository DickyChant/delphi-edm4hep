// EventWriter — implementation.
//
// Reads per-event scalars from the SKELANA / PHDST commons populated
// by PSBEG and writes them into the Frame as named parameters under
// "<source_tag>_EVT_*". No bank walking — pure common-block reads.

#include "delphi_edm4hep/Event/Event.h"

#include "phdst/phciii.hpp"
#include "skelana/pscbsp.hpp"
#include "skelana/pscevt.hpp"

// PHGEN BPILOT subroutine (current event's solenoid B in Tesla,
// curvature-to-momentum factor in GeV/cm). No header wrapper.
extern "C" void bpilot_(float* btesla, float* bgevcm);

namespace ph = phdst;
namespace sk = skelana;

namespace delphi_edm4hep::event {

void EventWriter::emit() {
  constexpr float kCm2Mm = 10.0f;

  // PHCIII run-level identifiers.
  putParameter("EVT", "runNumber",  ph::IIIRUN);
  putParameter("EVT", "eventNumber", ph::IIIEVT);
  putParameter("EVT", "fileSeq",    ph::IIFILE);
  putParameter("EVT", "date",       ph::IIIDAT);   // yymmdd
  putParameter("EVT", "time",       ph::IIITIM);   // hhmmss
  putParameter("EVT", "fillNumber", ph::IIFILL);
  putParameter("EVT", "experiment", ph::IIIEXP);

  // PSCEVT hadronic-event tag + multiplicities + total energies.
  putParameter("EVT", "dstVersion",     sk::ISVER);
  putParameter("EVT", "hadronicTagTeam4", sk::IHAD4);
  putParameter("EVT", "nChargedTeam4",  sk::NCTR4);
  putParameter("EVT", "nCharged",       sk::NCTRK);
  putParameter("EVT", "nNeutral",       sk::NNTRK);
  putParameter("EVT", "ECMS",           sk::ECMAS);
  putParameter("EVT", "EChargedTotal",  sk::ECHAR);
  putParameter("EVT", "ENeutralEM",     sk::EMNEU);
  putParameter("EVT", "ENeutralHad",    sk::EHNEU);

  // PSCBSP beam-spot position (cm) -> mm.
  putParameter("EVT", "BeamSpotX",      sk::XYZBS(1) * kCm2Mm);
  putParameter("EVT", "BeamSpotY",      sk::XYZBS(2) * kCm2Mm);
  putParameter("EVT", "BeamSpotZ",      sk::XYZBS(3) * kCm2Mm);
  putParameter("EVT", "BeamSpotSigmaX", sk::DXYZBS(1) * kCm2Mm);
  putParameter("EVT", "BeamSpotSigmaY", sk::DXYZBS(2) * kCm2Mm);
  putParameter("EVT", "BeamSpotSigmaZ", sk::DXYZBS(3) * kCm2Mm);
  putParameter("EVT", "BeamSpotErrorCode", sk::IERRBS);

  // Per-event B-field (Tesla) + GeV/cm conversion factor.
  // pT [GeV/c] = bgevcm / |omega_DELPHI[1/cm]|.
  float btesla = 0.f, bgevcm = 0.f;
  bpilot_(&btesla, &bgevcm);
  putParameter("EVT", "BField",         btesla);
  putParameter("EVT", "BFieldGevPerCm", bgevcm);
}

}  // namespace delphi_edm4hep::event
