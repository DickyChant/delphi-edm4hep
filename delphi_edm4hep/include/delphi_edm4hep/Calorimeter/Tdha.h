// Tdha domain — runs in both passes: PA.TDHA is on the XSDST as well as the
// fullDST.
//
// PA.TDHA (label 11) carries the per-HCAL-layer associated TD ("Time
// Digitisation") hits along a track's HCAL extrapolation — the input to
// muon-vs-pion separation. Each TD is a hadron-calorimeter hit with a
// position + energy, so CalorimeterHit is the proper edm4hep home.
//
// Emits:
//   fDST_TDHA_HcalTimeHits   CalorimeterHitCollection
//     one hit per associated TD; energy = TD energy, position from the
//     (X/R, Y/Rφ, Z) coords (barrel loc=0 → cylindrical→cartesian, like
//     fDST_TEAD_TOFHits; endcap loc=1 → X/Y/Z direct), type = layer
//     number, cellID = location bit (0=barrel, 1=endcap).
//
// Track association is implicit (the bank lives under the track's PA),
// not stored as a relation — same convention as the other fDST calo-hit
// collections (CalorimeterHit has no particle relation). No per-hit time
// is decodable at this DST level (the layer holds extrap coords + energy,
// not a digitised time), so time is left 0.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::tdha {

class TdhaWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::tdha
