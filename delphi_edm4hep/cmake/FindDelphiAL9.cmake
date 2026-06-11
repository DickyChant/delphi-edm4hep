# FindDelphiAL9.cmake
#
# Locate the DELPHI almalinux-9 Fortran libraries + the header-only C++
# wrappers around the SKELANA / PHDST common blocks.
#
# Variables:
#   DELPHI_AL9_ROOT       (cache, default /cvmfs/delphi.cern.ch/releases/almalinux-9-x86_64/latest)
#   DELPHI_AL9_LIB_DIR    (computed from ROOT; can override)
#   CERN_AL9_LIB_DIR      (computed from ROOT; can override)
#   DELPHI_ANALYSIS_INC   (cache; defaults to ${USER}'s checkout of delphi-nanoaod under /afs)
#
# Imported targets:
#   DelphiAL9::headers         INTERFACE; just the include dir for phdst.hpp / skelana/*.hpp
#   DelphiAL9::fortran_group   INTERFACE; the full --start-group/--end-group linker list,
#                              with -L paths set. Bring in gfortran/dl/m/z/crypt yourself.
#
# Sets DelphiAL9_FOUND if the headers + one canonical archive (libphdstxx.a) are present.

set(DELPHI_AL9_ROOT
  "/cvmfs/delphi.cern.ch/releases/almalinux-9-x86_64/latest"
  CACHE PATH "Root of the DELPHI AL9 release tree"
)
set(DELPHI_AL9_LIB_DIR
  "${DELPHI_AL9_ROOT}/dstana/161018/lib"
  CACHE PATH "DELPHI AL9 dstana lib dir (contains libphdstxx.a et al.)"
)
set(CERN_AL9_LIB_DIR
  "${DELPHI_AL9_ROOT}/cern/2025.09.18.4-free-im/lib"
  CACHE PATH "CERNLIB AL9 lib dir (contains libpacklib.a et al.)"
)

# Default include path: a few common spots in priority order. The user
# can always override with -DDELPHI_ANALYSIS_INC=...
# The first candidate is the in-tree git submodule (extern/delphi-nanoaod),
# so a fresh clone with `git submodule update --init` builds with no -D.
set(_delphi_inc_candidates
  "${CMAKE_SOURCE_DIR}/extern/delphi-nanoaod/delphi-analysis/include"
  "$ENV{HOME}/delphi-nanoaod/delphi-analysis/include"
)
set(DELPHI_ANALYSIS_INC "" CACHE PATH "Include dir for delphi-analysis (phdst.hpp etc.)")
if(NOT DELPHI_ANALYSIS_INC)
  foreach(_p ${_delphi_inc_candidates})
    if(EXISTS "${_p}/phdst.hpp")
      set(DELPHI_ANALYSIS_INC "${_p}" CACHE PATH "" FORCE)
      break()
    endif()
  endforeach()
endif()

# Sanity check: archive presence.
find_file(_delphi_phdstxx_archive
  NAMES libphdstxx.a
  PATHS ${DELPHI_AL9_LIB_DIR}
  NO_DEFAULT_PATH
)
find_file(_delphi_packlib_archive
  NAMES libpacklib.a
  PATHS ${CERN_AL9_LIB_DIR}
  NO_DEFAULT_PATH
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(DelphiAL9
  REQUIRED_VARS
    DELPHI_AL9_LIB_DIR
    CERN_AL9_LIB_DIR
    DELPHI_ANALYSIS_INC
    _delphi_phdstxx_archive
    _delphi_packlib_archive
)

if(DelphiAL9_FOUND)
  # Header-only target.
  if(NOT TARGET DelphiAL9::headers)
    add_library(DelphiAL9::headers INTERFACE IMPORTED)
    target_include_directories(DelphiAL9::headers
      INTERFACE "${DELPHI_ANALYSIS_INC}"
    )
  endif()

  # Fortran linker group. DELPHI archives have circular dependencies so
  # they must be wrapped in --start-group/--end-group, AND must come
  # AFTER the binary's object file on the link line (otherwise the
  # archive's default main / user00_..user99_ stubs are pulled in before
  # the user binary's overrides are seen, producing multiple-definition
  # errors).
  #
  # CMake's LINK_GROUP generator expression (3.24+) handles this: the
  # group ends up as -Wl,--start-group <-l...> -Wl,--end-group with
  # correct placement relative to object files when used through
  # target_link_libraries(... PRIVATE ...).
  if(NOT TARGET DelphiAL9::fortran_group)
    add_library(DelphiAL9::fortran_group INTERFACE IMPORTED)
    target_link_directories(DelphiAL9::fortran_group INTERFACE
      "${DELPHI_AL9_LIB_DIR}"
      "${CERN_AL9_LIB_DIR}"
    )
    target_link_libraries(DelphiAL9::fortran_group INTERFACE
      "$<LINK_GROUP:RESCAN,phdstxx,skelanaxx,dstanaxx,pxdstxx,vfclapxx,vdclapxx,ufieldxx,bsaurusxx,herlibxx,triggerxx,uhlibxx,mathlib,packlib,kernlib,ariadne,herwig59,jetset74>"
    )
  endif()
endif()

mark_as_advanced(
  _delphi_phdstxx_archive
  _delphi_packlib_archive
)
