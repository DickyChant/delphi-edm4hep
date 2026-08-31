// TrackHybridWriter — pass-2 implementation.

#include "delphi_edm4hep/Tracking/TrackHybrid.h"

#include <edm4hep/MutableTrack.h>
#include <edm4hep/TrackCollection.h>

#include <cstddef>
#include <vector>

namespace delphi_edm4hep::track_hybrid {

namespace {

// Clone the scalar / vector fields of a Track and its existing TrackStates.
// Cross-collection relations are not copied: the fDST track gets its own,
// pointing at the fDST track elements.
void cloneTrackShallow(edm4hep::MutableTrack dst, const edm4hep::Track& src) {
  dst.setType   (src.getType());
  dst.setChi2   (src.getChi2());
  dst.setNdf    (src.getNdf());
  dst.setNholes (src.getNholes());
  for (auto n : src.getSubdetectorHitNumbers())  dst.addToSubdetectorHitNumbers(n);
  for (auto n : src.getSubdetectorHoleNumbers()) dst.addToSubdetectorHoleNumbers(n);
  for (auto ts : src.getTrackStates())           dst.addToTrackStates(ts);
}

}  // namespace

void TrackHybridWriter::emit()
{
  edm4hep::TrackCollection trk_out;

  if (!ctx_.fdst_pa_to_sdst_track) {
    put(std::move(trk_out), "TRAC", "Tracks", Provenance::Derived);
    return;
  }
  const auto& pa_to_track = *ctx_.fdst_pa_to_sdst_track;
  const auto& sdst_tracks =
    frame_.get<edm4hep::TrackCollection>("sDST_TRAC_Tracks");

  // sDST Track index -> the fDST PAs the perigee match resolved to it.
  // Usually 1:1, but many-to-one is tolerated.
  std::vector<std::vector<int>> track_to_pas(sdst_tracks.size());
  for (int paIdx = 0; paIdx < static_cast<int>(pa_to_track.size()); ++paIdx) {
    const int t = pa_to_track[paIdx];
    if (t >= 0 && t < static_cast<int>(sdst_tracks.size())) {
      track_to_pas[t].push_back(paIdx);
    }
  }

  for (std::size_t i = 0; i < sdst_tracks.size(); ++i) {
    auto out = trk_out.create();
    cloneTrackShallow(out, sdst_tracks[i]);

    if (!ctx_.track_elements) continue;
    const auto& te = *ctx_.track_elements;
    for (int paIdx : track_to_pas[i]) {
      if (paIdx < static_cast<int>(te.pa_to_segments.size())) {
        for (const auto& seg : te.pa_to_segments[paIdx]) out.addToTracks(seg);
      }
      if (paIdx < static_cast<int>(te.pa_to_plane_hits.size())) {
        for (const auto& hit : te.pa_to_plane_hits[paIdx]) {
          out.addToTrackerHits(hit);
        }
      }
    }
  }

  put(std::move(trk_out), "TRAC", "Tracks", Provenance::Derived);
}

}  // namespace delphi_edm4hep::track_hybrid
