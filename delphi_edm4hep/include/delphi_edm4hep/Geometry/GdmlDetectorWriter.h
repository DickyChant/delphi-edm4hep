#pragma once

#include "delphi_edm4hep/Geometry/GeometryModel.h"

#include <iosfwd>
#include <string>
#include <string_view>
#include <vector>

namespace delphi_edm4hep::geometry {

struct GdmlDetectorRoot {
  std::string path;
  // Empty for passive roots; otherwise a Code4hep SensDet value.
  std::string sensitiveDetector;
  double maximumStepCm{};
};

// Write one or more top-level DELPHI detector trees into the authoritative
// world. This is the growing native detector-construction seam; only shape
// families with validated DELPHI-to-GDML translations are accepted.
void writeGdmlDetector(std::ostream &output, const GeometryModel &model,
                       const std::vector<GdmlDetectorRoot> &roots,
                       std::string_view worldPath = "/DELF.B",
                       std::string_view snapshotIdentifier = {});

} // namespace delphi_edm4hep::geometry
