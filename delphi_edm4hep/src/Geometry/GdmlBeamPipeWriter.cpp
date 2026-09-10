#include "delphi_edm4hep/Geometry/GdmlBeamPipeWriter.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <iomanip>
#include <ostream>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace delphi_edm4hep::geometry {
namespace {

constexpr double pi = 3.14159265358979323846;

struct RenderNode {
  const GeometryNode *record{};
  const GeometryNode *definition{};
  std::string instancePath;
  std::vector<std::size_t> children;
};

struct EulerRotation {
  double x{};
  double y{};
  double z{};
};

std::string xmlEscape(std::string_view value) {
  std::string escaped;
  for (const auto character : value) {
    switch (character) {
    case '&':
      escaped += "&amp;";
      break;
    case '<':
      escaped += "&lt;";
      break;
    case '>':
      escaped += "&gt;";
      break;
    case '\"':
      escaped += "&quot;";
      break;
    case '\'':
      escaped += "&apos;";
      break;
    default:
      escaped.push_back(character);
      break;
    }
  }
  return escaped;
}

std::string gdmlName(std::string_view value) {
  std::string result;
  result.reserve(value.size());
  for (const auto character : value) {
    const auto valid = (character >= 'a' && character <= 'z') ||
                       (character >= 'A' && character <= 'Z') ||
                       (character >= '0' && character <= '9') ||
                       character == '_';
    result.push_back(valid ? character : '_');
  }
  if (result.empty() || (result.front() >= '0' && result.front() <= '9')) {
    result.insert(result.begin(), '_');
  }
  return result;
}

double radians(double degrees) { return degrees * pi / 180.0; }
double degrees(double radiansValue) { return radiansValue * 180.0 / pi; }

std::array<double, 9>
delphiRotationMatrix(const std::array<double, 3> &angles) {
  const auto phi = radians(angles[0]);
  const auto theta = radians(angles[1]);
  const auto psi = radians(angles[2]);
  const auto cphi = std::cos(phi);
  const auto sphi = std::sin(phi);
  const auto ctheta = std::cos(theta);
  const auto stheta = std::sin(theta);
  const auto cpsi = std::cos(psi);
  const auto spsi = std::sin(psi);
  return {
      cpsi * cphi - spsi * ctheta * sphi,
      -spsi * cphi - cpsi * ctheta * sphi,
      stheta * sphi,
      cpsi * sphi + spsi * ctheta * cphi,
      -spsi * sphi + cpsi * ctheta * cphi,
      -stheta * cphi,
      spsi * stheta,
      cpsi * stheta,
      ctheta,
  };
}

EulerRotation gdmlRotation(const std::array<double, 3> &angles) {
  // DXMATR's DELPHI Euler convention is converted to the x-y-z convention
  // used by GDML placements by first constructing the authoritative matrix.
  const auto matrix = delphiRotationMatrix(angles);
  const auto sineY = std::clamp(matrix[2], -1.0, 1.0);
  const auto y = std::asin(sineY);
  const auto cosineY = std::cos(y);
  double x{};
  double z{};
  if (std::abs(cosineY) > 1.0e-12) {
    x = std::atan2(-matrix[5], matrix[8]);
    z = std::atan2(-matrix[1], matrix[0]);
  } else {
    x = std::atan2(sineY * matrix[3], matrix[4]);
  }
  return {degrees(x), degrees(y), degrees(z)};
}

std::string nodeId(const RenderNode &node) {
  return "delphi_node_" + gdmlName(node.instancePath);
}

std::string shapeId(const RenderNode &node, std::size_t index) {
  return nodeId(node) + "_shape_" + std::to_string(index);
}

std::string solidId(const RenderNode &node) {
  if (node.definition->shapes.size() == 1) {
    return shapeId(node, 0);
  }
  return nodeId(node) + "_union_" +
         std::to_string(node.definition->shapes.size() - 1);
}

const MaterialAssignment &effectiveMaterial(const RenderNode &node) {
  if (!node.record->materials.empty()) {
    return node.record->materials.front();
  }
  if (!node.definition->materials.empty()) {
    return node.definition->materials.front();
  }
  throw std::runtime_error("DELPHI beam-pipe node has no material: " +
                           node.instancePath);
}

const std::vector<ReferenceTransform> &
effectiveReferences(const RenderNode &node) {
  if (!node.record->references.empty()) {
    return node.record->references;
  }
  return node.definition->references;
}

void writePlacement(std::ostream &output, const std::string &physicalName,
                    const std::string &volumeName,
                    const ReferenceTransform *reference) {
  output << "      <physvol name=\"" << physicalName << "\">\n"
         << "        <volumeref ref=\"" << volumeName << "\"/>\n";
  if (reference != nullptr) {
    const auto rotation = gdmlRotation(reference->rotationDegrees);
    output << "        <position name=\"" << physicalName << "_position\" x=\""
           << reference->translationCm[0] << "\" y=\""
           << reference->translationCm[1] << "\" z=\""
           << reference->translationCm[2] << "\" unit=\"cm\"/>\n"
           << "        <rotation name=\"" << physicalName << "_rotation\" x=\""
           << rotation.x << "\" y=\"" << rotation.y << "\" z=\"" << rotation.z
           << "\" unit=\"deg\"/>\n";
  }
  output << "      </physvol>\n";
}

void validateRadii(double minimum, double maximum, const RenderNode &node) {
  if (minimum < 0 || maximum <= minimum) {
    throw std::runtime_error("invalid DELPHI beam-pipe radii at " +
                             node.instancePath);
  }
}

void writeShape(std::ostream &output, const RenderNode &node,
                const ShapeDefinition &shape, std::size_t index) {
  const auto &parameters = shape.parameters;
  const auto name = shapeId(node, index);
  switch (shape.kind) {
  case DelphiShapeKind::Cylinder1:
    if (parameters.size() != 6 || parameters[1] <= parameters[0] ||
        parameters[5] <= parameters[4]) {
      throw std::runtime_error("invalid DELPHI beam-pipe CYL1 at " +
                               node.instancePath);
    }
    validateRadii(parameters[2], parameters[3], node);
    output << "    <polycone name=\"" << name << "\" startphi=\""
           << parameters[0] << "\" deltaphi=\"" << parameters[1] - parameters[0]
           << "\" aunit=\"deg\" lunit=\"cm\">\n"
           << "      <zplane rmin=\"" << parameters[2] << "\" rmax=\""
           << parameters[3] << "\" z=\"" << parameters[4] << "\"/>\n"
           << "      <zplane rmin=\"" << parameters[2] << "\" rmax=\""
           << parameters[3] << "\" z=\"" << parameters[5] << "\"/>\n"
           << "    </polycone>\n";
    return;
  case DelphiShapeKind::Cylinder3:
    if (parameters.size() != 8 || parameters[1] <= parameters[0] ||
        parameters[3] <= parameters[2]) {
      throw std::runtime_error("invalid DELPHI beam-pipe CYL3 at " +
                               node.instancePath);
    }
    validateRadii(parameters[4], parameters[5], node);
    validateRadii(parameters[6], parameters[7], node);
    output << "    <polycone name=\"" << name << "\" startphi=\""
           << parameters[0] << "\" deltaphi=\"" << parameters[1] - parameters[0]
           << "\" aunit=\"deg\" lunit=\"cm\">\n"
           << "      <zplane rmin=\"" << parameters[4] << "\" rmax=\""
           << parameters[5] << "\" z=\"" << parameters[2] << "\"/>\n"
           << "      <zplane rmin=\"" << parameters[6] << "\" rmax=\""
           << parameters[7] << "\" z=\"" << parameters[3] << "\"/>\n"
           << "    </polycone>\n";
    return;
  case DelphiShapeKind::Brick:
    if (parameters.size() != 3 || parameters[0] <= 0 || parameters[1] <= 0 ||
        parameters[2] <= 0) {
      throw std::runtime_error("invalid DELPHI beam-pipe BRIK at " +
                               node.instancePath);
    }
    output << "    <box name=\"" << name << "\" x=\"" << parameters[0]
           << "\" y=\"" << parameters[1] << "\" z=\"" << parameters[2]
           << "\" lunit=\"cm\"/>\n";
    return;
  default:
    throw std::runtime_error("unsupported DELPHI beam-pipe shape " +
                             std::string(shapeKindName(shape.kind)) + " at " +
                             node.instancePath);
  }
}

std::vector<RenderNode> buildRenderTree(const GeometryModel &model,
                                        const GeometryNode &root) {
  std::vector<RenderNode> nodes;
  std::unordered_set<std::string> active;
  std::function<std::size_t(const GeometryNode &, std::string)> append =
      [&](const GeometryNode &record, std::string instancePath) {
        if (!active.insert(record.path).second) {
          throw std::runtime_error("DELPHI beam-pipe hierarchy cycle at " +
                                   record.path);
        }
        const auto *definition = model.shapeDefinition(record);
        if (definition->shapes.empty()) {
          throw std::runtime_error("DELPHI beam-pipe node has no shape: " +
                                   record.path);
        }
        const auto index = nodes.size();
        nodes.push_back({&record, definition, std::move(instancePath), {}});

        auto children = model.childrenOf(record.path);
        if (children.empty()) {
          if (const auto *replacement = model.replacementTarget(record)) {
            children = model.childrenOf(replacement->path);
          }
        }
        for (const auto *child : children) {
          const auto childIndex =
              append(*child, nodes[index].instancePath + '/' + child->name);
          nodes[index].children.push_back(childIndex);
        }
        active.erase(record.path);
        return index;
      };
  append(root, root.path.substr(0, root.path.size() - 2));
  return nodes;
}

} // namespace

