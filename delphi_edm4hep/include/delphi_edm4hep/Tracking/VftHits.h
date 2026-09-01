// VftHits domain — pass-1 only.
//
// The pixel clusters the Very Forward Tracker reconstructed in this event:
// where each cluster sits, how precisely it was measured, how many pixels it
// spans and which track element it was assigned to. Event-level rather than
// per-particle, so the bank hangs off LDTOP rather than the PA chain.
//
// Emits:
//   <prefix>_PXTD_PixelHits              TrackerHitPlaneCollection
//   <prefix>_PXTD_PixelHits_ClusterSize  UserDataCollection<int32>, parallel
//   <prefix>_PXTD_PixelHits_TanagraId    UserDataCollection<int32>, parallel
//
// Positions are in the DELPHI frame. `du` and `dv` are the measurement errors
// along the module's own two axes; the module orientation is not on the DST,
// so the directions `u` and `v` those errors belong to are NaN rather than
// zero. The per-pixel addresses the bank also stores are column and row
// within a module and cannot be placed without the module geometry, so they
// are not emitted.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::vft_hits {

class VftHitsWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::vft_hits
