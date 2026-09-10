#include "delphi_edm4hep/Simulation/InnerDetectorReadoutGeometry.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <numbers>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace delphi_edm4hep::simulation {
namespace {

const geometry::CargoRecord &record(const geometry::CargoDatabase &database,
                                    const std::string &path) {
  const geometry::CargoRecord *found{};
  for (const auto &candidate : database.records()) {
    if (candidate.kind == "CALB" && candidate.path == path) {
      if (found != nullptr) {
        throw std::runtime_error("duplicate ID calibration record: " + path);
      }
      found = &candidate;
    }
  }
  if (found == nullptr) {
    throw std::runtime_error("missing ID calibration record: " + path);
  }
  return *found;
}

std::vector<double> values(const geometry::CargoRecord &source,
                           std::string_view fieldName) {
  const auto *field = source.findField(fieldName);
  if (field == nullptr) {
    throw std::runtime_error("missing ID " + std::string(fieldName) +
                             " field: " + source.path);
  }
  auto text = field->value;
  for (const auto &line : field->continuation) {
    text += ' ';
    text += line;
  }
  std::replace(text.begin(), text.end(), ',', ' ');
  std::replace(text.begin(), text.end(), 'D', 'E');
  std::replace(text.begin(), text.end(), 'd', 'e');
  std::istringstream input(text);
  std::size_t count{};
  if (!(input >> count)) {
    throw std::runtime_error("invalid ID field count: " + source.path);
  }
  std::vector<double> result;
  double value{};
  while (input >> value) {
    result.push_back(value);
  }
  if (result.size() != count) {
    throw std::runtime_error("ID field count mismatch: " + source.path);
  }
  return result;
}

std::string numberedPath(std::string_view part, unsigned int number,
                         std::string_view sensor = {}) {
  std::ostringstream path;
  path << "/ID**/" << part << '/' << std::setw(4) << std::setfill('0')
       << number;
  if (!sensor.empty()) {
    path << ".SENS$" << sensor;
  }
  path << ".B";
  return path.str();
}

std::int32_t integer(double value, const std::string &context) {
  const auto rounded = std::lround(value);
  if (std::abs(value - static_cast<double>(rounded)) > 1e-8) {
    throw std::runtime_error("non-integral ID field value: " + context);
  }
  return static_cast<std::int32_t>(rounded);
}

template <std::size_t N>
void fillTriggerChannels(std::array<InnerDetectorTriggerChannel, N> &channels,
                         const std::vector<double> &calibration,
                         const std::vector<double> &status,
                         const std::string &context) {
  if (calibration.size() != 2 * N || status.size() != N) {
    throw std::runtime_error("invalid ID trigger channel payload: " + context);
  }
  for (std::size_t index = 0; index < N; ++index) {
    channels[index] = {static_cast<std::uint32_t>(index + 1),
                       {calibration[2 * index], calibration[2 * index + 1]},
                       integer(status[index], context)};
  }
}

} // namespace

InnerDetectorReadoutGeometry InnerDetectorReadoutGeometry::fromCargo(
    const geometry::CargoDatabase &database) {
  InnerDetectorReadoutGeometry result;

  const auto timeZeros =
      values(record(database, numberedPath("JET*", 1)), "SHAR");
  if (timeZeros.size() != 3) {
    throw std::runtime_error("invalid ID time-zero payload");
  }
  result.driftTimeZeroNs_ = timeZeros[0];
  result.cathodeTimeZeroNs_ = timeZeros[1];
  result.bunchTimeZeroNs_ = timeZeros[2];

  for (unsigned int sector = 1; sector <= result.jetSectors_.size(); ++sector) {
    const auto path = numberedPath("JET*", sector, "WIRE");
    const auto &source = record(database, path);
    const auto lead = values(source, "LEAD");
    const auto location = values(source, "LOCC");
    const auto size = values(source, "SIZC");
    const auto calibration = values(source, "CALW");
    const auto status = values(source, "STAT");
    constexpr std::size_t wires = 24;
    constexpr std::size_t calibrationWords = 21;
    if (lead.size() != 12 || integer(lead[0], path) != wires ||
        location.size() != 2 * wires || size.size() != 1 ||
        calibration.size() != wires * calibrationWords ||
        status.size() != wires) {
      throw std::runtime_error("invalid ID jet readout payload: " + path);
    }
    auto &destination = result.jetSectors_[sector - 1];
    destination.sector = sector;
    destination.halfLengthCm = 0.5 * size[0];
    for (std::size_t wire = 0; wire < wires; ++wire) {
      auto &channel = destination.wires[wire];
      channel.wire = wire + 1;
      channel.radiusCm = location[2 * wire];
      std::copy_n(calibration.begin() + wire * calibrationWords,
                  calibrationWords, channel.calibration.begin());
      channel.status = integer(status[wire], path);
    }
  }

  for (unsigned int layer = 1; layer <= result.triggerLayers_.size(); ++layer) {
    const auto anodePath = numberedPath("TRIG", layer, "WIRE");
    const auto cathodePath = numberedPath("TRIG", layer, "STRP");
    const auto &anode = record(database, anodePath);
    const auto &cathode = record(database, cathodePath);
    const auto anodeLead = values(anode, "LEAD");
    const auto anodeLocation = values(anode, "LOCC");
    const auto anodeSize = values(anode, "SIZC");
    const auto cathodeLead = values(cathode, "LEAD");
    const auto cathodeLocation = values(cathode, "LOCC");
    if (anodeLead.size() != 12 || cathodeLead.size() != 12 ||
        integer(anodeLead[0], anodePath) != 192 ||
        integer(cathodeLead[0], cathodePath) != 192 ||
        anodeLocation.size() != 3 || cathodeLocation.size() != 3 ||
        anodeSize.size() != 1) {
      throw std::runtime_error("invalid ID trigger geometry payload");
    }

    auto &destination = result.triggerLayers_[layer - 1];
    destination.layer = layer;
    destination.halfLengthCm = 0.5 * anodeSize[0];
    destination.anodeRadiusCm = anodeLocation[0];
    destination.anodeFirstPhiRadians =
        anodeLocation[1] * std::numbers::pi / 180.0;
    destination.anodePitchRadians = anodeLocation[2] * std::numbers::pi / 180.0;
    // SIGEOM advances odd layers by one wire pitch.
    if (layer % 2 == 1) {
      destination.anodeFirstPhiRadians += destination.anodePitchRadians;
    }
    destination.cathodeRadiusCm = cathodeLocation[0];
    destination.cathodeFirstZCm = cathodeLocation[1];
    destination.cathodeWidthCm = cathodeLocation[2];
    fillTriggerChannels(destination.anodes, values(anode, "CALW"),
                        values(anode, "STAT"), anodePath);
    fillTriggerChannels(destination.cathodes, values(cathode, "CALW"),
                        values(cathode, "STAT"), cathodePath);
  }

  return result;
}

} // namespace delphi_edm4hep::simulation
