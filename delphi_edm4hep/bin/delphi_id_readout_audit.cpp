#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Simulation/InnerDetectorReadoutGeometry.h"

#include <algorithm>
#include <exception>
#include <iostream>

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: " << argv[0] << " CERNSNAP*_DELSIM.ASC\n";
    return 2;
  }
  try {
    using namespace delphi_edm4hep;
    const auto database = geometry::CargoDatabase::readFile(argv[1]);
    const auto readout =
        simulation::InnerDetectorReadoutGeometry::fromCargo(database);
    unsigned int jetBadChannels{};
    unsigned int anodeBadChannels{};
    unsigned int cathodeBadChannels{};
    for (const auto &sector : readout.jetSectors()) {
      jetBadChannels +=
          std::count_if(sector.wires.begin(), sector.wires.end(),
                        [](const auto &wire) { return wire.status != 0; });
    }
    for (const auto &layer : readout.triggerLayers()) {
      anodeBadChannels += std::count_if(
          layer.anodes.begin(), layer.anodes.end(),
          [](const auto &channel) { return channel.status != 0; });
      cathodeBadChannels += std::count_if(
          layer.cathodes.begin(), layer.cathodes.end(),
          [](const auto &channel) { return channel.status != 0; });
    }
    const auto &firstJet = readout.jetSectors().front();
    const auto &firstTrigger = readout.triggerLayers().front();
    const auto &lastTrigger = readout.triggerLayers().back();
    std::cout
        << "jet_sectors=" << readout.jetSectors().size() << '\n'
        << "jet_wires_per_sector=" << firstJet.wires.size() << '\n'
        << "jet_half_length_cm=" << firstJet.halfLengthCm << '\n'
        << "jet_first_wire_radius_cm=" << firstJet.wires.front().radiusCm
        << '\n'
        << "jet_last_wire_radius_cm=" << firstJet.wires.back().radiusCm << '\n'
        << "trigger_layers=" << readout.triggerLayers().size() << '\n'
        << "trigger_anodes_per_layer=" << firstTrigger.anodes.size() << '\n'
        << "trigger_cathodes_per_layer=" << firstTrigger.cathodes.size() << '\n'
        << "trigger_first_anode_radius_cm=" << firstTrigger.anodeRadiusCm
        << '\n'
        << "trigger_last_anode_radius_cm=" << lastTrigger.anodeRadiusCm << '\n'
        << "trigger_first_cathode_radius_cm=" << firstTrigger.cathodeRadiusCm
        << '\n'
        << "trigger_last_cathode_radius_cm=" << lastTrigger.cathodeRadiusCm
        << '\n'
        << "drift_time_zero_ns=" << readout.driftTimeZeroNs() << '\n'
        << "cathode_time_zero_ns=" << readout.cathodeTimeZeroNs() << '\n'
        << "bunch_time_zero_ns=" << readout.bunchTimeZeroNs() << '\n'
        << "dead_time_us=" << readout.deadTimeMicroseconds() << '\n'
        << "cathode_anode_ratio=" << readout.cathodeToAnodeRatio() << '\n'
        << "cathode_sigma_cm=" << readout.cathodeDistributionSigmaCm() << '\n'
        << "jet_bad_channels=" << jetBadChannels << '\n'
        << "anode_bad_channels=" << anodeBadChannels << '\n'
        << "cathode_bad_channels=" << cathodeBadChannels << '\n';
  } catch (const std::exception &error) {
    std::cerr << "delphi_id_readout_audit: " << error.what() << '\n';
    return 1;
  }
}
