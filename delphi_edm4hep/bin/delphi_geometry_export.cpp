#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Geometry/GdmlWorldWriter.h"
#include "delphi_edm4hep/Geometry/GeometryModel.h"

#include <exception>
#include <fstream>
#include <iostream>

int main(int argc, char **argv) {
  if (argc != 3) {
    std::cerr << "usage: " << argv[0]
              << " CERNSNAP*_DELSIM.ASC delphi-world.gdml\n";
    return 2;
  }
  try {
    const auto database =
        delphi_edm4hep::geometry::CargoDatabase::readFile(argv[1]);
    const auto model =
        delphi_edm4hep::geometry::GeometryModel::fromCargo(database, argv[1]);
    std::ofstream output(argv[2]);
    if (!output) {
      throw std::runtime_error(std::string("cannot create GDML file: ") +
                               argv[2]);
    }
    delphi_edm4hep::geometry::writeGdmlWorld(output, model, "/DELF.B", argv[1]);
  } catch (const std::exception &error) {
    std::cerr << "delphi_geometry_export: " << error.what() << '\n';
    return 1;
  }
}
