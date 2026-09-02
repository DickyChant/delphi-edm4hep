// MainHybridWriter — pass-2 implementation.

#include "delphi_edm4hep/Tracking/MainHybrid.h"

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableReconstructedParticle.h>
#include <edm4hep/MutableVertex.h>
#include <edm4hep/ReconstructedParticleCollection.h>
#include <edm4hep/TrackCollection.h>
#include <edm4hep/VertexCollection.h>

#include <cstddef>
#include <string>

namespace delphi_edm4hep::main_hybrid {

namespace {

// Clone the scalar (non-relation) fields of a RecoParticle.
void cloneScalars(edm4hep::MutableReconstructedParticle dst,
                  const edm4hep::ReconstructedParticle& src) {
  dst.setPDG           (src.getPDG());
  dst.setEnergy        (src.getEnergy());
  dst.setMomentum      (src.getMomentum());
  dst.setReferencePoint(src.getReferencePoint());
  dst.setCharge        (src.getCharge());
  dst.setMass          (src.getMass());
  dst.setGoodnessOfPID (src.getGoodnessOfPID());
  dst.setCovMatrix     (src.getCovMatrix());
}

// Clone the scalar fields of a Vertex.
void cloneScalars(edm4hep::MutableVertex dst, const edm4hep::Vertex& src) {
  dst.setType         (src.getType());
  dst.setChi2         (src.getChi2());
  dst.setNdf          (src.getNdf());
  dst.setPosition     (src.getPosition());
  dst.setCovMatrix    (src.getCovMatrix());
  dst.setAlgorithmType(src.getAlgorithmType());
  for (std::size_t k = 0; k < src.parameters_size(); ++k) {
    dst.addToParameters(src.getParameters(k));
  }
}

// Clone a Vertex collection (scalars only — caller re-points the
// particles relation via the fDST particle map).
void cloneVerticesWithRepointedParticles(
    const edm4hep::VertexCollection& src,
    edm4hep::VertexCollection&       dst,
    const edm4hep::ReconstructedParticleCollection& fdst_particles)
{
  const std::size_t n_fdst = fdst_particles.size();
  for (const auto& sv : src) {
    auto dv = dst.create();
    cloneScalars(dv, sv);
    for (const auto& sp : sv.getParticles()) {
      const auto idx = sp.getObjectID().index;
      if (idx >= 0 && static_cast<std::size_t>(idx) < n_fdst) {
        dv.addToParticles(fdst_particles[idx]);
      }
    }
  }
}

}  // namespace

void MainHybridWriter::emit()
{
  const auto& sdst_particles =
    frame_.get<edm4hep::ReconstructedParticleCollection>(sdstName("MAIN", "Particles"));
  const auto& fdst_tracks =
    frame_.get<edm4hep::TrackCollection>("fDST_TRAC_Tracks");
  const std::size_t n_fdst_tracks = fdst_tracks.size();

  // Calorimeter showers. ShowerHybridWriter runs BEFORE this writer and
  // has already cloned the sDST EM/HAD neutral showers into the fDST_*
  // collections (1:1 order). The Particle→Cluster relation lives on the
  // particle, so it must be re-pointed here while main_out is mutable
  // (it cannot be wired from the cluster side after the fact). sDST
  // particles reference both sDST_EMNC and sDST_HCNC, so disambiguate by
  // the reference's collectionID.
  const auto& fdst_emnc = frame_.get<edm4hep::ClusterCollection>("fDST_EMNC_Showers");
  const auto& fdst_hcnc = frame_.get<edm4hep::ClusterCollection>("fDST_HCNC_Showers");
  const auto  emnc_id   = frame_.get<edm4hep::ClusterCollection>(sdstName("EMNC", "Showers")).getID();
  const auto  hcnc_id   = frame_.get<edm4hep::ClusterCollection>(sdstName("HCNC", "Showers")).getID();
  const std::size_t n_emnc = fdst_emnc.size();
  const std::size_t n_hcnc = fdst_hcnc.size();

  // Phase 1: create fDST_MAIN_Particles with scalars only (no relations
  // yet — subParticles need the full collection to exist first).
  edm4hep::ReconstructedParticleCollection main_out;
  for (const auto& sp : sdst_particles) {
    auto dp = main_out.create();
    cloneScalars(dp, sp);
  }

  // Phase 2: wire relations. Tracks re-point to fDST_TRAC_Tracks
  // (sDST_TRAC_Tracks[i] ↔ fDST_TRAC_Tracks[i], 1:1 order). Clusters
  // re-point to the fDST EMNC/HCNC shower clones (also 1:1 order).
  // ParticleIDs are NOT wired here — they are stored on the ParticleID
  // side, so PidHybridWriter re-points them via setParticle() after this
  // writer runs. SubParticles (e.g. V0 daughters listed on a parent
  // particle) re-point to the newly-created fDST_MAIN_Particles entries.
  for (std::size_t i = 0; i < sdst_particles.size(); ++i) {
    auto dp = main_out[i];
    const auto& sp = sdst_particles[i];
    for (const auto& st : sp.getTracks()) {
      const auto idx = st.getObjectID().index;
      if (idx >= 0 && static_cast<std::size_t>(idx) < n_fdst_tracks) {
        dp.addToTracks(fdst_tracks[idx]);
      }
    }
    for (const auto& sc : sp.getClusters()) {
      const auto oid = sc.getObjectID();
      if (oid.collectionID == emnc_id &&
          oid.index >= 0 && static_cast<std::size_t>(oid.index) < n_emnc) {
        dp.addToClusters(fdst_emnc[oid.index]);
      } else if (oid.collectionID == hcnc_id &&
                 oid.index >= 0 && static_cast<std::size_t>(oid.index) < n_hcnc) {
        dp.addToClusters(fdst_hcnc[oid.index]);
      }
    }
    for (const auto& sub : sp.getParticles()) {
      const auto idx = sub.getObjectID().index;
      if (idx >= 0 && static_cast<std::size_t>(idx) < main_out.size()) {
        dp.addToParticles(main_out[idx]);
      }
    }
  }

  // Vertex cascade. Each of PV / Vertices / V0 / PHC is a separate
  // VertexCollection; re-emit with addToParticles re-pointed.
  edm4hep::VertexCollection pv_out;
  edm4hep::VertexCollection vtx_out;
  edm4hep::VertexCollection v0_out;
  edm4hep::VertexCollection phc_out;

  const auto& sdst_pv  = frame_.get<edm4hep::VertexCollection>(sdstName("PV", "PrimaryVertex"));
  const auto& sdst_vtx = frame_.get<edm4hep::VertexCollection>(sdstName("PV", "Vertices"));
  const auto& sdst_v0  = frame_.get<edm4hep::VertexCollection>(sdstName("V0", "V0Candidates"));
  const auto& sdst_phc = frame_.get<edm4hep::VertexCollection>(sdstName("PHC", "PhotonConversions"));

  cloneVerticesWithRepointedParticles(sdst_pv,  pv_out,  main_out);
  cloneVerticesWithRepointedParticles(sdst_vtx, vtx_out, main_out);
  cloneVerticesWithRepointedParticles(sdst_v0,  v0_out,  main_out);
  cloneVerticesWithRepointedParticles(sdst_phc, phc_out, main_out);

  put(std::move(main_out), "MAIN", "Particles", Provenance::Derived);
  put(std::move(pv_out),   "PV",   "PrimaryVertex", Provenance::Transcribed);
  put(std::move(vtx_out),  "PV",   "Vertices", Provenance::Transcribed);
  put(std::move(v0_out),   "V0",   "V0Candidates", Provenance::Transcribed);
  put(std::move(phc_out),  "PHC",  "PhotonConversions", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::main_hybrid
