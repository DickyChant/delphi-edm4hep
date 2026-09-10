#pragma once

#include "delphi_edm4hep/Geometry/CargoDatabase.h"

#include <array>
#include <cstdint>

namespace delphi_edm4hep::simulation {

struct InnerDetectorJetWire {
  std::uint32_t wire{};
  double radiusCm{};
  std::array<double, 21> calibration{};
  std::int32_t status{};
};

struct InnerDetectorJetSector {
  std::uint32_t sector{};
  double halfLengthCm{};
  std::array<InnerDetectorJetWire, 24> wires;
};

struct InnerDetectorTriggerChannel {
  std::uint32_t channel{};
  std::array<double, 2> calibration{};
  std::int32_t status{};
};

struct InnerDetectorTriggerLayer {
  std::uint32_t layer{};
  double halfLengthCm{};
  double anodeRadiusCm{};
  double anodeFirstPhiRadians{};
  double anodePitchRadians{};
  double cathodeRadiusCm{};
  double cathodeFirstZCm{};
  double cathodeWidthCm{};
  std::array<InnerDetectorTriggerChannel, 192> anodes;
  std::array<InnerDetectorTriggerChannel, 192> cathodes;
};

class InnerDetectorReadoutGeometry {
public:
  static InnerDetectorReadoutGeometry
  fromCargo(const geometry::CargoDatabase &database);

  const std::array<InnerDetectorJetSector, 24> &jetSectors() const {
    return jetSectors_;
  }
  const std::array<InnerDetectorTriggerLayer, 5> &triggerLayers() const {
    return triggerLayers_;
  }

  double driftTimeZeroNs() const { return driftTimeZeroNs_; }
  double cathodeTimeZeroNs() const { return cathodeTimeZeroNs_; }
  double bunchTimeZeroNs() const { return bunchTimeZeroNs_; }
  double deadTimeMicroseconds() const { return deadTimeMicroseconds_; }
  double cathodeToAnodeRatio() const { return cathodeToAnodeRatio_; }
  double cathodeDistributionSigmaCm() const {
    return cathodeDistributionSigmaCm_;
  }

private:
  std::array<InnerDetectorJetSector, 24> jetSectors_;
  std::array<InnerDetectorTriggerLayer, 5> triggerLayers_;
  double driftTimeZeroNs_{};
  double cathodeTimeZeroNs_{};
  double bunchTimeZeroNs_{};
  double deadTimeMicroseconds_{0.055};
  double cathodeToAnodeRatio_{2.3875};
  double cathodeDistributionSigmaCm_{0.286};
};

} // namespace delphi_edm4hep::simulation
