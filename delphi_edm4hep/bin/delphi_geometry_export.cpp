#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Geometry/GdmlBeamPipeWriter.h"
#include "delphi_edm4hep/Geometry/GdmlDetectorWriter.h"
#include "delphi_edm4hep/Geometry/GdmlWorldWriter.h"
#include "delphi_edm4hep/Geometry/GeometryModel.h"

#include <exception>
#include <fstream>
#include <iostream>
#include <string_view>

int main(int argc, char **argv) {
  const auto mode = argc == 4 ? std::string_view(argv[1]) : std::string_view{};
  const auto detectorMode = mode == "--beam-pipe" || mode == "--tpc";
  if (argc != 3 && !detectorMode) {
    std::cerr << "usage: " << argv[0]
              << " [--beam-pipe|--tpc] CERNSNAP*_DELSIM.ASC delphi.gdml\n";
    return 2;
  }
  const auto inputIndex = detectorMode ? 2 : 1;
  const auto outputIndex = detectorMode ? 3 : 2;
  try {
    const auto database =
        delphi_edm4hep::geometry::CargoDatabase::readFile(argv[inputIndex]);
    const auto model = delphi_edm4hep::geometry::GeometryModel::fromCargo(
        database, argv[inputIndex]);
    std::ofstream output(argv[outputIndex]);
    if (!output) {
      throw std::runtime_error(std::string("cannot create GDML file: ") +
                               argv[outputIndex]);
    }
    if (mode == "--beam-pipe") {
      delphi_edm4hep::geometry::writeGdmlBeamPipe(output, model, "/DELF.B",
                                                  "/BEA*.B", argv[inputIndex]);
    } else if (mode == "--tpc") {
      delphi_edm4hep::geometry::writeGdmlDetector(
          output, model,
          {{"/BEA*.B", {}, 0.0}, {"/TPC*.B", "step_tracker_sd", 1.0}},
          "/DELF.B", argv[inputIndex]);
    } else {
      delphi_edm4hep::geometry::writeGdmlWorld(output, model, "/DELF.B",
                                               argv[inputIndex]);
    }
  } catch (const std::exception &error) {
    std::cerr << "delphi_geometry_export: " << error.what() << '\n';
    return 1;
  }
}
