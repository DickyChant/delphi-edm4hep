// SticShower domain — runs in BOTH passes.
//
// The STIC (Small-angle TIle Calorimeter) showers are exposed through the
// SKELANA PSCSTC common, filled from PA.SSTC (33) on the sDST and PA.STIC (19)
// on the fDST. The common is a table indexed by VECP track, one row per track,
// so a shower belongs to a particle. Each shower carries an energy and a
// direction, so Cluster is the proper edm4hep home.
//
// Emits (ClusterCollection):
//   sDST_SSTC_Showers   (pass 1)   } same data, named by the bank that
//   fDST_STIC_Showers   (pass 2)   } feeds PSCSTC on each pass
//     energy = QSTIC(1); iTheta = QSTIC(2); iPhi = QSTIC(3);
//     shapeParameters = KSTIC(4..9); type bit 3 (=8).
//
// Pass 1 attaches each shower to the particle built from the same VECP slot;
// pass 2 has no VECP-to-particle map and leaves them unattached.
//
// A track whose row is entirely zero has no shower and is skipped, so the
// collection is empty when no track has one.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::stic_shower {

class SticShowerWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::stic_shower
