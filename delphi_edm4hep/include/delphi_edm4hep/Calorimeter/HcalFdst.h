// HcalFdst domain — pass-2 pure-fDST writer.
//
// Walks fDST PA chain, reads PA.HCAL (label 3, fDST-only — the per-
// tower bank). Each HCAL shower carries a tower block (TDAM = tower
// energy + LAYLUV = LAY*10000 + JU*100 + JV cell-index encoding).
// We emit one CalorimeterHit per tower:
//
//   <tag>_HCAL_Towers   CalorimeterHitCollection
//                       energy = TDAM, position = shower centroid (mm),
//                       cellID = packed LAYLUV (LAY/JU/JV), type = LAY.
//
// JU is θ-cell index; JV is φ-cell index with period 96 (DELPHI HCAL
// barrel wrap-around).

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::hcal_fdst {

class HcalFdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::hcal_fdst
