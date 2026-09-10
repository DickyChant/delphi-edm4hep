#include "delphi_edm4hep/Simulation/TpcDigitizationConditions.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace delphi_edm4hep::simulation {
namespace {

const geometry::CargoRecord &record(const geometry::CargoDatabase &database,
                                    std::string_view path) {
  const geometry::CargoRecord *found{};
  for (const auto &candidate : database.records()) {
    if (candidate.kind == "CALB" && candidate.path == path) {
      if (found != nullptr) {
        throw std::runtime_error("duplicate TPC conditions record: " +
                                 std::string(path));
      }
      found = &candidate;
    }
  }
  if (found == nullptr) {
    throw std::runtime_error("missing TPC conditions record: " +
                             std::string(path));
  }
  return *found;
}

std::vector<double> values(const geometry::CargoRecord &source,
                           std::string_view fieldName) {
  const auto *field = source.findField(fieldName);
  if (field == nullptr) {
    throw std::runtime_error("missing TPC conditions field " +
                             std::string(fieldName) + ": " + source.path);
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
    throw std::runtime_error("invalid TPC conditions field count: " +
                             source.path);
  }
  std::vector<double> result;
  double value{};
  while (input >> value) {
    result.push_back(value);
  }
  if (result.size() != count) {
    throw std::runtime_error("TPC conditions field count mismatch: " +
                             source.path);
  }
  return result;
}

} // namespace

TpcDigitizationConditions TpcDigitizationConditions::fromCargo(
    const geometry::CargoDatabase &database,
    const TpcReadoutGeometry &readout) {
  const auto &global = record(database, "/TPC*.B");
  const auto slow = values(global, "SLOW");
  const auto user = values(global, "USER");
  const auto status = values(global, "ISLO");
  if (slow.size() != 18 || user.size() != 16 || status.size() != 16) {
    throw std::runtime_error("invalid global TPC digitization conditions");
  }

  TpcDigitizationConditions result;
  result.highVoltageVolt_ = slow[5] * 1000.0;
  result.minimumIonizingDedx_ = user[0];
  result.meanPadAmplitude_ = user[13];
  if (result.highVoltageVolt_ <= 0 || result.minimumIonizingDedx_ <= 0 ||
      result.meanPadAmplitude_ <= 0) {
    throw std::runtime_error("non-positive global TPC conditions");
  }

  std::array<double, 2> driftVelocity{};
  for (unsigned int endcap = 0; endcap < 2; ++endcap) {
    const auto endcapPath =
        std::string("/TPC*/ENP") + std::to_string(endcap) + ".B";
    const auto endcapSlow = values(record(database, endcapPath), "SLOW");
    if (endcapSlow.size() != 14 || endcapSlow[0] <= 0) {
      throw std::runtime_error("invalid TPC endcap drift velocity: " +
                               endcapPath);
    }
    driftVelocity[endcap] = endcapSlow[0];
  }

  const auto gateWord = static_cast<std::uint32_t>(std::llround(status[6]));
  result.sectors_.reserve(readout.sectors().size());
  for (const auto &sector : readout.sectors()) {
    if (sector.geometrySector >= 12 || sector.endcap >= driftVelocity.size()) {
      throw std::runtime_error("TPC sector exceeds packed conditions fields");
    }
    const auto raw = (gateWord >> (2U * sector.geometrySector)) & 0x3U;
    auto decoded = static_cast<int>(raw) - 1;
    // Preserve STCALB's recovery for invalid two-bit database values.
    if (decoded < 0 || decoded >= 2) {
      decoded = decoded == 2 ? 1 : 0;
    }
    result.sectors_.push_back(
        {sector.readoutSector, sector.geometrySector, sector.endcap,
         driftVelocity[sector.endcap], decoded == 1});
  }
  return result;
}

const TpcSectorConditions &
TpcDigitizationConditions::sector(unsigned int readoutSector) const {
  const auto found =
      std::find_if(sectors_.begin(), sectors_.end(), [&](const auto &entry) {
        return entry.readoutSector == readoutSector;
      });
  if (found == sectors_.end()) {
    throw std::runtime_error("unknown TPC readout sector");
  }
  return *found;
}

} // namespace delphi_edm4hep::simulation
