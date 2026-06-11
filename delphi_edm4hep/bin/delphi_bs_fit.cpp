// delphi_bs_fit — per-run beamspot from aggregated primary vertices.
//
// Reproduces the per-run PV-aggregated beamspot recipe on edm4hep output.
// The official DELPHI beamspot bank (sDST_BSP_BeamSpot / PSCBSP) closes
// poorly in data-vs-MC; re-deriving the beamspot CENTRE from each sample's
// own per-event primary-vertex distribution is self-consistent within a
// sample and closes better. This is a CUSTOM OP (no DELPHI-bank value) and
// a per-RUN aggregation, so it lives as a downstream tool over the
// converter output rather than in the per-event converter — it never
// replaces sDST_BSP_BeamSpot.
//
// Recipe (bs_fit.cpp + docs/aleph-lep1-btag-summary.md §2):
//   centre = robust (Tukey biweight) mean of per-event PV positions, per
//            run; uncertainty sigma_centre = robust_sigma / sqrt(N).
//   width  = the physical beam pancake (kept from the bank's per-event
//            BeamSpotSigma*, averaged per run) — NOT re-derived.
//   sigma  = sqrt(sigma_beam^2 + sigma_centre^2).
//
// Inputs are read in EDM4hep units (mm); the CSV is written in mm.
// Run the tool once per sample (data and MC separately).
//
// Usage: delphi_bs_fit <input.edm4hep.root> <out_bs.csv>
//   reads sDST_PV_PrimaryVertex, sDST_EVT_runNumber,
//         sDST_EVT_BeamSpotSigma{X,Y,Z}

#include <podio/Frame.h>
#include <podio/ROOTReader.h>

#include <edm4hep/VertexCollection.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <utility>
#include <vector>

namespace {

// Tukey biweight robust mean (5-iteration M-estimator). Returns
// (mean, sigma_of_mean). Transplanted verbatim from reco/vertex/bs_fit.cpp.
std::pair<double, double> robustMean(std::vector<double> v) {
  if (v.empty()) return {0.0, 0.0};
  std::sort(v.begin(), v.end());
  const double med = v[v.size() / 2];
  std::vector<double> ad;
  ad.reserve(v.size());
  for (double x : v) ad.push_back(std::fabs(x - med));
  std::sort(ad.begin(), ad.end());
  const double mad   = ad[ad.size() / 2];
  const double scale = std::max(1.4826 * mad, 1e-9);   // robust sigma
  double mu = med;
  for (int it = 0; it < 5; ++it) {
    double sumW = 0, sumWX = 0;
    const double c = 6.0 * scale;                       // Tukey constant
    for (double x : v) {
      const double r = (x - mu) / c;
      if (std::fabs(r) >= 1.0) continue;
      const double w = (1.0 - r * r) * (1.0 - r * r);
      sumW  += w;
      sumWX += w * x;
    }
    if (sumW <= 0) break;
    const double newMu = sumWX / sumW;
    if (std::fabs(newMu - mu) < 1e-9) { mu = newMu; break; }
    mu = newMu;
  }
  double sumW = 0, sumWX2 = 0;
  const double c = 6.0 * scale;
  for (double x : v) {
    const double r = (x - mu) / c;
    if (std::fabs(r) >= 1.0) continue;
    const double w = (1.0 - r * r) * (1.0 - r * r);
    sumW   += w;
    sumWX2 += w * (x - mu) * (x - mu);
  }
  const double s = (sumW > 0) ? std::sqrt(sumWX2 / sumW) : scale;
  return {mu, s / std::sqrt(std::max(1.0, sumW))};
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "Usage: " << argv[0]
              << " <input.edm4hep.root> <out_bs.csv>\n"
              << "  per-run beamspot from aggregated sDST_PV_PrimaryVertex (mm)\n";
    return 1;
  }

  podio::ROOTReader reader;
  reader.openFile(argv[1]);
  const unsigned N = reader.getEntries("events");

  std::map<int, std::vector<double>> runX, runY, runZ;
  std::map<int, std::array<double, 4>> beamSum;   // sumSx, sumSy, sumSz, n

  for (unsigned i = 0; i < N; ++i) {
    auto fd = reader.readEntry("events", i);
    if (!fd) break;
    const podio::Frame f(std::move(fd));

    const auto run = f.getParameter<int>("sDST_EVT_runNumber");
    if (!run) continue;

    const auto& pv = f.get<edm4hep::VertexCollection>("sDST_PV_PrimaryVertex");
    if (pv.size() == 0 || pv[0].getNdf() <= 0) continue;   // no real PV
    const auto p = pv[0].getPosition();
    runX[*run].push_back(p.x);
    runY[*run].push_back(p.y);
    runZ[*run].push_back(p.z);

    auto& b = beamSum[*run];
    b[0] += f.getParameter<float>("sDST_EVT_BeamSpotSigmaX").value_or(0.f);
    b[1] += f.getParameter<float>("sDST_EVT_BeamSpotSigmaY").value_or(0.f);
    b[2] += f.getParameter<float>("sDST_EVT_BeamSpotSigmaZ").value_or(0.f);
    b[3] += 1.0;
  }

  std::ofstream out(argv[2]);
  out << "# run_number  bs_x  bs_y  bs_z  sigma_x  sigma_y  sigma_z   (mm)\n"
      << "#   centre = Tukey-biweight robust mean of per-event PVs;\n"
      << "#   sigma  = sqrt(beam_width_avg^2 + centre_uncertainty^2)\n";
  for (auto& [run, xs] : runX) {
    const auto [muX, eX] = robustMean(xs);
    const auto [muY, eY] = robustMean(runY[run]);
    const auto [muZ, eZ] = robustMean(runZ[run]);
    const auto& b = beamSum[run];
    const double n = std::max(b[3], 1.0);
    const double sBx = b[0] / n, sBy = b[1] / n, sBz = b[2] / n;
    const double effX = std::sqrt(sBx * sBx + eX * eX);
    const double effY = std::sqrt(sBy * sBy + eY * eY);
    const double effZ = std::sqrt(sBz * sBz + eZ * eZ);
    out << run << "  " << muX << "  " << muY << "  " << muZ
        << "  " << effX << "  " << effY << "  " << effZ
        << "    # n=" << xs.size() << "\n";
    std::cout << "run " << run << " : N=" << xs.size()
              << "  centre=(" << muX << ", " << muY << ", " << muZ << ") mm"
              << "  sigma_centre=(" << eX << ", " << eY << ", " << eZ << ") mm\n";
  }
  std::cout << "Wrote " << argv[2] << "\n";
  return 0;
}
