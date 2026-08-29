// BankReader.h — internal header (not exported).
//
// Locating and reading PA extra-modules in the ZEBRA store. A Record owns
// the decoding of one module: where its words are, and any layout that
// varies with the DST version. Writers map the values into EDM4hep and do
// not read Q/IQ directly.

#pragma once

#include "delphi_edm4hep/internal/PaWalk.h"

#include <cmath>
#include <initializer_list>
#include <optional>
#include <string_view>

namespace delphi_edm4hep::banks {

// A located module, or a sub-record inside one. `name` is the mnemonic that
// answered, which matters where a module changed identity between
// data-taking eras: hadron-calorimeter clusters are HCNC at LEP1 and HCAL
// from 1996.
class Record {
public:
  Record(std::string_view name, int address)
    : name_(name), address_(address) {}

  std::string_view name() const { return name_; }

  // Word `n`, numbered from 1 as in the DELPHI layout documents.
  float real(int n) const { return phdst::Q(address_ + n); }
  int   integer(int n) const {
    return static_cast<int>(std::lround(phdst::Q(address_ + n)));
  }

  // A record starting `n` words further on. Used for the repeated
  // sub-records — showers, layers — that follow a module header.
  Record subRecord(int n) const { return Record(name_, address_ + n); }

private:
  std::string_view name_;
  int              address_;
};

// Locate `name` on the PA at `lpa`. Empty if the module is absent.
// `name` is passed to the Fortran lookup and must be NUL-terminated.
std::optional<Record> find(int lpa, const char* name);

// Locate the first of `names` present. Use where a module was replaced
// between eras and either may appear.
std::optional<Record> findFirst(int lpa,
                                std::initializer_list<const char*> names);

}  // namespace delphi_edm4hep::banks
