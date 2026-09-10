#pragma once

#include "delphi_edm4hep/Geometry/CargoDatabase.h"

#include <array>
#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace delphi_edm4hep::geometry {

enum class DelphiShapeKind {
  Dummy,
  FourSidedBox,
  Polygon4,
  Polygon6,
  Cylinder0,
  Cylinder1,
  Cylinder2,
  Cylinder3,
  Sphere,
  Paraboloid,
  Wedge4,
  Brick,
  PlanePolyhedron,
};

std::string_view shapeKindName(DelphiShapeKind kind);

struct MaterialDefinition {
  std::string name;
  std::array<double, 6> parameters{};
  std::size_t sourceLine{};
};

struct MaterialAssignment {
  std::string inner;
  std::string outer;
  std::size_t sourceLine{};
};

struct ShapeDefinition {
  std::string field;
  std::string tag;
  DelphiShapeKind kind{};
  std::vector<double> parameters;
  std::size_t sourceLine{};
};

struct ReferenceTransform {
  std::string field;
  std::array<double, 3> translationCm{};
  std::array<double, 3> rotationDegrees{};
  std::size_t sourceLine{};
};

struct GeometryNode {
  std::string path;
  std::string name;
  std::vector<MaterialAssignment> materials;
  std::vector<ShapeDefinition> shapes;
  std::vector<ReferenceTransform> references;
  std::vector<std::vector<std::string>> replacements;
  std::size_t sourceLine{};
};

class GeometryModel {
public:
  static GeometryModel fromCargo(const CargoDatabase &database,
                                 std::string sourceName = "<CARGO>");

  const std::vector<MaterialDefinition> &materials() const {
    return materials_;
  }
  const std::vector<GeometryNode> &nodes() const { return nodes_; }

private:
  std::vector<MaterialDefinition> materials_;
  std::vector<GeometryNode> nodes_;
};

} // namespace delphi_edm4hep::geometry
