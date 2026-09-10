#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Geometry/GeometryModel.h"
#include "delphi_edm4hep/Simulation/TpcDigitizationConditions.h"
#include "delphi_edm4hep/Simulation/TpcPadResponse.h"
#include "delphi_edm4hep/Simulation/TpcReadoutGeometry.h"

#include <algorithm>
#include <cmath>
#include <exception>
#include <iostream>
#include <numbers>
#include <numeric>

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: " << argv[0] << " CERNSNAP*_DELSIM.ASC\n";
    return 2;
  }
  try {
    const auto database =
        delphi_edm4hep::geometry::CargoDatabase::readFile(argv[1]);
    const auto model =
        delphi_edm4hep::geometry::GeometryModel::fromCargo(database, argv[1]);
    const auto readout =
        delphi_edm4hep::simulation::TpcReadoutGeometry::fromCargo(database,
                                                                  model);
    const auto pads =
        std::accumulate(readout.rows().begin(), readout.rows().end(), 0U,
                        [](unsigned int total, const auto &row) {
                          return total + row.padCount;
                        });
    const delphi_edm4hep::simulation::TpcPadResponse response(readout);
    const auto conditions =
        delphi_edm4hep::simulation::TpcDigitizationConditions::fromCargo(
            database, readout);
    const auto closedGates =
        std::count_if(conditions.sectors().begin(), conditions.sectors().end(),
                      [](const auto &sector) { return sector.gateClosed; });
    unsigned int centrePadMismatches{};
    unsigned int stampaResponseMismatches{};
    for (const auto &sector : readout.sectors()) {
      const auto angle = sector.rotationDegrees * std::numbers::pi / 180.0;
      const auto radius = readout.rows().front().radiusCm;
      const auto localPhi =
          -0.5 * (std::numbers::pi / 3.0) /
          static_cast<double>(readout.rows().front().padCount);
      const auto localX = radius * std::sin(localPhi);
      const auto localY = radius * std::cos(localPhi);
      const auto address =
          readout.locatePad(sector.translationXCm + std::cos(angle) * localX -
                                std::sin(angle) * localY,
                            sector.translationYCm + std::sin(angle) * localX +
                                std::cos(angle) * localY,
                            sector.endcap == 0 ? -1.0 : 1.0);
      if (!address || address->sector != sector.readoutSector ||
          address->row != 1 ||
          address->pad != readout.rows().front().padCount / 2) {
        std::cerr << "centre mismatch sector=" << sector.readoutSector
                  << " mapped=" << (address ? address->sector : 0)
                  << " row=" << (address ? address->row : 0)
                  << " pad=" << (address ? address->pad : 0) << '\n';
        ++centrePadMismatches;
      }
      const auto induced = response.induce(
          sector.translationXCm + std::cos(angle) * localX -
              std::sin(angle) * localY,
          sector.translationYCm + std::sin(angle) * localX +
              std::cos(angle) * localY,
          sector.endcap == 0 ? -140.0 : 140.0, -std::sin(angle),
          std::cos(angle), 1.0);
      const auto peak =
          std::max_element(induced.begin(), induced.end(),
                           [](const auto &left, const auto &right) {
                             return left.signal < right.signal;
                           });
      if (induced.size() != 5 || peak == induced.end() ||
          peak->address.pad != readout.rows().front().padCount / 2) {
        ++stampaResponseMismatches;
      }
    }
    std::cout << "rows=" << readout.rows().size() << '\n'
              << "pads_per_sector=" << pads << '\n'
              << "total_pads=" << pads * readout.sectors().size() << '\n'
              << "sectors=" << readout.sectors().size() << '\n'
              << "first_row_radius_cm=" << readout.rows().front().radiusCm
              << '\n'
              << "last_row_radius_cm=" << readout.rows().back().radiusCm << '\n'
              << "drift_half_length_cm=" << readout.driftHalfLengthCm() << '\n'
              << "high_voltage_volt=" << conditions.highVoltageVolt() << '\n'
              << "minimum_ionizing_dedx="
              << conditions.minimumIonizingDedx() << '\n'
              << "mean_pad_amplitude=" << conditions.meanPadAmplitude() << '\n'
              << "drift_velocity_endcap0_cm_per_us="
              << conditions.sector(1).driftVelocityCmPerMicrosecond << '\n'
              << "drift_velocity_endcap1_cm_per_us="
              << conditions.sector(12).driftVelocityCmPerMicrosecond << '\n'
              << "closed_gates=" << closedGates << '\n'
              << "centre_pad_mismatches=" << centrePadMismatches << '\n'
              << "stampa_response_mismatches=" << stampaResponseMismatches
              << '\n';
  } catch (const std::exception &error) {
    std::cerr << "delphi_tpc_readout_audit: " << error.what() << '\n';
    return 1;
  }
}
