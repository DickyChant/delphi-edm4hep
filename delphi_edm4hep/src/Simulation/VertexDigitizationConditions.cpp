#include "delphi_edm4hep/Simulation/VertexDigitizationConditions.h"

#include <stdexcept>

namespace delphi_edm4hep::simulation {
namespace {

VertexPlaquetteConditions makePlaquette(std::uint32_t pStrips,
                                        std::uint32_t nStrips, double nPitchCm,
                                        double pActiveLengthCm,
                                        double nActiveLengthCm) {
  return {pStrips, nStrips, 0.0050, nPitchCm, pActiveLengthCm, nActiveLengthCm};
}

} // namespace

VertexDigitizationConditions VertexDigitizationConditions::legacyV94c() {
  VertexDigitizationConditions conditions;
  conditions.layers_[0] = {24,
                           2,
                           384,
                           384,
                           2400.0,
                           1850.0,
                           5.0,
                           5.0,
                           {makePlaquette(384, 1152, 0.00495, 7.737, 1.915),
                            makePlaquette(384, 384, 0.00990, 5.836, 1.915),
                            {},
                            {}}};
  conditions.layers_[1] = {20,
                           4,
                           640,
                           640,
                           1550.0,
                           1850.0,
                           5.0,
                           5.0,
                           {makePlaquette(640, 0, 0.0, 0.0, 0.0),
                            makePlaquette(640, 0, 0.0, 0.0, 0.0),
                            makePlaquette(640, 1280, 0.00420, 5.444, 3.204),
                            makePlaquette(640, 640, 0.00840, 5.444, 3.204)}};
  conditions.layers_[2] = {24,
                           4,
                           640,
                           640,
                           850.0,
                           1200.0,
                           5.0,
                           5.0,
                           {makePlaquette(640, 1280, 0.00440, 5.836, 3.187),
                            makePlaquette(640, 640, 0.00440, 5.836, 3.187),
                            makePlaquette(640, 320, 0.00880, 5.836, 3.187),
                            makePlaquette(640, 320, 0.00880, 5.836, 3.187)}};
  return conditions;
}

const VertexLayerConditions &
VertexDigitizationConditions::layer(VertexBarrelLayer layerValue) const {
  const auto index = static_cast<std::size_t>(layerValue);
  if (index < 1 || index > layers_.size()) {
    throw std::out_of_range("invalid DELPHI vertex barrel layer");
  }
  return layers_[index - 1];
}

const VertexPlaquetteConditions &
VertexDigitizationConditions::plaquette(VertexBarrelLayer layerValue,
                                        std::size_t number) const {
  const auto &layerConditions = layer(layerValue);
  if (number < 1 || number > layerConditions.plaquettes) {
    throw std::out_of_range("invalid DELPHI vertex plaquette number");
  }
  return layerConditions.plaquette[number - 1];
}

} // namespace delphi_edm4hep::simulation
