cmake_minimum_required(VERSION 3.24)  # LINK_GROUP genex needs >=3.24
project(delphi_edm4hep
  LANGUAGES CXX
  DESCRIPTION "DELPHI ZEBRA -> EDM4hep converter (per-domain library, two-pass)"
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Build type default: Release with debug info.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type" FORCE)
endif()

add_compile_options(-Wall -Wextra)

# key4hep stack pin. The converter is built and validated against one
# specific key4hep release (the -r argument to
#   source /cvmfs/sw.hsf.org/key4hep/setup.sh -r <release>
# sourced before cmake). find_package alone picks up whatever stack happens
# to be in the environment, so a drifting `latest` can silently swap
# EDM4hep/podio/ROOT versions under us. Parse the sourced release out of
# $KEY4HEP_STACK and require it to match the pin. Bump the pin here when
# migrating releases, or override per-build with -DKEY4HEP_RELEASE=...;
# set -DKEY4HEP_RELEASE_STRICT=OFF to demote a mismatch to a warning.
set(KEY4HEP_RELEASE "2026-04-08"
  CACHE STRING "key4hep stack release this build is pinned to")
option(KEY4HEP_RELEASE_STRICT
  "Fail configure when the sourced key4hep release differs from KEY4HEP_RELEASE" ON)
if(DEFINED ENV{KEY4HEP_STACK})
  string(REGEX MATCH "/releases/([^/]+)/" _k4h_unused "$ENV{KEY4HEP_STACK}")
  set(_k4h_sourced "${CMAKE_MATCH_1}")
  if(_k4h_sourced STREQUAL KEY4HEP_RELEASE)
    message(STATUS "key4hep: stack release ${_k4h_sourced} (matches pin)")
  elseif(KEY4HEP_RELEASE_STRICT)
    message(FATAL_ERROR
      "key4hep: sourced stack release '${_k4h_sourced}' does not match the "
      "pinned release '${KEY4HEP_RELEASE}'. Re-source with\n"
      "  source /cvmfs/sw.hsf.org/key4hep/setup.sh -r ${KEY4HEP_RELEASE}\n"
      "or configure with -DKEY4HEP_RELEASE=${_k4h_sourced} (after validating), "
      "or -DKEY4HEP_RELEASE_STRICT=OFF to proceed anyway.")
  else()
    message(WARNING
      "key4hep: sourced stack release '${_k4h_sourced}' != pinned "
      "'${KEY4HEP_RELEASE}' (KEY4HEP_RELEASE_STRICT=OFF, continuing)")
  endif()
else()
  message(WARNING
    "key4hep: \$KEY4HEP_STACK is not set — source "
    "/cvmfs/sw.hsf.org/key4hep/setup.sh -r ${KEY4HEP_RELEASE} before "
    "configuring. Proceeding with whatever EDM4hep/podio/ROOT find_package "
    "locates, which is NOT the validated stack.")
endif()

find_package(EDM4HEP 1.0 REQUIRED)
find_package(podio   1.7 REQUIRED)
find_package(ROOT        REQUIRED COMPONENTS Core RIO Matrix)
message(STATUS
  "key4hep: EDM4hep ${EDM4HEP_VERSION}, podio ${podio_VERSION}, ROOT ${ROOT_VERSION}")

# DELPHI almalinux-9 Fortran libraries (custom find module).
list(APPEND CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake)
find_package(DelphiAL9 REQUIRED)

# ---------------------------------------------------------------------------
# delphi_edm4hep library: pure C++, depends on edm4hep + podio + ROOT +
# DelphiAL9. No Fortran symbols are pulled in here directly; the Fortran
# linkage happens via the binaries (which need the full --start-group
# linker dance because the DELPHI archives have circular symbol deps).
add_library(delphi_edm4hep
  src/BankPrefix.cpp
  src/PerigeeMatch.cpp
  src/Helix.cpp
  src/TeBank.cpp
  src/PhdstHarness.cpp
  src/Event/Event.cpp
  src/Vertex/Vertex.cpp
  src/Tracking/Tracking.cpp
  src/Calorimeter/Calorimeter.cpp
  src/Pid/ParticleId.cpp
  src/Truth/Truth.cpp
  src/Tracking/MatchProvenance.cpp
  src/Pid/TofFdst.cpp
  src/Pid/MtpcFdst.cpp
  src/Tracking/TeStateMerge.cpp
  src/Calorimeter/EmcaFdst.cpp
  src/Calorimeter/HcalFdst.cpp
  src/Calorimeter/TeadFdst.cpp
  src/Tracking/MainHybrid.cpp
  src/Pid/PidHybrid.cpp
  src/Calorimeter/ShowerHybrid.cpp
  src/Truth/TblHybrid.cpp
  src/Pid/FdstPidExtras.cpp
  src/Calorimeter/TdhaFdst.cpp
  src/Pid/SdstPaExtras.cpp
  src/Calorimeter/SticShower.cpp
  src/Tracking/EltrSdst.cpp
  src/Tracking/TraxFdst.cpp
  src/Tracking/VdHits.cpp
  src/Pid/PidExtrasSdst.cpp
  src/Calorimeter/CcalFdst.cpp
)
target_include_directories(delphi_edm4hep
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(delphi_edm4hep
  PUBLIC
    EDM4HEP::edm4hep
    podio::podio
    podio::podioRootIO
    ROOT::Core
    ROOT::RIO
    ROOT::Matrix
  PRIVATE
    DelphiAL9::headers
)

# ---------------------------------------------------------------------------
# Helper interface target: full DELPHI Fortran linker group for binaries.
# Pulls in everything in the --start-group --end-group block plus gfortran
# and the small C deps.
add_library(delphi_fortran_link INTERFACE)
target_link_libraries(delphi_fortran_link
  INTERFACE
    DelphiAL9::fortran_group
    gfortran dl m z crypt
)

# ---------------------------------------------------------------------------
# Pass-1 binary (sDST -> intermediate edm4hep).
add_executable(delphi_sdst_pass bin/delphi_sdst_pass.cpp)
target_link_libraries(delphi_sdst_pass
  PRIVATE delphi_edm4hep delphi_fortran_link
)

# Pass-2 binary (intermediate edm4hep + fDST -> final edm4hep).
add_executable(delphi_fdst_pass bin/delphi_fdst_pass.cpp)
target_link_libraries(delphi_fdst_pass
  PRIVATE delphi_edm4hep delphi_fortran_link
)

# Standalone post-processing tool: per-run beamspot from aggregated PVs.
# Pure podio/ROOT — no PHDST, no DELPHI Fortran link group.
add_executable(delphi_bs_fit bin/delphi_bs_fit.cpp)
target_link_libraries(delphi_bs_fit
  PRIVATE EDM4HEP::edm4hep podio::podio podio::podioRootIO ROOT::Core ROOT::RIO
)

# ---------------------------------------------------------------------------
# Tests (subtask 5+; for now just smoke).
enable_testing()
if(EXISTS ${CMAKE_SOURCE_DIR}/tests/CMakeLists.txt)
  add_subdirectory(tests)
endif()

# ---------------------------------------------------------------------------
# Install rules.
include(GNUInstallDirs)
install(TARGETS delphi_edm4hep delphi_sdst_pass delphi_fdst_pass delphi_bs_fit
  EXPORT  delphi_edm4hepTargets
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/delphi_edm4hep
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
