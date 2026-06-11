#include "delphi_edm4hep/BankPrefix.h"

#include <string>

namespace delphi_edm4hep::bank {

std::string make(std::string_view source_tag,
        std::string_view bank,
        std::string_view readable_name)
{
  std::string out;
  out.reserve(source_tag.size() + 1 + bank.size() + 1 + readable_name.size());
  out.append(source_tag);
  out.push_back('_');
  out.append(bank);
  out.push_back('_');
  out.append(readable_name);
  return out;
}

}  // namespace delphi_edm4hep::bank
