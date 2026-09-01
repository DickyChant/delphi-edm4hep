// SPDX-License-Identifier: same-as-repo
// BankPrefix.h
//
// Collection names follow <prefix>_<BANK>_<ReadableName>.
//
// The prefix names the kind of DELPHI input file that supplies the bank, so a
// collection name states what a reader needs in order to have the data:
//
//   sDST   kept by every DST flavour
//   xsDST  kept by the extended shortDST and the longDST, but not by a plain
//          shortDST
//   lDST   kept by the longDST only
//   fDST   written by the fullDST pass
//
// Which PA modules a file carries is fixed by the production description deck
// it was written with (shortdst.des, longdst.des, DESCRIP), not by the year or
// the reprocessing tag. Collections are emitted whether or not the input
// carries the module, and are empty when it does not; the prefix says which
// inputs can fill them.
//
// This header is the single source of truth for the prefix and for what a
// bank mnemonic means in a collection name.
//
// No state, no Fortran linkage.

#pragma once

#include <string>
#include <string_view>

namespace delphi_edm4hep::bank {

// Which conversion pass is writing. The fullDST pass reads a different input
// file, so everything it writes carries the fDST prefix regardless of bank.
enum class Pass { Sdst, Fdst };

// Prefix for `bank` when written by `pass`.
std::string_view prefixFor(Pass pass, std::string_view bank);

// Build "<prefix>_<bank>_<readable_name>". One allocation; called at
// frame.put time only.
std::string make(Pass pass, std::string_view bank, std::string_view readable_name);

}  // namespace delphi_edm4hep::bank
