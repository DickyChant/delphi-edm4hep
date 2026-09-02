// DstCensus.h — internal (not exported).
//
// Records which PA extra-modules and PILOT blocklets the converted file
// actually contains, for the job's metadata frame. This is what separates
// "this collection is empty because the input never carried its module" from
// "empty because this event had no such activity" — a distinction the
// collection set deliberately does not encode, since it never varies.
//
// The census covers the events actually converted, so a short -n run reports
// only what those events held.

#pragma once

#include <string>
#include <vector>

namespace delphi_edm4hep::census {

// Call once per event, with the DST record in the ZEBRA store.
void observeEvent();

// Mnemonics of every PA module seen in any event so far, sorted.
std::vector<std::string> paModules();

// Names of every PILOT blocklet present in any event so far, sorted.
std::vector<std::string> pilotBlocklets();

}  // namespace delphi_edm4hep::census
