// EltrSdst domain — pass-1 only.
//
// PA.ELTR (label 28) is the electron-refitted track: a perigee
// (d0, z0, theta, phi, 1/R) + 15-element lower-tri weight matrix with
// the SAME layout as PA.TRAC. A re-fit track is properly a Track, so we
// emit it as a TrackCollection (reusing delphi_edm4hep::perigee), rather
// than a flat 5-float ParticleID dump.
//
// Emits:
//   sDST_ELTR_RefitTracks    TrackCollection
//     one Track per PA carrying an ELTR bank; AtIP TrackState with the
//     5x5 helix-basis cov pushed forward from the weight matrix.
//   sDST_ELTR_RefitTracks_ParticleIndex  UserDataCollection<int32>
//     0-based sDST_MAIN_Particles index for each refit track (-1 if the
//     owning PA produced no Particle). Preserves the electron-candidate
//     association without re-pointing the already-emitted (immutable)
//     Particle.tracks relation.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::eltr_sdst {

class EltrSdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::eltr_sdst
