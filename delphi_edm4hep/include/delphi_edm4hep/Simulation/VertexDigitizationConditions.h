#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace delphi_edm4hep::simulation {

enum class VertexBarrelLayer : std::uint8_t {
  Closer = 1,
  Inner = 2,
  Outer = 3,
};

struct VertexPlaquetteConditions {
  std::uint32_t pStrips{};
  std::uint32_t nStrips{};
  double pReadoutPitchCm{};
  double nReadoutPitchCm{};
  double pActiveLengthCm{};
  double nActiveLengthCm{};
};

struct VertexLayerConditions {
  std::uint32_t modules{};
  std::uint32_t plaquettes{};
  std::uint32_t pReadoutChannelsPerHalfModule{};
  std::uint32_t nReadoutChannelsPerHalfModule{};
  double pNoiseElectrons{};
  double nNoiseElectrons{};
  double pThresholdSigma{};
  double nThresholdSigma{};
  std::array<VertexPlaquetteConditions, 4> plaquette;
};

class VertexDigitizationConditions {
public:
  // Defaults hard-coded by VDSIM 6.3 in SVBCAL/SVBINI for the 1994 geometry.
  static VertexDigitizationConditions legacyV94c();

  const VertexLayerConditions &layer(VertexBarrelLayer layer) const;
  const VertexPlaquetteConditions &plaquette(VertexBarrelLayer layer,
                                             std::size_t number) const;

  double trackingStepCm() const { return trackingStepCm_; }
  std::uint32_t minimumActiveSteps() const { return minimumActiveSteps_; }
  double electronsPerAdc() const { return electronsPerAdc_; }
  double electronHoleEnergyEv() const { return electronHoleEnergyEv_; }
  double lorentzShiftCm() const { return lorentzShiftCm_; }
  bool crossTalkEnabled() const { return crossTalkEnabled_; }
  bool noiseClustersEnabled() const { return noiseClustersEnabled_; }
  std::uint32_t minimumNoiseClusterSize() const {
    return minimumNoiseClusterSize_;
  }
  const std::array<double, 4> &crossTalkFractions() const {
    return crossTalkFractions_;
  }

private:
  std::array<VertexLayerConditions, 3> layers_;
  double trackingStepCm_{0.001};
  std::uint32_t minimumActiveSteps_{3};
  double electronsPerAdc_{1000.0};
  // Silicon pair-creation energy used to connect Geant4 energy deposition to
  // VDSIM's electron-domain pulse/noise calibration.
  double electronHoleEnergyEv_{3.6};
  double lorentzShiftCm_{0.0008};
  bool crossTalkEnabled_{false};
  bool noiseClustersEnabled_{true};
  std::uint32_t minimumNoiseClusterSize_{4};
  std::array<double, 4> crossTalkFractions_{0.7490, 0.0991, 0.0180, 0.0078};
};

} // namespace delphi_edm4hep::simulation
