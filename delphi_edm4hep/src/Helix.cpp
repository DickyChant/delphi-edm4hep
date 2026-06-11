// Helix.cpp — implementation.
//
// The conversion kernels are transplanted verbatim from the former
// BasisConversion.cpp (TE-basis 6×6 Jacobian) and PerigeeTrack.cpp
// (perigee 5×5 Jacobian + weight-matrix inversion); the numbers are
// unchanged, only the packaging differs.

#include "delphi_edm4hep/Helix.h"

#include <edm4hep/Constants.h>   // edm4hep::TrackParams

#include <TMatrixD.h>
#include <TMatrixDSym.h>

#include <cmath>

namespace delphi_edm4hep {

namespace {

constexpr double kCm2Mm = 10.0;

// ---- perigee (raw DELPHI) -> helix 5×5 Jacobian -------------------------
//   raw   : (d0, z0, theta, phi, invR)
//   helix : (D0, phi, omega, Z0, tanLambda)
TMatrixD perigeeJacobian(double theta_dp) {
  TMatrixD J(5, 5);
  J.Zero();
  const double s      = std::sin(theta_dp);
  const double inv_s2 = (s != 0.0) ? 1.0 / (s * s) : 0.0;
  J(0, 0) = -kCm2Mm;
  J(1, 3) = +1.0;
  J(2, 4) = +1.0 / kCm2Mm;
  J(3, 1) = +kCm2Mm;
  J(4, 2) = -inv_s2;
  return J;
}

// ---- TE-basis -> helix 6×6 Jacobian -------------------------------------
//   TE    : (c1, c2, c3, theta, phi, invP)  [cartesian c1=x,c2=y,c3=z]
//   helix : (D0, phi, omega, Z0, tanLambda, time)
TMatrixD teJacobian(double theta, double phi, double invP,
                    int charge_signed, double B_tesla, bool invPt) {
  TMatrixD J(6, 6);
  J.Zero();
  const double s = std::sin(theta);
  const double c = std::cos(theta);
  if (std::fabs(s) < 1e-9) return J;
  const double inv_s2 = 1.0 / (s * s);
  const double qB     = static_cast<double>(charge_signed) * B_tesla;
  J(0, 0) = -std::sin(phi) * kCm2Mm;
  J(0, 1) =  std::cos(phi) * kCm2Mm;
  J(1, 4) = 1.0;
  // omega = transverse curvature. The omega-row partials must match whichever
  // momentum form fromTrackElement uses: omega = kOmega*qB*invPt (no theta dep)
  // when the bank word is 1/|p_T|, else omega = kOmega*qB*invP/sin(theta).
  if (invPt) {
    J(2, 3) = 0.0;
    J(2, 5) = kOmega * qB;
  } else {
    J(2, 3) = -kOmega * qB * c * invP * inv_s2;   // d/dtheta[kOmega*qB*invP/sin]
    J(2, 5) =  kOmega * qB / s;                    // d/d(invP)
  }
  J(3, 2) = kCm2Mm;
  J(4, 3) = -inv_s2;
  return J;
}

TMatrixDSym covFromArray(const CovMatrix6& cov) {
  TMatrixDSym out(6);
  for (int i = 0; i < 6; ++i)
    for (int j = 0; j <= i; ++j) {
      const double v = static_cast<double>(cov[covOffset(i, j)]);
      out(i, j) = v;
      out(j, i) = v;
    }
  return out;
}

}  // namespace

Helix Helix::fromPerigee(float d0, float z0, float theta, float phi,
                         float invR, const std::array<float, 15>* W) {
  Helix h;
  h.p_.D0    = -d0 * static_cast<float>(kCm2Mm);
  h.p_.phi   = phi;
  h.p_.omega = invR / static_cast<float>(kCm2Mm);
  h.p_.Z0    = z0 * static_cast<float>(kCm2Mm);
  h.p_.time  = 0.f;

  const float s = std::sin(theta);
  if (std::fabs(s) < 1e-6f) {           // degenerate
    h.p_.tanLambda = 0.f;
    h.valid_ = false;
    return h;
  }
  h.p_.tanLambda = std::cos(theta) / s;

  if (!W) return h;                      // params only, no cov

  // Build the 5×5 weight matrix (lower-tri, mirror), invert -> raw cov.
  TMatrixDSym Wm(5);
  {
    int k = 0;
    for (int i = 0; i < 5; ++i)
      for (int j = 0; j <= i; ++j) { Wm(i, j) = (*W)[k]; Wm(j, i) = (*W)[k]; ++k; }
  }
  double det = 0.0;
  TMatrixDSym C_dp(Wm);
  C_dp.Invert(&det);
  if (det == 0.0 || !std::isfinite(det)) {
    h.hasCov_ = true;                    // zero cov, but a valid track
    return h;
  }
  const TMatrixD J  = perigeeJacobian(theta);
  const TMatrixD JC (J, TMatrixD::kMult, C_dp);
  const TMatrixD Jt (TMatrixD::kTransposed, J);
  const TMatrixD Cf (JC, TMatrixD::kMult, Jt);
  for (int i = 0; i < 5; ++i)
    for (int j = 0; j <= i; ++j)
      h.cov_[covOffset(i, j)] =
        static_cast<float>(0.5 * (Cf(i, j) + Cf(j, i)));
  h.hasCov_ = true;
  return h;
}

Helix Helix::fromTrackElement(double c1, double c2, double c3,
                              double theta, double phi, double invP,
                              bool invPt,
                              const CovMatrix6& teCov,
                              int charge, double B) {
  Helix h;
  h.refPoint_ = { static_cast<float>(c1 * kCm2Mm),
                  static_cast<float>(c2 * kCm2Mm),
                  static_cast<float>(c3 * kCm2Mm) };
  h.p_.D0   = 0.f;
  h.p_.Z0   = 0.f;
  h.p_.time = 0.f;
  h.p_.phi  = static_cast<float>(phi);
  h.hasCov_ = true;

  const double s = std::sin(theta);
  if (std::fabs(s) < 1e-9) {
    h.p_.tanLambda = 0.f;
    h.p_.omega     = 0.f;
    h.valid_ = false;
    return h;                            // cov_ stays zero
  }
  h.p_.tanLambda = static_cast<float>(std::cos(theta) / s);
  // omega = transverse curvature kappa. If the bank word is 1/|p_T| (invPt),
  // omega = kOmega*q*B*invP directly; otherwise it is 1/|p| and omega =
  // kOmega*q*B*invP/sin(theta). (The earlier form multiplied by sin(theta),
  // giving kappa*sin^2(theta) -- inconsistent with the perigee path's
  // omega=invR/10=kappa and with momentum(), which treats omega=kappa.)
  h.p_.omega     = static_cast<float>(
      invPt ? kOmega * charge * B * invP
            : kOmega * charge * B * invP / s);

  // Cov push-forward C_helix = J · C_te · J^T.
  const TMatrixD    J  = teJacobian(theta, phi, invP, charge, B, invPt);
  const TMatrixDSym Ct = covFromArray(teCov);
  const TMatrixD    JC (J, TMatrixD::kMult, Ct);
  const TMatrixD    Jt (TMatrixD::kTransposed, J);
  const TMatrixD    Cf (JC, TMatrixD::kMult, Jt);
  for (int i = 0; i < 6; ++i)
    for (int j = 0; j <= i; ++j)
      h.cov_[covOffset(i, j)] =
        static_cast<float>(0.5 * (Cf(i, j) + Cf(j, i)));
  return h;
}

Helix Helix::fromHelix(float D0, float phi, float omega,
                       float Z0, float tanLambda) {
  Helix h;
  h.p_ = { D0, phi, omega, Z0, tanLambda, 0.f };
  return h;
}

Momentum Helix::momentum(double B, int charge) const {
  if (charge == 0 || std::fabs(B) < 1e-9 ||
      std::fabs(p_.omega) < 1e-15) {
    return Momentum{0.0, 0.0, 0.0, 0.0};
  }
  const double pT = kOmega * std::fabs(static_cast<double>(charge) * B)
                  / std::fabs(static_cast<double>(p_.omega));
  const double px = pT * std::cos(p_.phi);
  const double py = pT * std::sin(p_.phi);
  const double pz = pT * static_cast<double>(p_.tanLambda);
  return Momentum{px, py, pz, std::sqrt(px*px + py*py + pz*pz)};
}

edm4hep::TrackState Helix::toTrackState(int location) const {
  edm4hep::TrackState ts;
  ts.location       = location;
  ts.D0             = p_.D0;
  ts.phi            = p_.phi;
  ts.omega          = p_.omega;
  ts.Z0             = p_.Z0;
  ts.tanLambda      = p_.tanLambda;
  ts.time           = p_.time;
  ts.referencePoint = refPoint_;
  if (hasCov_) {
    using P = edm4hep::TrackParams;
    static constexpr P kP[6] = {
      P::d0, P::phi, P::omega, P::z0, P::tanLambda, P::time
    };
    for (int a = 0; a < 6; ++a)
      for (int b = 0; b <= a; ++b) {
        const float v = cov_[covOffset(a, b)];
        ts.covMatrix.setValue(v, kP[a], kP[b]);
        if (a != b) ts.covMatrix.setValue(v, kP[b], kP[a]);
      }
  }
  return ts;
}

}  // namespace delphi_edm4hep
