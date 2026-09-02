// VftHits domain — pass-1 only.
//
// Very Forward Tracker pixel clusters. An event-level bank (LDTOP), not part
// of the PA chain.
//
// Emits:
//   <prefix>_PXTD_PixelHits              TrackerHitPlaneCollection
//   <prefix>_PXTD_PixelHits_ClusterSize  UserDataCollection<int32>, parallel
//   <prefix>_PXTD_PixelHits_TanagraId    UserDataCollection<int32>, parallel
//
// Positions are in the DELPHI frame; `du`/`dv` are the errors along the
// module axes. `u`/`v` are NaN, since the module orientation is not stored.
// Per-pixel addresses are not emitted: they cannot be placed without the
// module geometry.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::vft_hits {

class VftHitsWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::vft_hits
