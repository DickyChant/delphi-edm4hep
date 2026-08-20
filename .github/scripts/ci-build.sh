#!/bin/bash
# CI build + test recipe. Runs inside a bare AlmaLinux 9 container with
# /cvmfs bind-mounted and the repo at /repo (see .github/workflows/ci.yml).
#
# Reproduce locally on any host with apptainer and /cvmfs:
#   apptainer exec --containall --fakeroot --writable-tmpfs \
#     -B /cvmfs:/cvmfs -B "$PWD":/repo docker://almalinux:9 \
#     bash /repo/.github/scripts/ci-build.sh
set -e

# OS bits the toolchains expect from the base system: glibc dev files for
# the key4hep (spack) gcc, plus the -lz / -lcrypt dev symlinks needed by the
# DELPHI Fortran link line. Everything else (gcc, cmake, make, ROOT, ...)
# comes from cvmfs.
dnf install -y -q --setopt=install_weak_deps=False \
  glibc-devel zlib-devel libxcrypt-devel

# key4hep release: an optional first argument overrides the KEY4HEP_RELEASE
# pin in CMakeLists.txt (used by the bump-check canary to trial-build a newer
# stack); with no argument the pin is the single source of truth.
KEY4HEP_RELEASE=${1:-$(sed -n 's/^set(KEY4HEP_RELEASE "\([^"]*\)".*/\1/p' \
  /repo/delphi_edm4hep/CMakeLists.txt)}
if [ -z "${KEY4HEP_RELEASE}" ]; then
  echo "ERROR: could not extract KEY4HEP_RELEASE from CMakeLists.txt" >&2
  exit 1
fi
echo "Using key4hep release ${KEY4HEP_RELEASE}$( [ -n "${1:-}" ] && echo ' (override)' || echo ' (from the CMakeLists.txt pin)')"

# DELPHI first, then key4hep (same order as the README). The DELPHI profile
# prints harmless 'gcc: command not found' probe warnings in a bare container.
source /cvmfs/delphi.cern.ch/setup.sh
source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "${KEY4HEP_RELEASE}"
unset CXXFLAGS CFLAGS LDFLAGS  # DELPHI env injects CERNLIB-era flags; see README

cmake -S /repo/delphi_edm4hep -B /repo/build \
  -DKEY4HEP_RELEASE="${KEY4HEP_RELEASE}"
cmake --build /repo/build -j"$(nproc)"
ctest --test-dir /repo/build --output-on-failure
