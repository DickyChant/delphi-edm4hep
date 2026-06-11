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

# key4hep dependencies. The user is expected to have sourced
#   /cvmfs/sw.hsf.org/key4hep/setup.sh -r <release>
# before running cmake. find_package picks up EDM4hep and podio from that.
find_package(EDM4HEP REQUIRED)
find_package(podio   REQUIRED)
find_package(ROOT    REQUIRED COMPONENTS Core RIO Matrix)

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
