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

# key4hep release — three modes via the optional first argument:
#   (none)     pin mode: the KEY4HEP_RELEASE pin in CMakeLists.txt, the
#              single source of truth. Regular CI uses this: a release is
#              not trusted until it has been tested.
#   newest     canary mode: source setup.sh with NO -r, letting key4hep's
#              own resolution pick the newest dated release (never `-r
#              latest` — that is a stale 2024-04-12 remnant). Used by the
#              dependency canary to trial-build bump candidates.
#   <release>  trial-build one specific release.
# In all modes the release the setup actually resolved is read back from
# $KEY4HEP_STACK and passed to cmake as -DKEY4HEP_RELEASE, so the pin gate
# sees the candidate deliberately and the cache/badges record what was
# really used.
MODE=${1:-}
if [ -z "${MODE}" ]; then
  MODE=$(sed -n 's/^set(KEY4HEP_RELEASE "\([^"]*\)".*/\1/p' \
    /repo/delphi_edm4hep/CMakeLists.txt)
  if [ -z "${MODE}" ]; then
    echo "ERROR: could not extract KEY4HEP_RELEASE from CMakeLists.txt" >&2
    exit 1
  fi
fi

# DELPHI first, then key4hep (same order as the README). The DELPHI profile
# prints harmless 'gcc: command not found' probe warnings in a bare container.
source /cvmfs/delphi.cern.ch/setup.sh
if [ "${MODE}" = "newest" ]; then
  source /cvmfs/sw.hsf.org/key4hep/setup.sh
else
  source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "${MODE}"
fi
unset CXXFLAGS CFLAGS LDFLAGS  # DELPHI env injects CERNLIB-era flags; see README

KEY4HEP_RELEASE=$(echo "${KEY4HEP_STACK}" | sed -n 's|.*/releases/\([^/]*\)/.*|\1|p')
if [ -z "${KEY4HEP_RELEASE}" ]; then
  echo "ERROR: key4hep setup did not export \$KEY4HEP_STACK — stack not set up" >&2
  exit 1
fi
echo "Using key4hep release ${KEY4HEP_RELEASE} (mode: ${1:-pin})"
# Marker for the workflows: survives build failure, so the canary can badge
# a failing release by name.
echo "${KEY4HEP_RELEASE}" > /repo/.key4hep-resolved

cmake -S /repo/delphi_edm4hep -B /repo/build \
  -DKEY4HEP_RELEASE="${KEY4HEP_RELEASE}"
cmake --build /repo/build -j"$(nproc)"
ctest --test-dir /repo/build --output-on-failure
