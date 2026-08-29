// VdHitsWriter — pass-1 implementation.
//
// PSCVDU: NVDUN unassociated hits, KVDUN/QVDUN(i, n), i=1..5.
// PSCVDA: per track j (1..MTRACK) NASHT(j) hits, KVDAS/QVDAS(i, j, n).
// Field i: 1=module#(sign of Z), 2=localX/Z, 3=R(−R if R-Z), 4=RPhi/Z,
// 5=signal/noise. Position kept cylindrical-mixed (R, slot2, slot4)×10mm.

#include "delphi_edm4hep/Tracking/VdHits.h"

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
  podio::UserDataCollection<std::int32_t> trkIdxCol;

  // ---- Unassociated (PSCVDU) ----
  for (int n = 1; n <= sk::NVDUN; ++n) {
    fillHit(pointsCol.create(),
            sk::KVDUN(sk::IVDUMOD, n), sk::QVDUN(sk::IVDUXLC, n),
            sk::QVDUN(sk::IVDURCO, n), sk::QVDUN(sk::IVDURPH, n),
            sk::QVDUN(sk::IVDUSTN, n));
  }

  // ---- Associated (PSCVDA), per track j ----
  // Map the SKELANA track ordinal j -> sDST_MAIN_Particles index via the
  // tracking VECP->particle table (charged tracks share that ordinal).
  const auto* vecp_to_particle =
    ctx_.tracking ? &ctx_.tracking->vecp_to_particle : nullptr;
  // PSCVDA is per CHARGED track; bound j to the charged-track count (NCVECP),
  // not the MTRACK array maximum -- stale NASHT slots past the populated tracks
  // would otherwise emit fake hits (TrackIndex=-1). j is the charged VECP
  // ordinal (vecp_to_particle below maps it). Inner loop already clamps to NHIT.
  for (int j = 1; j <= sk::NCVECP && j <= skelana::MTRACK; ++j) {
    const int nhit = sk::NASHT(j);
    if (nhit <= 0) continue;
    int p_idx = -1;
    if (vecp_to_particle && j < static_cast<int>(vecp_to_particle->size()))
      p_idx = (*vecp_to_particle)[j];
    for (int n = 1; n <= nhit && n <= sk::NHIT; ++n) {
      fillHit(hitsCol.create(),
              sk::KVDAS(sk::IVDAMOD, j, n), sk::QVDAS(sk::IVDAXLC, j, n),
              sk::QVDAS(sk::IVDARCO, j, n), sk::QVDAS(sk::IVDARPH, j, n),
              sk::QVDAS(sk::IVDASTN, j, n));
      trkIdxCol.push_back(p_idx);
    }
  }

  put(std::move(pointsCol), "TDVD", "VDPoints", Provenance::Transcribed);
  put(std::move(hitsCol),   "TDVD", "VDHits", Provenance::Transcribed);
  put(std::move(trkIdxCol), "TDVD", "VDHits_TrackIndex", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::vd_hits
