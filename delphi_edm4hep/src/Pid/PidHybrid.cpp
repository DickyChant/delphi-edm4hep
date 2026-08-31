// PidHybridWriter — pass-2 implementation.

#include "delphi_edm4hep/Pid/PidHybrid.h"

#include <edm4hep/MutableParticleID.h>
#include <edm4hep/MutableRecDqdx.h>
#include <edm4hep/ParticleIDCollection.h>
#include <edm4hep/RecDqdxCollection.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <edm4hep/TrackCollection.h>

#include <cstddef>
#include <stdexcept>
#include <string>

namespace delphi_edm4hep::pid_hybrid {

namespace {

// dE/dx collections are named for the routine that produced them, and which
// routine runs depends on the DST version (ParticleId.cpp), so exactly one of
// these is on the pass-1 frame. Resolve it by presence and keep the name.
constexpr const char* kDedxAlgorithms[] = {"BBDXGET", "GETDEDX"};

std::string dedxAlgorithm(const podio::Frame& frame) {
  for (const char* algo : kDedxAlgorithms) {
    if (frame.get(std::string("sDST_") + algo + "_Dedx")) return algo;
  }
  throw std::runtime_error(
      "pass-1 frame carries no dE/dx collection; expected sDST_BBDXGET_Dedx"
      " or sDST_GETDEDX_Dedx");
}

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

  const std::string dedx_algo = dedxAlgorithm(frame_);
  const std::string dedx_name = "sDST_" + dedx_algo + "_Dedx";

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
    frame_.get<edm4hep::ParticleIDCollection>(dedx_name),
    dedx_out, fdst_particles);

  // RecDqdx: scalar (Quantity DQdx) + setTrack relation.
  edm4hep::RecDqdxCollection dqdx_out;
  const auto& sdst_dqdx =
    frame_.get<edm4hep::RecDqdxCollection>(dedx_name + "RecDqdx");
  for (const auto& sq : sdst_dqdx) {
    auto dq = dqdx_out.create();
    dq.setDQdx(sq.getDQdx());
    const auto& src_trk = sq.getTrack();
    const auto  tidx = src_trk.getObjectID().index;
    if (tidx >= 0 && static_cast<std::size_t>(tidx) < n_fdst_tracks) {
      dq.setTrack(fdst_tracks[tidx]);
    }
  }

  put(std::move(haid_out), "HAID", "HadronID", Provenance::Transcribed);
  put(std::move(muid_out), "MUID", "MuonID", Provenance::Transcribed);
  put(std::move(elid_out), "ELID", "ElectronID", Provenance::Transcribed);
  put(std::move(dedx_out), dedx_algo, "Dedx", Provenance::Derived);
  put(std::move(dqdx_out), dedx_algo, "DedxRecDqdx", Provenance::Derived);
}

}  // namespace delphi_edm4hep::pid_hybrid
