// TrackHybrid domain — pass-2 hybrid writer.
//
// Re-emits the sDST tracks under the fDST tag so the pass-2 PID writers have
// a track collection to point at, and links each one to the track elements
// reconstructed from the matched fDST PA:
//
//   <tag>_TRAC_Tracks   TrackCollection, one per sDST Track, cloned with its
//                       AtIP state, plus `tracks` / `trackerHits` relations
//                       into the <tag>_TE*_Segments and
//                       <tag>_TEVF_TrackElementPlane collections
//
// The track elements themselves are decoded by TrackElementsWriter, which
// must run first.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::track_hybrid {

class TrackHybridWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::track_hybrid
