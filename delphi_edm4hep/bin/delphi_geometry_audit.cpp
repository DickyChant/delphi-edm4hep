#include "delphi_edm4hep/Geometry/CargoDatabase.h"

#include <exception>
#include <iostream>
#include <map>
#include <string>

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: " << argv[0] << " CERNSNAP*_DELSIM.ASC\n";
    return 2;
  }

  try {
    const auto database =
        delphi_edm4hep::geometry::CargoDatabase::readFile(argv[1]);
    std::map<std::string, std::size_t> kinds;
    std::size_t shapes = 0;
    std::size_t materials = 0;
    for (const auto &record : database.records()) {
      ++kinds[record.kind];
      if (record.kind == "GEOM" && record.findField("SHAP") != nullptr) {
        ++shapes;
      }
      if (record.kind == "MATC" && record.findField("MATF") != nullptr) {
        ++materials;
      }
    }

    std::cout << "records=" << database.records().size() << '\n';
    for (const auto &[kind, count] : kinds) {
      std::cout << kind << '=' << count << '\n';
    }
    std::cout << "GEOM_with_SHAP=" << shapes << '\n';
    std::cout << "MATC_with_MATF=" << materials << '\n';
  } catch (const std::exception &error) {
    std::cerr << "delphi_geometry_audit: " << error.what() << '\n';
    return 1;
  }
}
