#include "delphi_edm4hep/Simulation/VertexDigitizationConditions.h"

#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

void require(bool condition, const char *message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

bool close(double left, double right) {
  return std::abs(left - right) < 1.0e-12;
}

} // namespace

int main() {
  using delphi_edm4hep::simulation::VertexBarrelLayer;
  using delphi_edm4hep::simulation::VertexDigitizationConditions;

  const auto conditions = VertexDigitizationConditions::legacyV94c();
  const auto &closer = conditions.layer(VertexBarrelLayer::Closer);
  const auto &inner = conditions.layer(VertexBarrelLayer::Inner);
  const auto &outer = conditions.layer(VertexBarrelLayer::Outer);

  require(closer.modules == 24 && closer.plaquettes == 2,
          "closer topology differs from SVPARW");
  require(inner.modules == 20 && inner.plaquettes == 4,
          "inner topology differs from SVPARW");
  require(outer.modules == 24 && outer.plaquettes == 4,
          "outer topology differs from SVPARW");
  require(closer.pReadoutChannelsPerHalfModule == 384 &&
              inner.pReadoutChannelsPerHalfModule == 640 &&
              outer.pReadoutChannelsPerHalfModule == 640,
          "readout-channel counts differ from SVBCAL");

  require(
      close(conditions.plaquette(VertexBarrelLayer::Closer, 1).pReadoutPitchCm,
            0.0050) &&
          close(conditions.plaquette(VertexBarrelLayer::Closer, 1)
                    .nReadoutPitchCm,
                0.00495) &&
          close(conditions.plaquette(VertexBarrelLayer::Closer, 2)
                    .nReadoutPitchCm,
                0.00990),
      "closer strip pitches differ from SVBCAL");
  require(
      conditions.plaquette(VertexBarrelLayer::Inner, 1).nStrips == 0 &&
          conditions.plaquette(VertexBarrelLayer::Inner, 3).nStrips == 1280 &&
          close(
              conditions.plaquette(VertexBarrelLayer::Inner, 4).nReadoutPitchCm,
              0.00840),
      "inner inactive/active plaquettes differ from SVBCAL");
  require(
      conditions.plaquette(VertexBarrelLayer::Outer, 1).nStrips == 1280 &&
          conditions.plaquette(VertexBarrelLayer::Outer, 4).nStrips == 320 &&
          close(
              conditions.plaquette(VertexBarrelLayer::Outer, 3).nReadoutPitchCm,
              0.00880),
      "outer strip layout differs from SVBCAL");

  require(close(closer.pNoiseElectrons, 2400.0) &&
              close(closer.nNoiseElectrons, 1850.0) &&
              close(inner.pNoiseElectrons, 1550.0) &&
              close(outer.pNoiseElectrons, 850.0) &&
              close(outer.nNoiseElectrons, 1200.0),
          "VD noise values differ from SVBINI");
  require(close(closer.pThresholdSigma, 5.0) &&
              close(outer.nThresholdSigma, 5.0),
          "VD thresholds differ from SVBINI");
  require(close(conditions.trackingStepCm(), 0.001) &&
              conditions.minimumActiveSteps() == 3 &&
              close(conditions.electronsPerAdc(), 1000.0) &&
              close(conditions.lorentzShiftCm(), 0.0008),
          "VD global response values differ from VDSIM");
  require(!conditions.crossTalkEnabled() && conditions.noiseClustersEnabled() &&
              conditions.minimumNoiseClusterSize() == 4,
          "VD default response switches differ from SVBINI");
  require(close(conditions.crossTalkFractions()[0], 0.7490) &&
              close(conditions.crossTalkFractions()[3], 0.0078),
          "VD cross-talk kernel differs from SVBINI");

  std::cout << "Vertex digitization conditions closure passed\n";
}
