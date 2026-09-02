// VftHitsWriter — pass-1 implementation.
//
// PXTD layout (production DESCRIP, bank 42):
//   word 1              number of clusters
//   per cluster, 11 words then one word per pixel:
//     1  module (crown + 1000 * raquette)
//     2..4  x, y, z in the DELPHI frame, times 10000
//     5,6   x, z in the module frame, times 10000
//     7,8   errors on those two, times 10000
//     9     TANAGRA identifier of the TK or TE
//     10    pixels in the cluster + 100 * truth label
//     11    TANAGRA identifier of the TDR
// Stored lengths are in cm.

#include "delphi_edm4hep/Tracking/VftHits.h"

#include "phdst/uxcom.hpp"
#include "phdst/uxlink.hpp"

#include <edm4hep/TrackerHitPlaneCollection.h>
#include <podio/UserDataCollection.h>

#include <cstdint>
#include <limits>

namespace ph = phdst;

namespace delphi_edm4hep::vft_hits {

namespace {
constexpr int    kPxtdLink   = 42;      // LQ(LDTOP-42)
constexpr int    kWordsPerHit = 11;
constexpr double kScale      = 10000.0; // stored coordinates are scaled
constexpr double kCm2Mm      = 10.0;
constexpr float  kNotMeasured = std::numeric_limits<float>::quiet_NaN();

double coord(int address) { return ph::IQ(address) / kScale * kCm2Mm; }
}  // namespace

void VftHitsWriter::emit()
{
  edm4hep::TrackerHitPlaneCollection      hits;
  podio::UserDataCollection<std::int32_t> cluster_size;
  podio::UserDataCollection<std::int32_t> tanagra_id;

  const int ldtop = ph::LDTOP;
  // The bank is reachable only when the DTOP link area is long enough to
  // hold its slot; older files stop short of it.
  if (ldtop > 0 && ph::IQ(ldtop - 3) >= kPxtdLink) {
    if (const int l = ph::LQ(ldtop - kPxtdLink); l > 0) {
      const int blen = ph::IQ(l - 1);
      const int nhit = ph::IQ(l + 1);
      int w = 2;
      for (int i = 0; i < nhit; ++i) {
        if (w + kWordsPerHit - 1 > blen) break;
        const int npix = ph::IQ(l + w + 9) % 100;

        auto hit = hits.create();
        hit.setCellID(static_cast<std::uint64_t>(ph::IQ(l + w)));
        hit.setPosition({coord(l + w + 1), coord(l + w + 2), coord(l + w + 3)});
        hit.setDu(static_cast<float>(coord(l + w + 6)));
        hit.setDv(static_cast<float>(coord(l + w + 7)));
        hit.setU({kNotMeasured, kNotMeasured});
        hit.setV({kNotMeasured, kNotMeasured});

        cluster_size.push_back(npix);
        tanagra_id.push_back(ph::IQ(l + w + 8));

        w += kWordsPerHit + npix;
      }
    }
  }

  // Emitted whether or not the file carries the bank, so the collection set
  // does not vary between samples.
  put(std::move(hits),         "PXTD", "PixelHits",             Provenance::Transcribed);
  put(std::move(cluster_size), "PXTD", "PixelHits_ClusterSize", Provenance::Transcribed);
  put(std::move(tanagra_id),   "PXTD", "PixelHits_TanagraId",   Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::vft_hits
