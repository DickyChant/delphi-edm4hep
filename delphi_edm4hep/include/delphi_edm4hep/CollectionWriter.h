// CollectionWriter.h
//
// Abstract base for per-domain podio writers. Owns a reference to the
// Frame, an EventContext (shared scratch space across writers in one
// event), and the source-tag prefix ("sDST" or "fDST"). Subclasses
// implement `emit()`; the protected `put` / `putParameter` helpers
// build the canonical "<source>_<bank>_<readable>" collection /
// parameter name and forward to the frame.
//
// Per-event flow:
//   EventContext ctx;
//   EventWriter        (frame, ctx, "sDST").emit();      // EVT_* params
//   TruthGenWriter     (frame, ctx, "sDST").emit();      // sets ctx.gen_truth
//   TrackingWriter     (frame, ctx, "sDST").emit();      // sets ctx.tracking
//   TruthRecoLinkWriter(frame, ctx, "sDST").emit();      // reads both
//   VertexWriter       (frame, ctx, "sDST").emit();      // reads ctx.tracking
//   CalorimeterWriter  (frame, ctx, "sDST").emit();      // reads ctx.tracking
//   ParticleIdWriter   (frame, ctx, "sDST").emit();      // reads ctx.tracking
//
// All writers are stack-allocated; no heap, no vtable dispatch in the
// usual case. `emit()` is virtual to leave the door open for runtime
// opt-out (e.g. --skip-calorimeter) but the dispatch overhead is just
// one indirect call per event per domain — negligible.

#pragma once

// Data-only headers (no writer classes) so this header doesn't pull
// CollectionWriter back in transitively.
#include "delphi_edm4hep/Tracking/TrackingData.h"   // tracking::Output
#include "delphi_edm4hep/Truth/TruthData.h"      // truth::GenParticleResult

#include <podio/Frame.h>

#include <optional>
#include <string>
#include <string_view>
#include <utility>

namespace delphi_edm4hep {

// Per-event shared state — passed by reference into every writer's ctor.
// Each writer reads its inputs from here (where another writer earlier
// in the chain set them) and stores its outputs here (where a later
// writer will read them). std::optional members signal "not yet set".
struct EventContext {
  // Set by TruthGenWriter; consumed by TruthRecoLinkWriter.
  std::optional<truth::GenParticleResult> gen_truth;

  // Set by TrackingWriter; consumed by VertexWriter, CalorimeterWriter,
  // ParticleIdWriter, and (pass 2) the TE-merge writers.
  std::optional<tracking::Output> tracking;

  // Pass-2 only: per-fDST-PA index -> sDST_TRAC_Tracks index, or -1
  // if no perigee-match. Built by MatchProvenanceWriter from the
  // fDST PA-chain walk; consumed by TeStateMergeWriter to find the
  // sDST Track to clone-and-extend.
  std::optional<std::vector<int>> fdst_pa_to_sdst_track;

  // Pass-2 only: per-fDST-PA index -> sDST_MAIN_Particles index, or
  // -1 if no match / unmatched. Built by MatchProvenanceWriter
  // alongside fdst_pa_to_sdst_track; consumed by TofFdstWriter,
  // MtpcFdstWriter, etc. for their ParticleID setParticle() linkage.
  std::optional<std::vector<int>> fdst_pa_to_sdst_particle;
};

// Where a collection's values came from.
//
//   Transcribed  the stored DST value, read from a ZEBRA bank word through
//                PHDST. Unit conversion and basis change still count as
//                transcription: the same measurement, represented differently.
//   Derived      produced by SKELANA at conversion time and read from a PSC*
//                common — a refit, a re-clustering or a recomputed tag.
//   Custom       computed by this converter. Not a DELPHI quantity at all.
//
// Every put() states one. A collection that would mix them must be split.
enum class Provenance { Transcribed, Derived, Custom };

// Record a collection's provenance for the end-of-job summary. Called by
// put(); no output is written to the file.
void noteProvenance(std::string_view name, Provenance prov);

// Print the provenance summary. Call once at end of job.
void reportProvenance();

class CollectionWriter {
public:
  CollectionWriter(podio::Frame& frame,
                   EventContext& ctx,
                   std::string_view source_tag)
    : frame_(frame), ctx_(ctx), source_tag_(source_tag) {}

  virtual ~CollectionWriter() = default;

  // Domain-specific implementation point.
  virtual void emit() = 0;

protected:
  podio::Frame&    frame_;
  EventContext&    ctx_;
  std::string_view source_tag_;

  // Build a canonical collection / parameter name
  // "<source_tag>_<bank>_<readable>". Single allocation.
  std::string makeName(std::string_view bank,
                       std::string_view readable) const {
    std::string out;
    out.reserve(source_tag_.size() + 1 + bank.size() + 1 + readable.size());
    out.append(source_tag_);
    out.push_back('_');
    out.append(bank);
    out.push_back('_');
    out.append(readable);
    return out;
  }

  // Move a freshly-built collection into the frame under
  // "<source>_<bank>_<readable>". `prov` states where the values came from;
  // see Provenance. Returns the const reference podio returns, for callers
  // that need to cross-reference the in-frame copy.
  template <typename Coll>
  const Coll& put(Coll&& coll,
                  std::string_view bank,
                  std::string_view readable,
                  Provenance prov) {
    auto name = makeName(bank, readable);
    noteProvenance(name, prov);
    return frame_.put(std::move(coll), std::move(name));
  }

  // Scaffolding for domains not yet migrated to the four-argument form.
  // Remove once every writer states its provenance.
  template <typename Coll>
  const Coll& put(Coll&& coll,
                  std::string_view bank,
                  std::string_view readable) {
    return frame_.put(std::move(coll), makeName(bank, readable));
  }

  // Frame-parameter equivalent. Name is "<source>_<bank>_<key>".
  // Type T must be one of podio's supported parameter types
  // (int, float, double, std::string, std::vector<...> of those, ...).
  template <typename T>
  void putParameter(std::string_view bank,
                    std::string_view key,
                    T&& value) {
    frame_.putParameter(makeName(bank, key), std::forward<T>(value));
  }
};

}  // namespace delphi_edm4hep
