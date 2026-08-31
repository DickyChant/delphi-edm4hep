// TrackElements domain — runs in both passes, before the track writers.
//
// Emits the PA track-element modules (te_bank::decodeModule) as:
//
//   <tag>_TE_Segments              Track,           one per track element
//   <tag>_TE_SegmentLength         UserData<float>, parallel, mm
//   <tag>_TEVF_TrackElementPlane   TrackerHitPlane, one per VFT element
//   <tag>_TEVF_TrackElementLength  UserData<float>, parallel, mm
//
// A segment is a Track carrying one TrackState at AtOther: referencePoint is
// the measured point, phi the track direction there, and chi2/ndf the
// module's own fit quality. Components the module did not measure are NaN,
// never zero — zero is a legal measured value. The VFT measures two
// coordinates and no direction, so it is a plane hit rather than a track.
//
// `type` identifies the source module and the reconstruction stage as
// label*10 + stage:
//
//   12  TEID  inner detector      stage 1 jet chamber, 2 trigger layer
//   13  TETP  TPC
//   14  TEOD  outer detector
//   15  TEFA  forward chamber A
//   16  TEFB  forward chamber B
//   21  TERF  forward RICH
//   41  TEST  straw tubes
//   42  TEVF  very forward tracker
//
// so 121 is an inner-detector element from the jet chamber and 131 a TPC
// element. The stage digit is 0 on files written before PXDST 2.87. Which
// TrackState components are measured varies with the module, so `type` also
// tells a reader which ones to expect; the README tabulates that.
//
// The links live on the mother track: the track writers read
// EventContext::track_elements and call addToTracks / addToTrackerHits, so a
// reader walks TRAC_Tracks -> tracks / trackerHits to reach these.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::track_elements {

class TrackElementsWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::track_elements
