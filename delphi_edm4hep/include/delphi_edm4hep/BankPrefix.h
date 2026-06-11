// SPDX-License-Identifier: same-as-repo
// BankPrefix.h
//
// Authoritative mapping between Delphi bank / SKELANA-common mnemonics and
// the BANK slot of the <source-tag>_<BANK>_<ReadableName> collection-naming
// convention used by the library.
//
// This header is the single source of truth for "what does e.g. MAIN mean
// in a collection name?" — the table covers per-PA modules, event-level
// banks, and SKELANA-aggregated commons.
//
// No state, no Fortran linkage — pure constexpr-ish lookups.

#pragma once

#include <string_view>

namespace delphi_edm4hep::bank {

// Source-tag prefix added by the harness depending on which pass wrote the
// frame. Stored as a string literal so we can prepend without allocation.
inline constexpr std::string_view kSourceTagSDST = "sDST";
inline constexpr std::string_view kSourceTagFDST = "fDST";

// Helper: build a fully-qualified collection name "<source>_<bank>_<name>".
// Returns a std::string (one allocation per call); only called at frame.put
// time so the cost is negligible.
std::string make(std::string_view source_tag,
        std::string_view bank,
        std::string_view readable_name);

}  // namespace delphi_edm4hep::bank
