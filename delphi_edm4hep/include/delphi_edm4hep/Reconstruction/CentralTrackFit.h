#pragma once

#include <array>
#include <optional>
#include <vector>

namespace delphi_edm4hep::reconstruction {

struct SpacePoint {
  double xMm{};
  double yMm{};
  double zMm{};
};

struct CentralTrackFitResult {
  double d0Mm{};
  double phiRadians{};
  double omegaPerMm{};
  double z0Mm{};
  double tanLambda{};
  double chi2{};
  int ndf{};
  double circleCenterXMm{};
  double circleCenterYMm{};
  double circleRadiusMm{};
  int transverseOrientation{};
};

std::optional<CentralTrackFitResult>
fitCentralTrack(const std::vector<SpacePoint> &points,
                double transverseSigmaMm = 1.0,
                double longitudinalSigmaMm = 10.0,
                bool constrainToInteractionPoint = false);

} // namespace delphi_edm4hep::reconstruction
