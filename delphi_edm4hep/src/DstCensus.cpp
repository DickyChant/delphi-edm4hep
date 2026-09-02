#include "delphi_edm4hep/internal/DstCensus.h"

#include "phdst/functions.hpp"
#include "phdst/uxcom.hpp"
#include "phdst/uxlink.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <set>
#include <string_view>
#include <utility>

namespace ph = phdst;

namespace delphi_edm4hep::census {
namespace {

// Blocklet label -> mnemonic, from PHDST's own tables: XTRAID (labels 1..21),
// XTRAID2 (41..43) and the shortDST-family extra modules CHIDXM (22..35).
// phdstxx.car:16689-16723. Label 0 is the standard module.
constexpr std::pair<int, std::string_view> kModules[] = {
  {0,"MAIN"},{1,"CCAL"},{2,"EMCA"},{3,"HCAL"},{4,"MU"},{5,"EL"},{6,"MRIC"},
  {7,"MTPC"},{8,"TRAC"},{9,"TOF"},{10,"VD"},{11,"TDHA"},{12,"TEID"},
  {13,"TETP"},{14,"TEOD"},{15,"TEFA"},{16,"TEFB"},{17,"TDID"},{18,"SAT"},
  {19,"STIC"},{20,"TRAX"},{21,"TERF"},{22,"EMNC"},{23,"HCNC"},{24,"MUID"},
  {25,"ELID"},{26,"HAID"},{27,"MUFI"},{28,"ELTR"},{29,"ODHI"},{30,"PHOT"},
  {31,"OTRK"},{32,"NMUS"},{33,"SSTC"},{34,"HCRO"},{35,"HCMU"},
  {41,"TEST"},{42,"TEVF"},{43,"TERB"},
};

// PILOT blocklets PHDST knows about (PIBL, phdstxx.car:16600-16660). Four
// characters, space-padded, as IPHPIC expects.
constexpr const char* kPilot[] = {
  "DAS ", "VERS", "IDEN", "DANA", "DANI", "DANF", "DPHA", "DPHY", "DJET",
  "SAT ", "VSAT", "TRIG", "TRGR", "DETV", "DETI", "DETP", "DETE", "TTAG",
  "DTAG", "LEP ",
};

std::set<std::string> g_modules;
std::set<std::string> g_pilot;

std::string_view mnemonic(int label) {
  for (const auto& [id, name] : kModules) {
    if (id == label) return name;
  }
  return {};
}

// Trailing spaces are part of the Fortran name, not of the reported one.
std::string trimmed(const char* name) {
  std::string out(name);
  while (!out.empty() && out.back() == ' ') out.pop_back();
  return out;
}

}  // namespace

void observeEvent() {
  const int LDTOP = ph::LDTOP;
  if (LDTOP <= 0) return;

  for (const char* name : kPilot) {
    if (ph::IPHPIC(name, 1) > 0) g_pilot.insert(trimmed(name));
  }

  // Read the blocklet labels out of each PA header rather than probing every
  // mnemonic: IQ(lpa+4) is the blocklet count, the words after it are the
  // per-blocklet lengths, and blocklet i's data follows them with its label
  // in the first word.
  for (int lpv = ph::LQ(LDTOP - 1); lpv > 0; lpv = ph::LQ(lpv)) {
    for (int lpa = ph::LQ(lpv - 1); lpa > 0; lpa = ph::LQ(lpa)) {
      const int nblk = ph::IQ(lpa + 4);
      if (nblk <= 0 || nblk > 64) continue;
      int offset = lpa + 4 + nblk;
      for (int i = 1; i <= nblk; ++i) {
        const int len = ph::IQ(lpa + 4 + i);
        if (len <= 0) break;
        const int label = static_cast<int>(std::lround(ph::Q(offset + 1)));
        if (const auto name = mnemonic(label); !name.empty()) {
          g_modules.emplace(name);
        }
        offset += len;
      }
    }
  }
}

std::vector<std::string> paModules() {
  return {g_modules.begin(), g_modules.end()};
}

std::vector<std::string> pilotBlocklets() {
  return {g_pilot.begin(), g_pilot.end()};
}

}  // namespace delphi_edm4hep::census
