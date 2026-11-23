#!/bin/bash
# Two-pass EDM4hep conversion on DATA, using the existing official short DST for
# the SDST-level collections and OUR reproduced data full DST (from
# run_data_reco.sh) for the genuinely-full-DST collections (EMCA HPC clusters,
# HCAL towers, TOF, TDHA, TRAX extrap, TDID drift-calib, MU chambers, dE/dx ...).
#
# This is the "two-pass on data" the project needed: the official .al alone
# leaves all fDST_* full-DST collections EMPTY (it's a short DST); feeding pass-2
# a real full DST populates them. pass-2 drives on the full DST and looks up the
# matching pass-1 frame by (run, evt), so the official .al (many runs, physics-
# selected) and our single-run full DST line up correctly on their overlap.
#
# Env note (important): the converter reads raw DELPHI files via PHDST, so it
# needs BOTH the DELPHI environment (pdl2pdl on PATH, $DELPHI_DAT for VD
# alignment) AND key4hep (podio/edm4hep). Source DELPHI first, then key4hep
# (key4hep's ROOT wins; the DELPHI Fortran is statically linked in the binaries).
#
# Usage:
#   run_data_twopass.sh <official.al> <our_fulldst> <out_dir> [<n>]
# B-tag production is fixed to recalculated AABTAG. A legacy BTAG_MODE
# environment value is accepted only when it is exactly `recalc`.
# Example (run 44249):
#   run_data_twopass.sh \
#     /eos/experiment/delphi/castor2015/tape/Y13709/Y13709.41.al \
#     /path/to/scratch/datareco/run44249_full_delana.dst \
#     /path/to/scratch/datareco/twopass 1100

set -euo pipefail
AL=${1:?official short DST (.al) required}
FULLDST=${2:?reproduced data full DST required}
OUT=${3:-$PWD/twopass}
N=${4:-1100}
requested_btag_mode=${BTAG_MODE-recalc}
if [[ $requested_btag_mode != recalc ]]; then
  echo "ERROR: run_data_twopass.sh is recalculated-AABTAG-only; " \
       "BTAG_MODE=$requested_btag_mode is not a production mode" >&2
  exit 2
fi
BTAG_MODE=recalc
readonly BTAG_MODE
PRIMARY_VERTEX_POLICY=keep-delana
readonly PRIMARY_VERTEX_POLICY
[[ $N =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: n must be a positive integer (got: $N)" >&2
  exit 2
}
[[ -f $AL ]] || { echo "ERROR: official short DST not found: $AL" >&2; exit 2; }
[[ -f $FULLDST ]] || { echo "ERROR: reproduced full DST not found: $FULLDST" >&2; exit 2; }
OUT=$(realpath -m -- "$OUT")
[[ $OUT != / ]] || { echo "ERROR: refusing to use / as out_dir" >&2; exit 2; }

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE=${IMAGE:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el9:x86_64}
EDM=${EDM:-$(cd "$HERE/../.." && pwd)/build}
KEY4HEP_RELEASE=${KEY4HEP_RELEASE:-2026-04-08}
[[ -d $EDM ]] || { echo "ERROR: converter build directory not found: $EDM" >&2; exit 2; }
EDM=$(realpath -- "$EDM")
for binary in delphi_sdst_pass delphi_fdst_pass delphi_btag_check; do
  [[ -x $EDM/$binary && ! -L $EDM/$binary ]] || {
    echo "ERROR: required regular executable not found: $EDM/$binary" >&2
    exit 2
  }
done

mkdir -p -- "$OUT"
cp -- "$AL"      "$OUT/sdst_official.al"
cp -- "$FULLDST" "$OUT/ours.fadana"

singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
  --bind "$OUT:$OUT" --bind "$EDM:/edmbin:ro" "$IMAGE" bash -c '
    set +u; set -eo pipefail
    source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
    source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
    cd -- "$2"
    echo "=== PASS 1: delphi_sdst_pass on official short DST (UNCAPPED) ==="
    # No -n on pass 1: the official .al spans many runs and pass 2 matches by
    # (run,evt); capping pass 1 can stop before the events pass 2 needs, silently
    # yielding an empty/incomplete final file. -n caps pass 2 (the final output).
    /edmbin/delphi_sdst_pass sdst_official.al intermediate.edm4hep.root --btag "$3"
    /edmbin/delphi_btag_check --source sDST --primary-vertex-policy "$5" \
      intermediate.edm4hep.root data "$3"
    echo "=== PASS 2: delphi_fdst_pass (intermediate + our reproduced full DST) ==="
    /edmbin/delphi_fdst_pass intermediate.edm4hep.root ours.fadana final.edm4hep.root -n "$4" --btag "$3"
    # The final frame has copied sDST_EVT identity plus two independent b-tag
    # payload prefixes. Validate each content domain explicitly; an fDST check
    # never claims that copied sDST_EVT identity is fDST provenance.
    /edmbin/delphi_btag_check --source sDST --primary-vertex-policy "$5" \
      final.edm4hep.root data "$3"
    /edmbin/delphi_btag_check --source fDST --primary-vertex-policy "$5" \
      final.edm4hep.root data "$3"
  ' run_data_twopass "$KEY4HEP_RELEASE" "$OUT" "$BTAG_MODE" "$N" \
    "$PRIMARY_VERTEX_POLICY"
echo "=== DONE ==="
ls -la "$OUT/final.edm4hep.root"
echo "validated final EDM4hep with independent sDST and fDST b-tag content: $OUT/final.edm4hep.root"
