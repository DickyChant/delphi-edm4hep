#include "delphi_edm4hep/Reconstruction/CentralTrackFit.h"

#include <cmath>
#include <stdexcept>
#include <vector>

int main() {
  using namespace delphi_edm4hep::reconstruction;
  constexpr double radiusMm = 10000.0;
  constexpr double tanLambda = 0.35;
  constexpr double z0Mm = -2.5;
  std::vector<SpacePoint> points;
  for (unsigned int index = 1; index <= 16; ++index) {
    const auto arcAngle = 0.003 * index;
    const auto angle = -std::acos(-1.0) / 2.0 + arcAngle;
    points.push_back({radiusMm * std::cos(angle),
                      radiusMm + radiusMm * std::sin(angle),
                      z0Mm + tanLambda * radiusMm * arcAngle});
  }
  const auto fit = fitCentralTrack(points, 0.1, 0.1);
  if (!fit || std::abs(fit->d0Mm) > 1e-6 ||
      std::abs(fit->phiRadians) > 1e-6 ||
      std::abs(fit->omegaPerMm + 1.0 / radiusMm) > 1e-10 ||
      std::abs(fit->z0Mm - z0Mm) > 1e-6 ||
      std::abs(fit->tanLambda - tanLambda) > 1e-9 || fit->ndf != 27 ||
      fit->chi2 > 1e-10) {
    throw std::runtime_error("native central helix fit changed");
  }
  const auto constrained = fitCentralTrack(points, 0.1, 0.1, true);
  if (!constrained || std::abs(constrained->d0Mm) > 1e-12 ||
      std::abs(constrained->omegaPerMm + 1.0 / radiusMm) > 1e-10 ||
      std::abs(constrained->z0Mm - z0Mm) > 1e-6) {
    throw std::runtime_error("IP-constrained central helix fit changed");
  }
}
