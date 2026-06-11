// PidHybridWriter — pass-2 implementation.

#include "delphi_edm4hep/Pid/PidHybrid.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/MutableRecDqdx.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/RecDqdxCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <edm4hep/TrackCollection.h>

#include <cstddef>
#include <string>

namespace delphi_edm4hep::pid_hybrid {

namespace {

// Clone a ParticleID collection, re-pointing setParticle() at the
// matching fDST_MAIN_Particles entry (by 1:1 identity index).
void clonePidWithRepoint(
    const edm4hep::ParticleIDCollection& src,
    edm4hep::ParticleIDCollection&       dst,
    const edm4hep::ReconstructedParticleCollection& fdst_particles)
{
  const std::size_t n_fdst = fdst_particles.size();
  for (const auto& sp : src) {
    auto dp = dst.create();
    dp.setType         (sp.getType());
    dp.setPDG          (sp.getPDG());
    dp.setAlgorithmType(sp.getAlgorithmType());
    dp.setLikelihood   (sp.getLikelihood());
    for (std::size_t k = 0; k < sp.parameters_size(); ++k) {
      dp.addToParameters(sp.getParameters(k));
    }
    const auto& src_part = sp.getParticle();
    const auto  idx = src_part.getObjectID().index;
    if (idx >= 0 && static_cast<std::size_t>(idx) < n_fdst) {
      dp.setParticle(fdst_particles[idx]);
    }
  }
}

}  // namespace

void PidHybridWriter::emit()
{
  const auto& fdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>("fDST_MAIN_Particles");
  const auto& fdst_tracks =
    frame_.get<edm4hep::TrackCollection>("fDST_TRAC_Tracks");
  const std::size_t n_fdst_tracks = fdst_tracks.size();

  edm4hep::ParticleIDCollection haid_out, muid_out, elid_out, dedx_out;
  clonePidWithRepoint(
    frame_.get<edm4hep::ParticleIDCollection>("sDST_HAID_HadronID"),
    haid_out, fdst_particles);
  clonePidWithRepoint(
    frame_.get<edm4hep::ParticleIDCollection>("sDST_MUID_MuonID"),
    muid_out, fdst_particles);
  clonePidWithRepoint(
    frame_.get<edm4hep::ParticleIDCollection>("sDST_ELID_ElectronID"),
    elid_out, fdst_particles);
  clonePidWithRepoint(
    frame_.get<edm4hep::ParticleIDCollection>("sDST_HAID_dEdx"),
    dedx_out, fdst_particles);

  // RecDqdx: scalar (Quantity DQdx) + setTrack relation.
  edm4hep::RecDqdxCollection dqdx_out;
  const auto& sdst_dqdx =
    frame_.get<edm4hep::RecDqdxCollection>("sDST_HAID_dEdx_RecDqdx");
  for (const auto& sq : sdst_dqdx) {
    auto dq = dqdx_out.create();
    dq.setDQdx(sq.getDQdx());
    const auto& src_trk = sq.getTrack();
    const auto  tidx = src_trk.getObjectID().index;
    if (tidx >= 0 && static_cast<std::size_t>(tidx) < n_fdst_tracks) {
      dq.setTrack(fdst_tracks[tidx]);
    }
  }

  put(std::move(haid_out), "HAID", "HadronID");
  put(std::move(muid_out), "MUID", "MuonID");
  put(std::move(elid_out), "ELID", "ElectronID");
  put(std::move(dedx_out), "HAID", "dEdx");
  put(std::move(dqdx_out), "HAID", "dEdx_RecDqdx");
}

}  // namespace delphi_edm4hep::pid_hybrid
