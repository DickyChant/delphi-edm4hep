#include "delphi_edm4hep/Reconstruction/CentralTrackFit.h"
#include "delphi_edm4hep/Simulation/TpcReadoutGeometry.h"

#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/EventSetup.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/Framework/interface/global/EDProducer.h"
#include "FWCore/ParameterSet/interface/ConfigurationDescriptions.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ParameterSet/interface/ParameterSetDescription.h"
#include "FWCore/Utilities/interface/EDGetToken.h"
#include "FWCore/Utilities/interface/EDPutToken.h"
#include "FWCore/Utilities/interface/InputTag.h"
#include "FWCore/Utilities/interface/StreamID.h"
#include "edm4hep/TrackCollection.h"
#include "edm4hep/TrackState.h"
#include "edm4hep/TrackerHit3DCollection.h"

#include "Code4hep/PodioUtilities/setCollectionID.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <utility>
#include <vector>

namespace delphi_edm4hep {

class DelphiCentralTrackFitProducer final : public edm::global::EDProducer<> {
public:
  explicit DelphiCentralTrackFitProducer(const edm::ParameterSet &config)
      : inputToken_(consumes(config.getParameter<edm::InputTag>("tpcHits"))),
        outputToken_(produces<edm4hep::TrackCollection>("CentralTracks")),
        minimumRows_(config.getParameter<unsigned int>("minimumRows")),
        transverseSigmaMm_(config.getParameter<double>("transverseSigmaMm")),
        longitudinalSigmaMm_(
            config.getParameter<double>("longitudinalSigmaMm")),
        constrainToInteractionPoint_(
            config.getParameter<bool>("constrainToInteractionPoint")) {}

  static void fillDescriptions(edm::ConfigurationDescriptions &descriptions) {
    edm::ParameterSetDescription description;
    description.add<edm::InputTag>("tpcHits");
    description.add<unsigned int>("minimumRows", 8U);
    description.add<double>("transverseSigmaMm", 5.0);
    description.add<double>("longitudinalSigmaMm", 10.0);
    description.add<bool>("constrainToInteractionPoint", true);
    descriptions.addDefault(description);
  }

private:
  void produce(edm::StreamID, edm::Event &event,
               const edm::EventSetup &) const final {
    struct RowAccumulator {
      double x{};
      double y{};
      double z{};
      unsigned int count{};
      std::vector<std::size_t> hitIndices;
    };
    using Sector = std::pair<std::uint32_t, std::uint32_t>;
    std::map<Sector, std::map<std::uint32_t, RowAccumulator>> rows;
    const auto &hits = event.get(inputToken_);
    for (std::size_t index = 0; index < hits.size(); ++index) {
      const auto hit = hits[index];
      const auto address =
          simulation::TpcReadoutGeometry::decodeCellId(hit.getCellID());
      const auto position = hit.getPosition();
      auto &row = rows[{address.endcap, address.sector}][address.row];
      row.x += position[0];
      row.y += position[1];
      row.z += position[2];
      ++row.count;
      row.hitIndices.push_back(index);
    }

    edm4hep::TrackCollection output;
    for (const auto &[sector, sectorRows] : rows) {
      if (sectorRows.size() < minimumRows_) {
        continue;
      }
      std::vector<reconstruction::SpacePoint> points;
      std::vector<std::size_t> hitIndices;
      points.reserve(sectorRows.size());
      for (const auto &[rowNumber, row] : sectorRows) {
        static_cast<void>(rowNumber);
        points.push_back(
            {row.x / row.count, row.y / row.count, row.z / row.count});
        hitIndices.insert(hitIndices.end(), row.hitIndices.begin(),
                          row.hitIndices.end());
      }
      const auto fit = reconstruction::fitCentralTrack(
          points, transverseSigmaMm_, longitudinalSigmaMm_,
          constrainToInteractionPoint_);
      if (!fit) {
        continue;
      }
      edm4hep::TrackState state{};
      state.location = edm4hep::TrackState::AtIP;
      state.D0 = static_cast<float>(fit->d0Mm);
      state.phi = static_cast<float>(fit->phiRadians);
      state.omega = static_cast<float>(fit->omegaPerMm);
      state.Z0 = static_cast<float>(fit->z0Mm);
      state.tanLambda = static_cast<float>(fit->tanLambda);
      state.time = 0.0F;
      state.referencePoint = {0.0F, 0.0F, 0.0F};
      using P = edm4hep::TrackParams;
      const auto radialSpan = std::max(
          1.0, std::hypot(points.back().xMm, points.back().yMm) -
                   std::hypot(points.front().xMm, points.front().yMm));
      state.covMatrix.setValue(transverseSigmaMm_ * transverseSigmaMm_,
                               P::d0, P::d0);
      state.covMatrix.setValue(
          std::pow(transverseSigmaMm_ / radialSpan, 2), P::phi, P::phi);
      state.covMatrix.setValue(
          std::pow(transverseSigmaMm_ / (radialSpan * radialSpan), 2),
          P::omega, P::omega);
      state.covMatrix.setValue(longitudinalSigmaMm_ * longitudinalSigmaMm_,
                               P::z0, P::z0);
      state.covMatrix.setValue(
          std::pow(longitudinalSigmaMm_ / radialSpan, 2), P::tanLambda,
          P::tanLambda);

      auto track = output.create();
      track.setType(constrainToInteractionPoint_ ? 1 : 0);
      track.setChi2(static_cast<float>(fit->chi2));
      track.setNdf(fit->ndf);
      track.setNholes(static_cast<int>(16 - std::min<std::size_t>(16, sectorRows.size())));
      track.addToTrackStates(state);
      for (const auto hitIndex : hitIndices) {
        track.addToTrackerHits(hits.at(hitIndex));
      }
    }
    c4h::setCollectionID(output, event, *this, outputToken_);
    event.emplace(outputToken_, std::move(output));
  }

  const edm::EDGetTokenT<edm4hep::TrackerHit3DCollection> inputToken_;
  const edm::EDPutTokenT<edm4hep::TrackCollection> outputToken_;
  const std::size_t minimumRows_;
  const double transverseSigmaMm_;
  const double longitudinalSigmaMm_;
  const bool constrainToInteractionPoint_;
};

} // namespace delphi_edm4hep

DEFINE_FWK_MODULE(delphi_edm4hep::DelphiCentralTrackFitProducer);
