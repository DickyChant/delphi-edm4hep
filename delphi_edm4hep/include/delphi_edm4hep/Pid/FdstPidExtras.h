// FdstPidExtras domain — pass-2 only.
//
// Three thin fDST-only PA diagnostic modules that are genuinely
// per-particle scalar/quality summaries, so ParticleID is the correct
// edm4hep home (companions to the corresponding sDST PID collections).
// Grouped into one writer because each is a handful of words.
//
// Emits (all ParticleIDCollection, setParticle -> matched sDST Particle
// via ctx_.fdst_pa_to_sdst_particle):
//   fDST_MU_MuonChambers   (algType=4)  PA.MU   raw muon-chamber refit
//     params = [det, nlay, ndof, chi2, x_first, y_first, hit_pattern,
//               chi2_alone, x_extrap, y_extrap, theta_extrap, phi_extrap]
//     (positions in cm, angles in rad — native bank units)
//   fDST_EL_ElectronExtra  (algType=5)  PA.EL   electron extra-module hdr
//     params = [detector_id, n_showers]
//   fDST_TDID_DriftCalib   (algType=17) PA.TDID ID drift-time calibration
//     params = [jet_sector, n_valid_wires, drift_sum]
//
// These correspond to the legacy ParticleID_MU / _EL / _TDID modules.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::fdst_pid_extras {

class FdstPidExtrasWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::fdst_pid_extras
