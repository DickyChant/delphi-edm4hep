// EmcaData.h — value type passed through EventContext.
// Separate from Emca.h so CollectionWriter.h can include this without
// pulling in the writer class.

#pragma once

#include <edm4hep/CalorimeterHit.h>

#include <vector>

namespace delphi_edm4hep::emca {

// Output of EmcaWriter::emit(): the calorimeter hits of each shower, keyed by
// the PA and the shower they were read from, so the cluster writer can attach
// them while its clusters are still mutable.
//
//   pa_shower_hits[paIdx][ns] : the hits of shower ns on PA paIdx
struct Output {
  std::vector<std::vector<std::vector<edm4hep::CalorimeterHit>>> pa_shower_hits;
};

}  // namespace delphi_edm4hep::emca
