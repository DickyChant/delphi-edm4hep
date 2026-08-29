// EventWriter — implementation.
//
// Reads per-event scalars from the SKELANA / PHDST commons populated by PSBEG
// and writes them into the Frame as named parameters under "<source>_EVT_*".
// No bank walking — pure common-block reads.
//
// The parameters fall into three groups by origin, declared separately below:
// values copied from the DST pilot record, values SKELANA counts or sums for
// itself, and the beam spot, which comes from an external database rather
// than from the DST at all.

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

  // Pilot-record words, written when the DST was produced.
  auto stored = parameters("EVT", Provenance::Transcribed);
  stored("runNumber",   ph::IIIRUN);
  stored("eventNumber", ph::IIIEVT);
  stored("fileSeq",     ph::IIFILE);
  stored("date",        ph::IIIDAT);   // yymmdd
  stored("time",        ph::IIITIM);   // hhmmss
  stored("fillNumber",  ph::IIFILL);
  stored("experiment",  ph::IIIEXP);
  stored("dstVersion",  sk::ISVER);

  // Centre-of-mass energy from the DANA pilot blocklet. SKELANA substitutes
  // 91.250 GeV when that blocklet is absent, which at LEP2 would be wrong by
  // more than a factor of two; check BeamSpotErrorCode and the energy itself
  // before relying on it.
  stored("ECMS", sk::ECMAS);

  // Per-event solenoid field and the curvature-to-momentum factor, both from
  // the pilot record. pT [GeV/c] = BFieldGevPerCm / |omega_DELPHI [1/cm]|.
  float btesla = 0.f, bgevcm = 0.f;
  bpilot_(&btesla, &bgevcm);
  stored("BField",         btesla);
  stored("BFieldGevPerCm", bgevcm);

  // Multiplicities and summed energies counted by SKELANA over the PA chain
  // under cuts hard-coded in PSHEVT — a momentum, track-length, impact-
  // parameter and polar-angle selection independent of IFLCUT and of the
  // LVLOCK track selection. Two events with the same nCharged can therefore
  // disagree with a count made from MAIN_Particles and LVLOCK.
  auto counted = parameters("EVT", Provenance::Derived);
  counted("hadronicTagTeam4", sk::IHAD4);
  counted("nChargedTeam4",    sk::NCTR4);
  counted("nCharged",         sk::NCTRK);
  counted("nNeutral",         sk::NNTRK);
  counted("EChargedTotal",    sk::ECHAR);
  counted("ENeutralEM",       sk::EMNEU);
  counted("ENeutralHad",      sk::EHNEU);

  // Beam spot from the per-processing database under $DELPHI_DAT, selected by
  // the DSTQID tag and looked up per run and cartridge — not from the DST.
  // For simulation it is instead the generated interaction point plus a
  // Gaussian smear, so it follows the event rather than describing a beam.
  auto beamspot = parameters("EVT", Provenance::Derived);
  beamspot("BeamSpotX",      sk::XYZBS(1) * kCm2Mm);
  beamspot("BeamSpotY",      sk::XYZBS(2) * kCm2Mm);
  beamspot("BeamSpotZ",      sk::XYZBS(3) * kCm2Mm);
  beamspot("BeamSpotSigmaX", sk::DXYZBS(1) * kCm2Mm);
  beamspot("BeamSpotSigmaY", sk::DXYZBS(2) * kCm2Mm);
  beamspot("BeamSpotSigmaZ", sk::DXYZBS(3) * kCm2Mm);
  beamspot("BeamSpotErrorCode", sk::IERRBS);
}

}  // namespace delphi_edm4hep::event
