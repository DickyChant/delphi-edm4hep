// Module lookup, over PHDST's LPHPA.

#include "delphi_edm4hep/internal/BankReader.h"

namespace delphi_edm4hep::banks {

std::optional<Record> find(int lpa, const char* name) {
  const int address = pawalk::lphpa(name, lpa);
  if (address <= 0) return std::nullopt;
  return Record(name, address);
}

std::optional<Record> findFirst(int lpa,
                                std::initializer_list<const char*> names) {
  for (const char* name : names) {
    if (auto record = find(lpa, name)) return record;
  }
  return std::nullopt;
}

}  // namespace delphi_edm4hep::banks
