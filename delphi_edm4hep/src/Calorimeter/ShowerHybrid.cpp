// ShowerHybridWriter — pass-2 implementation.

#include "delphi_edm4hep/Calorimeter/ShowerHybrid.h"

#include <edm4hep/ClusterCollection.h>
#include <edm4hep/MutableCluster.h>

#include <cstddef>
#include <string>

namespace delphi_edm4hep::shower_hybrid {

namespace {

void cloneShowers(const edm4hep::ClusterCollection& src,
                  edm4hep::ClusterCollection&       dst)
{
  for (const auto& sc : src) {
    auto dc = dst.create();
    dc.setType          (sc.getType());
    dc.setEnergy        (sc.getEnergy());
    dc.setEnergyError   (sc.getEnergyError());
    dc.setPosition      (sc.getPosition());
    dc.setPositionError (sc.getPositionError());
    dc.setITheta        (sc.getITheta());
    dc.setIPhi          (sc.getIPhi());
    dc.setDirectionError(sc.getDirectionError());
    for (std::size_t k = 0; k < sc.subdetectorEnergies_size(); ++k) {
      dc.addToSubdetectorEnergies(sc.getSubdetectorEnergies(k));
    }
    for (std::size_t k = 0; k < sc.shapeParameters_size(); ++k) {
      dc.addToShapeParameters(sc.getShapeParameters(k));
    }
  }
}

}  // namespace

void ShowerHybridWriter::emit()
{
  edm4hep::ClusterCollection emnc_out, hcnc_out, hcal_out;
  cloneShowers(frame_.get<edm4hep::ClusterCollection>("sDST_EMNC_Showers"), emnc_out);
  cloneShowers(frame_.get<edm4hep::ClusterCollection>("sDST_HCNC_Showers"), hcnc_out);
  cloneShowers(frame_.get<edm4hep::ClusterCollection>("sDST_HCAL_Showers"), hcal_out);
  put(std::move(emnc_out), "EMNC", "Showers", Provenance::Transcribed);
  put(std::move(hcnc_out), "HCNC", "Showers", Provenance::Transcribed);
  put(std::move(hcal_out), "HCAL", "Showers", Provenance::Transcribed);
}

}  // namespace delphi_edm4hep::shower_hybrid
