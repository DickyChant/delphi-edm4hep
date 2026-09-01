// VdHitsWriter — pass-1 implementation.
//
// PSCVDU: NVDUN unassociated hits, KVDUN/QVDUN(i, n), i=1..5.
// PSCVDA: per track j (1..MTRACK) NASHT(j) hits, KVDAS/QVDAS(i, j, n).
// Field i: 1=module#(sign of Z), 2=localX/Z, 3=R(−R if R-Z), 4=RPhi/Z,
// 5=signal/noise. Position kept cylindrical-mixed (R, slot2, slot4)×10mm.

#include "delphi_edm4hep/Tracking/VdHits.h"

#include <algorithm>

#include "skelana/pscvda.hpp"
#include "skelana/pscvdu.hpp"
#include "skelana/pscvec.hpp"   // NCVECP (charged-track count)

#include <edm4hep/MutableTrackerHit3D.h>
#include <edm4hep/TrackerHit3DCollection.h>
#include <podio/UserDataCollection.h>

#include <cstdint>

namespace sk = skelana;

namespace delphi_edm4hep::vd_hits {

namespace {
constexpr double kCm2Mm = 10.0;

// Fill a TrackerHit3D from the 5 VD-hit fields (module#, slot2, R, slot4,
// S/N). Position is the cylindrical-mixed (R, slot2, slot4) triple ×10mm.
void fillHit(edm4hep::MutableTrackerHit3D hit,
             int module_signed, float slot2, float R, float slot4, float sn) {
  hit.setCellID(static_cast<std::uint64_t>(
                  static_cast<std::int64_t>(module_signed)));
  hit.setType(R < 0.f ? 1 : 0);          // R-Z measurement flag
  hit.setEDep(sn);                        // signal/noise (no dedicated slot)
  hit.setPosition({ R * kCm2Mm, slot2 * kCm2Mm, slot4 * kCm2Mm });
}
}  // namespace

void VdHitsWriter::emit()
{
  edm4hep::TrackerHit3DCollection pointsCol;   // PSCVDU, unassociated
  edm4hep::TrackerHit3DCollection hitsCol;     // PSCVDA, associated
  Output out;

  // ---- Unassociated (PSCVDU) ----
  for (int n = 1; n <= sk::NVDUN; ++n) {
    fillHit(pointsCol.create(),
            sk::KVDUN(sk::IVDUMOD, n), sk::QVDUN(sk::IVDUXLC, n),
            sk::QVDUN(sk::IVDURCO, n), sk::QVDUN(sk::IVDURPH, n),
            sk::QVDUN(sk::IVDUSTN, n));
  }

  // ---- Associated (PSCVDA), per charged track j ----
  // Hits are grouped by the SKELANA charged-track ordinal and handed to
  // TrackingWriter, which links them onto the track built from the same
  // ordinal. Keying by the ordinal rather than by an emitted-particle index
  // is what lets this run BEFORE the track writer: a track is only mutable
  // while its own writer holds it.
  //
  // PSCVDA is per CHARGED track; bound j to the charged-track count (NCVECP),
  // not the MTRACK array maximum -- stale NASHT slots past the populated
  // tracks would otherwise emit hits belonging to nothing. The inner loop
  // clamps to NHIT.
  const int ntrk = std::min(sk::NCVECP, static_cast<int>(skelana::MTRACK));
  out.vecp_to_hits.assign(static_cast<std::size_t>(std::max(0, ntrk) + 1), {});
  for (int j = 1; j <= ntrk; ++j) {
    const int nhit = sk::NASHT(j);
    if (nhit <= 0) continue;
    for (int n = 1; n <= nhit && n <= sk::NHIT; ++n) {
      auto hit = hitsCol.create();
      fillHit(hit,
              sk::KVDAS(sk::IVDAMOD, j, n), sk::QVDAS(sk::IVDAXLC, j, n),
              sk::QVDAS(sk::IVDARCO, j, n), sk::QVDAS(sk::IVDARPH, j, n),
              sk::QVDAS(sk::IVDASTN, j, n));
      out.vecp_to_hits[static_cast<std::size_t>(j)].push_back(hit);
    }
  }

  put(std::move(pointsCol), "TDVD", "VDPoints", Provenance::Transcribed);
  put(std::move(hitsCol),   "TDVD", "VDHits", Provenance::Transcribed);
  ctx_.vd_hits = std::move(out);
}

}  // namespace delphi_edm4hep::vd_hits
