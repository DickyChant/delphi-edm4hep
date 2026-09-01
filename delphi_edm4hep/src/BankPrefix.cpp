#include "delphi_edm4hep/BankPrefix.h"

#include <algorithm>
#include <array>

namespace delphi_edm4hep::bank {
namespace {

// PA modules a plain shortDST does not keep, present on both the extended
// shortDST and the longDST. The TE family spans this class and the
// extended-shortDST-only one, so it is named for the weaker requirement.
constexpr std::array<std::string_view, 13> kExtendedOnly = {
    "EMCA", "HCAL", "HCMU", "MRIC", "MUFI", "STIC", "TDID",
    "TE",   "TERB", "TERF", "TEST", "TEVF", "TOF",
};

// PA modules only the longDST keeps.
constexpr std::array<std::string_view, 4> kLongOnly = {"EL", "MU", "TDHA", "TRAX"};

template <std::size_t N>
bool listed(const std::array<std::string_view, N>& table, std::string_view bank) {
  return std::find(table.begin(), table.end(), bank) != table.end();
}

}  // namespace

std::string_view prefixFor(Pass pass, std::string_view bank) {
  if (pass == Pass::Fdst) return "fDST";
  if (listed(kLongOnly, bank)) return "lDST";
  if (listed(kExtendedOnly, bank)) return "xsDST";
  return "sDST";
}

std::string make(Pass pass, std::string_view bank, std::string_view readable_name) {
  const std::string_view prefix = prefixFor(pass, bank);
  std::string out;
  out.reserve(prefix.size() + bank.size() + readable_name.size() + 2);
  out.append(prefix);
  out.push_back('_');
  out.append(bank);
  out.push_back('_');
  out.append(readable_name);
  return out;
}

}  // namespace delphi_edm4hep::bank
