#include "delphi_edm4hep/Reconstruction/CentralTrackFit.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>

namespace delphi_edm4hep::reconstruction {
namespace {

double wrapped(double value) {
  return std::remainder(value, 2.0 * std::numbers::pi);
}

std::optional<std::array<double, 3>> solve3x3(
    std::array<std::array<double, 4>, 3> matrix) {
  for (std::size_t column = 0; column < 3; ++column) {
    auto pivot = column;
    for (auto row = column + 1; row < 3; ++row) {
      if (std::abs(matrix[row][column]) >
          std::abs(matrix[pivot][column])) {
        pivot = row;
      }
    }
    if (std::abs(matrix[pivot][column]) < 1e-12) {
      return std::nullopt;
    }
    std::swap(matrix[pivot], matrix[column]);
    const auto scale = matrix[column][column];
    for (auto entry = column; entry < 4; ++entry) {
      matrix[column][entry] /= scale;
    }
    for (std::size_t row = 0; row < 3; ++row) {
      if (row == column) {
        continue;
      }
      const auto factor = matrix[row][column];
      for (auto entry = column; entry < 4; ++entry) {
        matrix[row][entry] -= factor * matrix[column][entry];
      }
    }
  }
  return std::array<double, 3>{matrix[0][3], matrix[1][3], matrix[2][3]};
}

} // namespace

std::optional<CentralTrackFitResult>
fitCentralTrack(const std::vector<SpacePoint> &input,
                double transverseSigmaMm, double longitudinalSigmaMm,
                bool constrainToInteractionPoint) {
  if (input.size() < 4 || transverseSigmaMm <= 0 ||
      longitudinalSigmaMm <= 0) {
    return std::nullopt;
  }
  auto points = input;
  std::sort(points.begin(), points.end(), [](const auto &left, const auto &right) {
    return std::hypot(left.xMm, left.yMm) < std::hypot(right.xMm, right.yMm);
  });

  double sx{}, sy{}, sxx{}, syy{}, sxy{}, sb{}, sxb{}, syb{};
  for (const auto &point : points) {
    const auto b = -(point.xMm * point.xMm + point.yMm * point.yMm);
    sx += point.xMm;
    sy += point.yMm;
    sxx += point.xMm * point.xMm;
    syy += point.yMm * point.yMm;
    sxy += point.xMm * point.yMm;
    sb += b;
    sxb += point.xMm * b;
    syb += point.yMm * b;
  }
  const auto count = static_cast<double>(points.size());
  double centerX{};
  double centerY{};
  double constant{};
  if (constrainToInteractionPoint) {
    const auto determinant = sxx * syy - sxy * sxy;
    if (std::abs(determinant) < 1e-12) {
      return std::nullopt;
    }
    const auto d = (sxb * syy - syb * sxy) / determinant;
    const auto e = (syb * sxx - sxb * sxy) / determinant;
    centerX = -d / 2.0;
    centerY = -e / 2.0;
  } else {
    const auto circle = solve3x3({{{sxx, sxy, sx, sxb},
                                   {sxy, syy, sy, syb},
                                   {sx, sy, count, sb}}});
    if (!circle) {
      return std::nullopt;
    }
    centerX = -(*circle)[0] / 2.0;
    centerY = -(*circle)[1] / 2.0;
    constant = (*circle)[2];
  }
  const auto radiusSquared = centerX * centerX + centerY * centerY - constant;
  if (!std::isfinite(radiusSquared) || radiusSquared <= 0) {
    return std::nullopt;
  }
  const auto radius = std::sqrt(radiusSquared);
  double angularProgress{};
  auto previousAngle =
      std::atan2(points.front().yMm - centerY, points.front().xMm - centerX);
  for (std::size_t index = 1; index < points.size(); ++index) {
    const auto angle =
        std::atan2(points[index].yMm - centerY, points[index].xMm - centerX);
    angularProgress += wrapped(angle - previousAngle);
    previousAngle = angle;
  }
  if (std::abs(angularProgress) < 1e-8) {
    return std::nullopt;
  }
  const auto orientation = angularProgress > 0 ? 1 : -1;

  std::vector<double> arcLengths(points.size());
  const auto firstAngle = std::atan2(points.front().yMm - centerY,
                                     points.front().xMm - centerX);
  auto unwrappedAngle = firstAngle;
  previousAngle = firstAngle;
  for (std::size_t index = 1; index < points.size(); ++index) {
    const auto angle =
        std::atan2(points[index].yMm - centerY, points[index].xMm - centerX);
    unwrappedAngle += wrapped(angle - previousAngle);
    arcLengths[index] = orientation * radius * (unwrappedAngle - firstAngle);
    previousAngle = angle;
  }
  double ss{}, sz{}, sss{}, ssz{};
  for (std::size_t index = 0; index < points.size(); ++index) {
    ss += arcLengths[index];
    sz += points[index].zMm;
    sss += arcLengths[index] * arcLengths[index];
    ssz += arcLengths[index] * points[index].zMm;
  }
  const auto denominator = count * sss - ss * ss;
  if (std::abs(denominator) < 1e-12) {
    return std::nullopt;
  }
  const auto tanLambda = (count * ssz - ss * sz) / denominator;
  const auto zAtFirst = (sz - tanLambda * ss) / count;

  const auto centerDistance = std::hypot(centerX, centerY);
  if (centerDistance < 1e-12) {
    return std::nullopt;
  }
  const auto perigeeX = constrainToInteractionPoint
                            ? 0.0
                            : centerX * (1.0 - radius / centerDistance);
  const auto perigeeY = constrainToInteractionPoint
                            ? 0.0
                            : centerY * (1.0 - radius / centerDistance);
  const auto radialX = (perigeeX - centerX) / radius;
  const auto radialY = (perigeeY - centerY) / radius;
  const auto tangentX = orientation * -radialY;
  const auto tangentY = orientation * radialX;
  const auto phi = std::atan2(tangentY, tangentX);
  const auto d0 = -perigeeX * std::sin(phi) + perigeeY * std::cos(phi);
  const auto perigeeAngle = std::atan2(perigeeY - centerY,
                                       perigeeX - centerX);
  auto firstFromPerigee = orientation * wrapped(firstAngle - perigeeAngle);
  if (firstFromPerigee < 0) {
    firstFromPerigee += 2.0 * std::numbers::pi;
  }
  const auto z0 = zAtFirst - tanLambda * radius * firstFromPerigee;

  double chi2{};
  for (std::size_t index = 0; index < points.size(); ++index) {
    const auto radialResidual =
        std::hypot(points[index].xMm - centerX, points[index].yMm - centerY) -
        radius;
    const auto zResidual =
        points[index].zMm - (zAtFirst + tanLambda * arcLengths[index]);
    chi2 += radialResidual * radialResidual /
                (transverseSigmaMm * transverseSigmaMm) +
            zResidual * zResidual /
                (longitudinalSigmaMm * longitudinalSigmaMm);
  }
  return CentralTrackFitResult{d0,
                               phi,
                               -static_cast<double>(orientation) / radius,
                               z0,
                               tanLambda,
                               chi2,
                               static_cast<int>(2 * points.size()) - 5,
                               centerX,
                               centerY,
                               radius,
                               orientation};
}

} // namespace delphi_edm4hep::reconstruction
