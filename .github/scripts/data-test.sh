#!/bin/bash
# Conversion identity test, run on the self-hosted runner.
#
# Sets up the DELPHI and key4hep environments, then hands over to
# delphi_edm4hep/tests/run_tests.py. Everything after the environment is
# Python; this script exists because the environments are shell profiles.
#
#   data-test.sh                     compare every sample against its reference
#   data-test.sh <id> [<id> ...]     only those samples
#   data-test.sh --bless [<id>]      regenerate references instead
#
# Expects the build artifact unpacked at build/ in the workspace. The key4hep
# release is read from .github/key4hep-production-release, the same pin the
# production build uses.
#
# Overrides: DELPHI_CI_WORK (scratch), DELPHI_CI_REFS (reference store).
set -e

# Saved before `set --` below, which clears the positional parameters.
ARGS=("$@")

REPO="${GITHUB_WORKSPACE:-$PWD}"
BIN="${REPO}/build/delphi_sdst_pass"
BTAG="${REPO}/build/delphi_btag_check"
TESTS="${REPO}/delphi_edm4hep/tests"
WORK="${DELPHI_CI_WORK:-${RUNNER_TEMP:-/tmp}/delphi-dt}"
REFS="${DELPHI_CI_REFS:-/home/delphi-ci/refs}"

[ -x "${BIN}" ] || { echo "no converter at ${BIN} - is the build artifact unpacked?" >&2; exit 1; }
[ -x "${BTAG}" ] || { echo "no checker at ${BTAG} - is the build artifact unpacked?" >&2; exit 1; }
PIN="${REPO}/.github/key4hep-production-release"
K4="$(tr -d '[:space:]' < "${PIN}" 2>/dev/null || true)"
[ -n "${K4}" ] || { echo "no key4hep release in ${PIN}" >&2; exit 1; }

# `source setup.sh` with no arguments passes ours through, and key4hep then
# warns about an unknown argument, so clear them first.
set --
source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "${K4}" >/dev/null 2>&1 || true
[ -n "${KEY4HEP_STACK:-}" ] || { echo "key4hep ${K4} did not set up" >&2; exit 1; }

# The DELPHI profile exports CERNLIB-era compiler flags that break later builds.
unset CXXFLAGS CFLAGS LDFLAGS

# Read the inputs from CERN Open Data. Without this the DELPHI profile prefers
# /eos/experiment/delphi/castor2015 whenever it happens to be mounted, which
# needs credentials; fatfind resolves nicknames under either root.
export DELPHI_DATA_ROOT=/eos/opendata/delphi
[ -d "${DELPHI_DATA_ROOT}/collision-data" ] \
  || { echo "${DELPHI_DATA_ROOT} is not mounted" >&2; exit 1; }

rm -rf "${WORK}"
mkdir -p "${WORK}" "${REFS}"

echo "converter ${BIN}"
echo "key4hep   ${K4}"
echo "data root ${DELPHI_DATA_ROOT}"

exec python3 "${TESTS}/run_tests.py" \
  --bin "${BIN}" \
  --btag-check "${BTAG}" \
  --work "${WORK}" \
  --refs "${REFS}" \
  --key4hep "${K4}" \
  ${GITHUB_STEP_SUMMARY:+--summary "${GITHUB_STEP_SUMMARY}"} \
  "${ARGS[@]}"
