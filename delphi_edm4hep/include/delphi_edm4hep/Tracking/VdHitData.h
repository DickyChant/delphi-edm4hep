// VdHitData.h — value type passed through EventContext.
// Separate from VdHits.h so CollectionWriter.h can include this without
// pulling in the writer class.

#pragma once

#include <edm4hep/TrackerHit3D.h>

#include <vector>

namespace delphi_edm4hep::vd_hits {

// Output of VdHitsWriter::emit(): the associated Vertex-Detector hits,
// grouped by the SKELANA charged-track ordinal they belong to, so the track
// writer can link each track to its own hits while the track is still
// mutable.
//
//   vecp_to_hits[j] : hits on charged VECP track j (1..NCVECP). Index 0 is
//                     unused so the ordinal indexes directly. Empty for a
//                     track with no associated hits.
struct Output {
  std::vector<std::vector<edm4hep::TrackerHit3D>> vecp_to_hits;
};

}  // namespace delphi_edm4hep::vd_hits
