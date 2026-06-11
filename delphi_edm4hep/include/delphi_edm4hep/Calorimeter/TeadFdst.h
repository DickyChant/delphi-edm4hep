// TeadFdst domain — pass-2 pure-fDST writer.
//
// LDTOP-10 holds the "unassociated TE BANK 10" — TOF/HOF hits NOT
// associated with any tracked Particle. We emit:
//
//   <tag>_TEAD_TOFHits    CalorimeterHitCollection
//                         barrel TOF (sub-bank 5); positions converted
//                         (R, R*phi, Z) → (x, y, z) cm; time in ns
//   <tag>_TEAD_HOFHits    CalorimeterHitCollection
//                         forward HOF (sub-bank 11); positions (X,Y,Z)
//                         direct; time not decoded at this DST level
//                         (passed through as 0 to keep the schema
//                         consistent — downstream can detect by det).
//

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::tead_fdst {

class TeadFdstWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::tead_fdst
