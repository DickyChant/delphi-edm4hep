// VdHits domain — pass-1 only.
//
// Vertex-Detector hits from SKELANA PSCVDU (unassociated) and PSCVDA
// (associated to a track). Each hit is a TrackerHit3D. The position is
// stored as a **cylindrical-mixed** triple
// (R, slot2, slot4), NOT Cartesian — the module→φ table needed for
// (x,y) is not in any doc we have, so global-φ conversion is deferred.
//
// Emits:
//   sDST_TDVD_VDPoints   TrackerHit3DCollection  (PSCVDU, unassociated)
//   sDST_TDVD_VDHits     TrackerHit3DCollection  (PSCVDA, associated)
//
// The associated hits are also handed to TrackingWriter through EventContext,
// grouped by charged-track ordinal, so each track links its own hits through
// Track.trackerHits. That is why this writer runs BEFORE the track writer: a
// track can only be given relations while its own writer still holds it.
//
// Per-hit fields (both commons, 5 each): K(1)=module# with sign of Z,
// Q(2)=local X (or Z since '94), Q(3)=R (−R if R-Z measured), Q(4)=RPhi
// (or Z since '94), Q(5)=signal/noise. cellID = signed module#; type bit
// 0 set when slot-3 (R) is negative (R-Z measurement); eDep carries S/N.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::vd_hits {

class VdHitsWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::vd_hits
