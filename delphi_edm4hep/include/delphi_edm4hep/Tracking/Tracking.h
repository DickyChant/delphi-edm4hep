// Tracking domain: PA.MAIN + PA.TRAC + PSCVEC (VECP / LVLOCK).
// TrackingWriter emits:
//   <tag>_TRAC_Tracks                Track + AtIP TrackState + 5x5 cov
//   <tag>_MAIN_Particles             charged + neutral, VECP 4-mom
//   <tag>_VECP_LVLOCK                UserData<int32>
//   <tag>_TRAC_d0PV / z0PV / d0BS    UserData<float> from QTRAC(38..40); mm
//                                    (cm x10), DELPHI sign, parallel to
//                                    TRAC_Tracks (charged-only), EMPTY in real
//                                    DATA. For data use the geometric
//                                    <tag>_PV_trackD0PV (Vertex.cpp; mm, LCIO
//                                    sign) ~= -1x this.
// and stores its Output (handle list + index maps) into ctx_.tracking
// for downstream writers.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"
#include "delphi_edm4hep/Tracking/TrackingData.h"  // Output

namespace delphi_edm4hep::tracking {

class TrackingWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::tracking
