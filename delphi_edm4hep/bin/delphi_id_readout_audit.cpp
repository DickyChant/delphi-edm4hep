#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Simulation/InnerDetectorJetResponse.h"
#include "delphi_edm4hep/Simulation/InnerDetectorReadoutGeometry.h"

#include <algorithm>
#include <cmath>
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
    const auto jetResponse = simulation::InnerDetectorJetResponse::fromCargo(
        database, readout, 1.2312434);
    unsigned int jetBadChannels{};
    unsigned int anodeBadChannels{};
    unsigned int cathodeBadChannels{};
    unsigned int triggerRoundTripMismatches{};
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
      for (const auto &channel : layer.anodes) {
        const auto phi = readout.anodePhi(layer.layer, channel.channel);
        const auto address = readout.locateAnode(
            layer.layer, layer.anodeRadiusCm * std::cos(phi),
            layer.anodeRadiusCm * std::sin(phi));
        triggerRoundTripMismatches +=
            !address ||
            address->side != simulation::InnerDetectorTriggerSide::Anode ||
            address->channel != channel.channel;
      }
      for (const auto &channel : layer.cathodes) {
        const auto address = readout.locateCathode(
            layer.layer, readout.cathodeZ(layer.layer, channel.channel));
        triggerRoundTripMismatches +=
            !address ||
            address->side != simulation::InnerDetectorTriggerSide::Cathode ||
            address->channel != channel.channel;
      }
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
        << "jet_lorentz_angle_deg="
        << jetResponse.lorentzAngleRadians() * 180.0 / std::acos(-1.0) << '\n'
        << "jet_boundary_angle_deg="
        << jetResponse.boundaryAngleRadians() * 180.0 / std::acos(-1.0) << '\n'
        << "jet_s1_w1_left_edge_ns="
        << jetResponse.driftTimeNs(1, 1,
                                   simulation::InnerDetectorDriftSide::Left,
                                   -std::acos(-1.0) / 24.0)
        << '\n'
        << "jet_s1_w1_right_edge_ns="
        << jetResponse.driftTimeNs(1, 1,
                                   simulation::InnerDetectorDriftSide::Right,
                                   std::acos(-1.0) / 24.0)
        << '\n'
        << "jet_max_drift_time_ns=" << jetResponse.maximumDriftTimeNs() << '\n'
        << "jet_bad_channels=" << jetBadChannels << '\n'
        << "anode_bad_channels=" << anodeBadChannels << '\n'
        << "cathode_bad_channels=" << cathodeBadChannels << '\n';
    std::cout << "trigger_round_trip_mismatches=" << triggerRoundTripMismatches
              << '\n';
  } catch (const std::exception &error) {
    std::cerr << "delphi_id_readout_audit: " << error.what() << '\n';
    return 1;
  }
}
