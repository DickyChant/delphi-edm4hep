// Btag.h — b-tagging domain writer.
//
// Emits both forms of DELPHI's b-tag, because they are different quantities:
//
//   <prefix>_BTG_*     the tag DELPHI stored on the DST, read back with
//                      PSHBTG. Transcribed. NaN where the bank was never
//                      written, which includes many shortDSTs.
//   <prefix>_AABTAG_*  the tag recalculated here by rerunning AABTAG.
//                      Derived. Carries the per-track quantities from the
//                      AAMAIN / AAMNVX commons and AABTAG's own primary
//                      vertex as well; the stored bank has no per-track
//                      content at all.
//
// AABTAG is deliberately not a bank mnemonic: it marks values the converter
// computed rather than read. Prefer it for analysis -- rerunning the tagger
// improves data/MC agreement -- and keep BTG for what DELPHI recorded.
//
// Per-track arrays are emitted in AABTAG's OWN track ordering (1..NTRK),
// not remapped onto the Track/Particle collections, with a parallel
// _ParticleIndex giving the <prefix>_MAIN_Particles entry for each (-1
// when unresolvable). That mirrors sDST_ELTR_ParticleIndex and keeps the
// AABTAG selection (ISRT) meaningful; a remap would have to invent
// entries for tracks AABTAG never considered.

#pragma once

#include "delphi_edm4hep/CollectionWriter.h"

#include <string_view>

namespace delphi_edm4hep::btag {

class BtagWriter : public CollectionWriter {
public:
  using CollectionWriter::CollectionWriter;

  void emit() override;

private:
  // Emit the event and hemisphere b-tag probabilities plus the thrust that
  // are currently in the PSCBTG common, under `bank`. Both the stored tag and
  // the recalculated one land there, one after the other, so the caller
  // controls which is being read.
  void emitEventLevel(std::string_view bank, Provenance prov, bool valid);
};

}  // namespace delphi_edm4hep::btag
