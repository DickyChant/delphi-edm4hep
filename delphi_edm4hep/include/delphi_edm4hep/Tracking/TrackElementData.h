// TrackElementData.h — value type passed through EventContext.
// Separate from TrackElements.h so CollectionWriter.h can include this
// without pulling in the writer class.

#pragma once

#include <edm4hep/Track.h>
#include <edm4hep/TrackerHitPlane.h>

#include <vector>

namespace delphi_edm4hep::track_elements {

// Output of TrackElementsWriter::emit(), indexed by PA-walk index.
// TrackingWriter reads it to link each mother track to the track elements
// reconstructed from the same PA, while the mother is still mutable.
struct Output {
  std::vector<std::vector<edm4hep::Track>>           pa_to_segments;
  std::vector<std::vector<edm4hep::TrackerHitPlane>> pa_to_plane_hits;
};

}  // namespace delphi_edm4hep::track_elements
