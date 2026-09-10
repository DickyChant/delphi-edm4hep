#pragma once

#include "edm4hep/RawTimeSeries.h"
#include "edm4hep/SimTrackerHit.h"
#include "podio/LinkCollection.h"

namespace delphi_edm4hep {

using VertexDigiSimTrackerHitLinkCollection =
    podio::LinkCollection<edm4hep::RawTimeSeries, edm4hep::SimTrackerHit>;

} // namespace delphi_edm4hep
