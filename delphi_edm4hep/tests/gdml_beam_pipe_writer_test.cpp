#include "delphi_edm4hep/Geometry/CargoDatabase.h"
#include "delphi_edm4hep/Geometry/GdmlBeamPipeWriter.h"
#include "delphi_edm4hep/Geometry/GeometryModel.h"

#include <sstream>
#include <stdexcept>
#include <string>

namespace {

void require(bool condition, const std::string &message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

} // namespace

int main() {
  std::istringstream input(R"(*MATC /AIR*.B
880101,0,940621,190801
*MATF  6,1,.129E-02,7.2,14.4,30050,0
**
*MATC /BPAV.B
880101,0,940621,190801
*MATF  6,1,.01,7,14,100,200
**
*MATC /VACU.B
880101,0,940621,190801
*MATF  6,0,0,1,1,0,0
**
*MATC /TUN*.B
880101,0,940621,190801
*MATF  6,1,19.3,74,183.84,.35,10
**
*GEOM /DELF.B
890101,0,931220,214701
*MATS  2,AIR*,AIR*
*SHAP  7,CYL1,0,360,0,680,-585,585
**
*GEOM /BEA*.B
890101,0,931220,214701
*MATS  2,BPAV,AIR*
*SHA1  7,CYL1,0,360,0,8,-20,-10
*SHAP  7,CYL1,0,360,0,8,-10,20
**
*GEOM /BEA*/PIPE.B
890101,0,931220,214701
*MATS  2,VACU,VACU
*SHAP  9,CYL3,0,360,-10,10,0,4,0,5
**
*GEOM /BEA*/VPIC.B
890101,0,931220,214701
*MATS  2,VACU,VACU
*SHAP  7,CYL1,0,360,0,6,-30,30
**
*GEOM /BEA*/VPIC/MSK1.B
890101,0,931220,214701
*MATS  2,VACU,VACU
*REFR  6,0,0,-21,180,180,90
*REPL  1,MSK2
**
*GEOM /BEA*/VPIC/MSK2.B
890101,0,931220,214701
*MATS  2,VACU,VACU
*REFR  6,0,0,21,0,0,0
*SHAP  7,CYL1,0,360,4,5,0,10
**
*GEOM /BEA*/VPIC/MSK2/INC1.B
890101,0,931220,214701
*MATS  2,TUN*,TUN*
*SHAP  4,BRIK,.14,.16,5
**
)");
  const auto database =
      delphi_edm4hep::geometry::CargoDatabase::read(input, "fixture");
  const auto model =
      delphi_edm4hep::geometry::GeometryModel::fromCargo(database, "fixture");
  std::ostringstream output;
  delphi_edm4hep::geometry::writeGdmlBeamPipe(output, model, "/DELF.B",
                                              "/BEA*.B", "v94c<&\"");
  const auto gdml = output.str();
  require(gdml.find("delphi_node__BEA__union_1") != std::string::npos,
          "multiple beam-pipe shapes were not combined");
  require(gdml.find("delphi_node__BEA__VPIC_MSK1_INC1") != std::string::npos,
          "replacement children were not instantiated");
  require(gdml.find("<box name=\"delphi_node__BEA__VPIC_MSK1_INC1") !=
              std::string::npos,
          "inherited brick was not rendered");
  require(gdml.find("value=\"1e-25\"") != std::string::npos,
          "DELPHI vacuum sentinel was not mapped for transport");
  require(gdml.find("x=\"-180\"") != std::string::npos &&
              gdml.find("z=\"-90\"") != std::string::npos,
          "DXMATR rotation was not converted to GDML Euler angles");
  require(gdml.find("v94c&lt;&amp;&quot;") != std::string::npos,
          "snapshot identifier was not XML escaped");
}
