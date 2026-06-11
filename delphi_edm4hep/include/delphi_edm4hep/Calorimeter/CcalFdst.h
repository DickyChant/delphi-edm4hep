// CcalFdst domain — pass-2 only.
//
// PA.CCAL (module 1, fullDST) is Combined Calorimetry — the per-PA
// reconciliation of overlapping EMF/HPC/HAC showers into a single
// calibrated shower list. Each shower has energy + position + direction,
// so Cluster is the proper home.
//
// Emits:
//   fDST_CCAL_Showers   ClusterCollection
//     energy, position (X/Y/Z ×10 mm), iTheta, iPhi; type bit 4 (=16)
//     marks CCA (vs HPC=bit0 / EMF=bit1 / HCAL=bit2 / STIC=bit3).

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::ccal_fdst {

class CcalFdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::ccal_fdst
