// MatchProvenance domain — pass-2 only.
//
// Walks the fDST PA chain, extracts each charged PA's perigee, and
// calls perigee_match::findMatch against sDST_TRAC_Tracks (read out
// of frame_) to determine whether the same physical track exists in
// both DSTs.
//
// Emits:
//   <tag>_MAIN_MatchProvenance   UserDataCollection<int32>
//     parallel to sDST_MAIN_Particles (charged + neutral, in PA-walk
//     order from pass-1). Values per legacy commit fb62da1:
//       +1 charged PFO matched perigee with a fDST PA
//       0  charged PFO with no fDST counterpart (postDST V0 daughter,
//          gamma-conversion daughter, or hadronic-secondary refit)
//      -1  neutral PFO (perigee match doesn't apply)
//
// Also populates ctx_.fdst_pa_to_sdst_track so downstream pass-2
// writers (TofFdst, MtpcFdst, TeStateMerge) can find the matching
// sDST track / particle for each fDST PA they process.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

namespace delphi_edm4hep::matchprov {

class MatchProvenanceWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;
  void emit() override;
};

}  // namespace delphi_edm4hep::matchprov
