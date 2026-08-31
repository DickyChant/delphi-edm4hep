// Trax domain — runs in both passes, before the track writers.
//
// Decodes PA.TRAX (label 20), the track extrapolated onto its first measured
// point and a set of named detector surfaces, and hands the resulting
// TrackStates to the track writers through EventContext. They are appended to
// the track built from the same PA, so a reader finds them on
// TRAC_Tracks.trackStates; `location` marks the first measured point and the
// calorimeter crossings.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::trax {

class TraxWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::trax
