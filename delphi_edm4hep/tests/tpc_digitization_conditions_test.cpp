#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Simulation/TpcDigitizationConditions.h"

#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string &message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

} // namespace

int main() {
  std::istringstream input(R"(*CALB /TPC*.B
940624,235900,941030,222515
*ISLO 16,0,0,0,0,0,0,11184810,0,0,0,0,0,0,0,0,0
*SLOW 18,0,0,0,975,986.2,25.306,-189,-169,91.7,12.5,19.1,9.1,12.5,1.03005,975.21,989.93,-169,-154.5
*USER 16,254.5,.959,.942,1.005,1.007,.978,1.048,.977,1.042,.981,.989,1.037,1.036,652.8,1,1.066
**
*CALB /TPC*/ENP0.B
940624,235900,941030,231638
*SLOW 14,6.998,0,0,0,0,0,0,0,0,0,0,0,0,0
**
*CALB /TPC*/ENP1.B
940624,235900,941030,232213
*SLOW 14,7.002,0,0,0,0,0,0,0,0,0,0,0,0,0
**
)");
  const auto database =
      delphi_edm4hep::geometry::CargoDatabase::read(input, "fixture");
  const delphi_edm4hep::simulation::TpcReadoutGeometry readout(
      {{1, 64, 36.5, .959, .547}},
      {{1, 0, 0, 0, 0, 0}, {12, 1, 1, 0, 0, 0}}, 145.0);
  const auto conditions =
      delphi_edm4hep::simulation::TpcDigitizationConditions::fromCargo(
          database, readout);
  require(conditions.highVoltageVolt() == 25306.0, "wrong high voltage");
  require(conditions.minimumIonizingDedx() == 254.5,
          "wrong dE/dx normalization");
  require(conditions.meanPadAmplitude() == 652.8,
          "wrong mean pad amplitude");
  require(conditions.sector(1).driftVelocityCmPerMicrosecond == 6.998,
          "wrong negative-endcap drift velocity");
  require(conditions.sector(12).driftVelocityCmPerMicrosecond == 7.002,
          "wrong positive-endcap drift velocity");
  require(conditions.sector(1).gateClosed && conditions.sector(12).gateClosed,
          "wrong packed gate-state decoding");
}
