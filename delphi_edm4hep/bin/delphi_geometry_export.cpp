#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Geometry/GdmlBeamPipeWriter.h"
#include "delphi_edm4hep/Geometry/GdmlWorldWriter.h"
#include "delphi_edm4hep/Geometry/GeometryModel.h"

#include <exception>
#include <fstream>
#include <iostream>
#include <string_view>

int main(int argc, char **argv) {
  const auto beamPipe = argc == 4 && std::string_view(argv[1]) == "--beam-pipe";
  if (argc != 3 && !beamPipe) {
    std::cerr << "usage: " << argv[0]
              << " [--beam-pipe] CERNSNAP*_DELSIM.ASC delphi.gdml\n";
    return 2;
  }
  const auto inputIndex = beamPipe ? 2 : 1;
  const auto outputIndex = beamPipe ? 3 : 2;
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
    if (beamPipe) {
      delphi_edm4hep::geometry::writeGdmlBeamPipe(output, model, "/DELF.B",
                                                  "/BEA*.B", argv[inputIndex]);
    } else {
      delphi_edm4hep::geometry::writeGdmlWorld(output, model, "/DELF.B",
                                               argv[inputIndex]);
    }
  } catch (const std::exception &error) {
    std::cerr << "delphi_geometry_export: " << error.what() << '\n';
    return 1;
  }
}
