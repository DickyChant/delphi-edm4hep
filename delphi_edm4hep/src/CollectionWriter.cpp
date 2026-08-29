// Provenance registry.
//
// Collects the source of every collection emitted during a job and prints a
// summary at the end. The summary flags collections whose values SKELANA
// produced but whose name carries a DST bank mnemonic, since that naming
// implies a transcription.

#include "delphi_edm4hep/CollectionWriter.h"

#include <algorithm>
#include <cstdio>
#include <iostream>
#include <map>
#include <string>

namespace delphi_edm4hep {

namespace {

// Collection name -> provenance, first writer wins. Collections are emitted
// once per event, so this deduplicates across the job.
std::map<std::string, Provenance, std::less<>> g_seen;

// PA extra-module (blocklet) names accepted by PHDST's LPHPA, plus the
// event-level bank mnemonics used in collection names. A name built from one
// of these asserts that its values are stored DST content.
constexpr std::string_view kBankMnemonics[] = {
  "BSP",  "CCAL", "EL",   "ELID", "ELTR", "EMCA", "EMNC", "HAID", "HCAL",
  "HCMU", "HCNC", "HCRO", "LUJ",  "MAIN", "MRIC", "MTPC", "MU",   "MUFI",
  "MUID", "ODHI", "PHC",  "PHOT", "SSTC", "STIC", "TBL",  "TDHA", "TDID",
  "TDVD", "TEAD", "TEFA", "TEFB", "TEID", "TEOD", "TERB", "TERF", "TEST",
  "TETP", "TEVF", "TOF",  "TRAC", "TRAX", "V0",
};

// Extract the "<bank>" field of "<source>_<bank>_<readable>".
std::string_view bankField(std::string_view name) {
  const auto first = name.find('_');
  if (first == std::string_view::npos) return {};
  const auto second = name.find('_', first + 1);
  if (second == std::string_view::npos) return {};
  return name.substr(first + 1, second - first - 1);
}

bool isBankMnemonic(std::string_view bank) {
  return std::find(std::begin(kBankMnemonics), std::end(kBankMnemonics), bank)
         != std::end(kBankMnemonics);
}

}  // namespace

const char* label(Provenance prov) {
  switch (prov) {
    case Provenance::Derived: return "derived";
    case Provenance::Custom:  return "custom";
    default:                  return "transcribed";
  }
}

void noteProvenance(std::string_view name, Provenance prov) {
  g_seen.emplace(std::string(name), prov);
}

ProvenanceRecord provenanceRecord() {
  ProvenanceRecord record;
  record.collections.reserve(g_seen.size());
  record.sources.reserve(g_seen.size());
  for (const auto& [name, prov] : g_seen) {
    record.collections.push_back(name);
    record.sources.emplace_back(label(prov));
  }
  return record;
}

void reportProvenance() {
  if (g_seen.empty()) return;

  std::size_t transcribed = 0, derived = 0, custom = 0;
  std::cout << "delphi_edm4hep: provenance summary\n";
  for (const auto& [name, prov] : g_seen) {
    switch (prov) {
      case Provenance::Transcribed: ++transcribed; break;
      case Provenance::Derived:     ++derived;     break;
      case Provenance::Custom:      ++custom;      break;
    }
    // A bank mnemonic asserts stored DST content, so anything not
    // transcribed is wearing a name it has not earned.
    const bool mismatch = prov != Provenance::Transcribed
                          && isBankMnemonic(bankField(name));
    std::printf("  %-11s  %s%s\n", label(prov), name.c_str(),
                mismatch ? "   [bank mnemonic]" : "");
  }
  std::cout << "  " << transcribed << " transcribed, " << derived
            << " derived, " << custom << " custom\n";
}

}  // namespace delphi_edm4hep
