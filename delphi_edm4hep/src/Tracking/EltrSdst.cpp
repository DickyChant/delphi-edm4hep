// EltrSdstWriter — pass-1 implementation.
//
// PA.ELTR (label 28) layout mirrors PA.TRAC:
//   +2 d0 (cm)  +3 z0 (cm)  +4 theta (rad)  +5 phi (rad)  +6 1/R (1/cm)
//   +7..+21  15-element lower-tri weight matrix
// converted to an EDM4hep helix AtIP TrackState via the shared
// delphi_edm4hep::perigee helpers.

#include "delphi_edm4hep/Tracking/EltrSdst.h"

#include "delphi_edm4hep/Helix.h"
#include "delphi_edm4hep/internal/PaWalk.h"

#include <edm4hep/TrackCollection.h>
#include <edm4hep/TrackState.h>
#include <podio/UserDataCollection.h>

#include <array>
#include <cstdint>

namespace ph = phdst;

namespace delphi_edm4hep::eltr_sdst {

void EltrSdstWriter::emit()
{
  edm4hep::TrackCollection             trkCol;
  podio::UserDataCollection<std::int32_t> idxCol;

  if (!ctx_.tracking) {
    put(std::move(trkCol), "ELTR", "RefitTracks", Provenance::Transcribed);
    put(std::move(idxCol), "ELTR", "ParticleIndex", Provenance::Transcribed);
    return;
  }
  const auto& tracking = *ctx_.tracking;

  pawalk::forEachPA([&](int lpa, int paIdx) {
    const int leltr = pawalk::lphpa("ELTR", lpa);
    if (leltr <= 0) return;

    const float d0    = ph::Q(leltr + 2);
    const float z0    = ph::Q(leltr + 3);
    const float theta = ph::Q(leltr + 4);
    const float phi   = ph::Q(leltr + 5);
    const float invR  = ph::Q(leltr + 6);
    std::array<float, 15> Wraw{};
    for (int k = 0; k < 15; ++k) Wraw[k] = ph::Q(leltr + 7 + k);

    const auto helix = Helix::fromPerigee(d0, z0, theta, phi, invR, &Wraw);
    if (!helix.valid()) return;   // degenerate sin(theta)

    auto trk = trkCol.create();
    trk.addToTrackStates(helix.toTrackState(edm4hep::TrackState::AtIP));

    const int p_idx =
      (paIdx >= 0 && paIdx < static_cast<int>(tracking.pa_to_particle.size()))
        ? tracking.pa_to_particle[paIdx] : -1;
    idxCol.push_back(p_idx);
  });

  put(std::move(trkCol), "ELTR", "RefitTracks", Provenance::Transcribed);
  put(std::move(idxCol), "ELTR", "ParticleIndex", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::eltr_sdst