void writeGdmlBeamPipe(std::ostream &output, const GeometryModel &model,
                       std::string_view worldPath,
                       std::string_view beamPipePath,
                       std::string_view snapshotIdentifier) {
  const auto *world = model.findNode(worldPath);
  const auto *beamPipe = model.findNode(beamPipePath);
  if (world == nullptr) {
    throw std::runtime_error("DELPHI GDML world node not found: " +
                             std::string(worldPath));
  }
  if (beamPipe == nullptr) {
    throw std::runtime_error("DELPHI GDML beam-pipe node not found: " +
                             std::string(beamPipePath));
  }
  const auto worldShape = std::find_if(
      world->shapes.begin(), world->shapes.end(),
      [](const auto &candidate) { return candidate.field == "SHAP"; });
  if (worldShape == world->shapes.end() ||
      worldShape->kind != DelphiShapeKind::Cylinder1 ||
      worldShape->parameters.size() != 6 || world->materials.empty()) {
    throw std::runtime_error("DELPHI GDML world definition is invalid");
  }
  const auto &worldParameters = worldShape->parameters;
  if (worldParameters[1] <= worldParameters[0] || worldParameters[2] < 0 ||
      worldParameters[3] <= worldParameters[2] ||
      worldParameters[5] <= worldParameters[4] ||
      std::abs(worldParameters[4] + worldParameters[5]) > 1.0e-9) {
    throw std::runtime_error("DELPHI GDML world bounds are invalid");
  }

  auto nodes = buildRenderTree(model, *beamPipe);
  std::set<std::string> materialNames{world->materials.front().inner};
  for (const auto &node : nodes) {
    materialNames.insert(effectiveMaterial(node).inner);
  }

  output << std::setprecision(17)
         << "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
         << "<gdml xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" "
            "xsi:noNamespaceSchemaLocation=\"http://service-spi.web.cern.ch/"
            "service-spi/app/releases/GDML/schema/gdml.xsd\">\n"
         << "  <define/>\n"
         << "  <materials>\n";
  for (const auto &name : materialNames) {
    const auto *material = model.findMaterial(name);
    if (material == nullptr || material->atomicNumber <= 0 ||
        material->atomicWeightGramPerMole <= 0) {
      throw std::runtime_error("invalid DELPHI beam-pipe material: " + name);
    }
    auto density = material->densityGramPerCm3;
    if (density == 0 && name == "VACU") {
      // MATF uses zero as the DELPHI vacuum sentinel. Geant4 requires a
      // positive density, so retain its H-like Z/A and use a transport vacuum.
      density = 1.0e-25;
    }
    if (density <= 0) {
      throw std::runtime_error("non-positive DELPHI material density: " + name);
    }
    const auto id = gdmlName(name);
    output << "    <element name=\"delphi_element_" << id << "\" formula=\""
           << xmlEscape(name) << "\" Z=\"" << material->atomicNumber << "\">\n"
           << "      <atom unit=\"g/mole\" value=\""
           << material->atomicWeightGramPerMole << "\"/>\n"
           << "    </element>\n"
           << "    <material name=\"delphi_material_" << id << "\" state=\""
           << (density < 0.01 ? "gas" : "solid") << "\">\n"
           << "      <D unit=\"g/cm3\" value=\"" << density << "\"/>\n"
           << "      <fraction n=\"1\" ref=\"delphi_element_" << id << "\"/>\n"
           << "    </material>\n";
  }
  output << "  </materials>\n"
         << "  <solids>\n";

  output << "    <tube name=\"delphi_world_solid\" rmin=\""
         << worldParameters[2] << "\" rmax=\"" << worldParameters[3]
         << "\" z=\"" << worldParameters[5] - worldParameters[4]
         << "\" startphi=\"" << worldParameters[0] << "\" deltaphi=\""
         << worldParameters[1] - worldParameters[0]
         << "\" aunit=\"deg\" lunit=\"cm\"/>\n";
  for (const auto &node : nodes) {
    for (std::size_t index = 0; index < node.definition->shapes.size();
         ++index) {
      writeShape(output, node, node.definition->shapes[index], index);
    }
    for (std::size_t index = 1; index < node.definition->shapes.size();
         ++index) {
      output << "    <union name=\"" << nodeId(node) << "_union_" << index
             << "\">\n"
             << "      <first ref=\""
             << (index == 1
                     ? shapeId(node, 0)
                     : nodeId(node) + "_union_" + std::to_string(index - 1))
             << "\"/>\n"
             << "      <second ref=\"" << shapeId(node, index) << "\"/>\n"
             << "    </union>\n";
    }
  }
  output << "  </solids>\n"
         << "  <structure>\n";

  for (auto node = nodes.rbegin(); node != nodes.rend(); ++node) {
    const auto material = effectiveMaterial(*node).inner;
    output << "    <volume name=\"" << nodeId(*node) << "\">\n"
           << "      <materialref ref=\"delphi_material_" << gdmlName(material)
           << "\"/>\n"
           << "      <solidref ref=\"" << solidId(*node) << "\"/>\n";
    for (const auto childIndex : node->children) {
      const auto &child = nodes[childIndex];
      const auto &references = effectiveReferences(child);
      if (references.empty()) {
        writePlacement(output, nodeId(child) + "_placement", nodeId(child),
                       nullptr);
      } else {
        for (std::size_t index = 0; index < references.size(); ++index) {
          writePlacement(output,
                         nodeId(child) + "_placement_" + std::to_string(index),
                         nodeId(child), &references[index]);
        }
      }
    }
    output << "    </volume>\n";
  }

  const auto worldMaterial = world->materials.front().inner;
  output << "    <volume name=\"delphi_world\">\n"
         << "      <materialref ref=\"delphi_material_"
         << gdmlName(worldMaterial) << "\"/>\n"
         << "      <solidref ref=\"delphi_world_solid\"/>\n";
  const auto &rootReferences = effectiveReferences(nodes.front());
  if (rootReferences.empty()) {
    writePlacement(output, nodeId(nodes.front()) + "_placement",
                   nodeId(nodes.front()), nullptr);
  } else {
    for (std::size_t index = 0; index < rootReferences.size(); ++index) {
      writePlacement(
          output, nodeId(nodes.front()) + "_placement_" + std::to_string(index),
          nodeId(nodes.front()), &rootReferences[index]);
    }
  }
  if (!snapshotIdentifier.empty()) {
    output << "      <auxiliary auxtype=\"DELPHI_CARGO_SOURCE\" auxvalue=\""
           << xmlEscape(snapshotIdentifier) << "\"/>\n";
  }
  output << "    </volume>\n"
         << "  </structure>\n"
         << "  <setup name=\"DELPHI_BEAM_PIPE\" version=\"1.0\">\n"
         << "    <world ref=\"delphi_world\"/>\n"
         << "  </setup>\n"
         << "</gdml>\n";
  if (!output) {
    throw std::runtime_error("failed while writing DELPHI beam-pipe GDML");
  }
}

} // namespace delphi_edm4hep::geometry
