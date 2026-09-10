#pragma once

#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Simulation/TpcReadoutGeometry.h"

#include <vector>

namespace delphi_edm4hep::simulation {

struct TpcSectorConditions {
  unsigned int readoutSector{};
  unsigned int geometrySector{};
  unsigned int endcap{};
  double driftVelocityCmPerMicrosecond{};
  bool gateClosed{};
};

class TpcDigitizationConditions {
public:
  static TpcDigitizationConditions
  fromCargo(const geometry::CargoDatabase &database,
            const TpcReadoutGeometry &readout);

  double highVoltageVolt() const { return highVoltageVolt_; }
  double minimumIonizingDedx() const { return minimumIonizingDedx_; }
  double meanPadAmplitude() const { return meanPadAmplitude_; }
  const std::vector<TpcSectorConditions> &sectors() const { return sectors_; }

  const TpcSectorConditions &sector(unsigned int readoutSector) const;

private:
  double highVoltageVolt_{};
  double minimumIonizingDedx_{};
  double meanPadAmplitude_{};
  std::vector<TpcSectorConditions> sectors_;
};

} // namespace delphi_edm4hep::simulation
