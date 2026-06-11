// SticShower domain — runs in BOTH passes.
//
// The STIC (Small-angle TIle Calorimeter) showers are exposed through
// the SKELANA PSCSTC common (NSTIC + QSTIC(1..6) = E, θ, φ, nTowers,
// vetoTag, Si-vertex pos), filled from PA.SSTC (33) on the sDST and
// PA.STIC (19) on the fDST. Since each shower carries an energy and a
// direction (θ, φ), Cluster is the proper edm4hep home.
//
// Emits (ClusterCollection, event-level — STIC showers are standalone,
// not per-track):
//   sDST_SSTC_Showers   (pass 1)   } same data, named by the bank that
//   fDST_STIC_Showers   (pass 2)   } feeds PSCSTC on each pass
//     energy = QSTIC(1); iTheta = QSTIC(2); iPhi = QSTIC(3);
//     shapeParameters = [nTowers, vetoTag, SiVtxPos]; type bit 3 (=8).
//
// If PSCSTC is not populated on a given pass (NSTIC=0) the collection is
// emitted empty — graceful, never wrong.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::stic_shower {

class SticShowerWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::stic_shower
