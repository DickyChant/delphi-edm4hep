#!/usr/bin/env bash
# Large-scale 94c data -> EDM4hep batch. Resumable + parallel.
#   Phase A: for each unique official .al, pass1 -> cached intermediate.
#   Phase B: per run: raw .sl -> DELANA full DST (MBLIMI raised) -> pass2 with the
#            cached intermediate -> EDM4hep; delete the full DST. Skip if done.
#
# Usage: batch_94c.sh <N runs from worklist | all> [<n_parallel>] [all|sdst]
# Production policy is fixed to prefix-isolated AABTAG recalculation.
set -uo pipefail

requested_btag_mode=${BTAG_MODE-recalc}
if [[ $requested_btag_mode != recalc ]]; then
  echo "ERROR: batch_94c.sh is recalculated-AABTAG-only; " \
       "BTAG_MODE=$requested_btag_mode is not a production mode" >&2
  exit 2
fi
BTAG_MODE=recalc
readonly BTAG_MODE
PRIMARY_VERTEX_POLICY=keep-delana
readonly PRIMARY_VERTEX_POLICY
ROOT=${ROOT:-$HOME/scratch/datareco/batch94c_recalc}
N=${1:-30}; PAR=${2:-6}; PHASE=${3:-all}
[[ $PAR =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: n_parallel must be a positive integer" >&2
  exit 2
}
[ "$PHASE" = all ] || [ "$PHASE" = sdst ] || {
  echo "ERROR: phase must be 'all' or 'sdst'" >&2
  exit 2
}

mkdir -p -- "$ROOT" || exit 2
ROOT=$(realpath -- "$ROOT") || exit 2
[[ $ROOT != / ]] || {
  echo "ERROR: refusing to use / as the campaign root" >&2
  exit 2
}
WORKLIST=$ROOT/worklist.txt
INT=$ROOT/intermediates      # cached pass1 outputs (keyed by Y-VID.seq)
EDM=$ROOT/edm4hep            # final per-run EDM4hep (the product)
SCR=$ROOT/scratch            # transient full DSTs / .al copies
LOG=$ROOT/logs

[[ -f $WORKLIST && ! -L $WORKLIST ]] || {
  echo "ERROR: regular worklist not found: $WORKLIST" >&2
  exit 2
}

# Worklist fields later become scratch/output path components. Validate the
# complete file before creating or removing any path derived from a row.
if ! LC_ALL=C awk '
  NF != 3 || $1 !~ /^ED[0-9]+\.[0-9]+$/ || $2 !~ /^[1-9][0-9]*$/ ||
      $3 !~ /^Y[0-9]+\.[0-9]+(,Y[0-9]+\.[0-9]+)*$/ {
    printf "invalid worklist line %d: %s\\n", NR, $0 > "/dev/stderr"
    bad=1
    next
  }
  seen[$1]++ {
    printf "duplicate raw segment at worklist line %d: %s\\n", NR, $1 \
      > "/dev/stderr"
    bad=1
  }
  {
    n=split($3,tapes,",")
    for (i=1; i<=n; ++i) {
      key=NR SUBSEP tapes[i]
      if (seen_tape[key]++) {
        printf "duplicate tape at worklist line %d: %s\\n", NR, tapes[i] \
          > "/dev/stderr"
        bad=1
      }
    }
  }
  END {
    if (NR == 0) {
      print "worklist is empty" > "/dev/stderr"
      bad=1
    }
    exit bad ? 1 : 0
  }
' "$WORKLIST"; then
  echo "ERROR: worklist grammar validation failed" >&2
  exit 2
fi

[ "$N" = all ] && N=$(wc -l < "$WORKLIST")
[[ $N =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: N must be a positive integer or 'all'" >&2
  exit 2
}

command -v flock >/dev/null 2>&1 || {
  echo "ERROR: flock is required" >&2
  exit 2
}
command -v sha256sum >/dev/null 2>&1 || {
  echo "ERROR: sha256sum is required" >&2
  exit 2
}

# The files below (`worklist.run`, manifests, logs and final names) are shared
# campaign state. A whole-campaign lock prevents two invocations with different
# selections from racing while workers are active.
exec {campaign_lock_fd}>"$ROOT/.campaign.lock"
if ! flock -n "$campaign_lock_fd"; then
  echo "ERROR: campaign is already active: $ROOT" >&2
  exit 2
fi

mkdir -p "$INT" "$EDM" "$SCR" "$LOG"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE=${IMAGE:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el9:x86_64}
EDMBIN=${EDMBIN:-$(cd "$HERE/../.." && pwd)/build}
KEY4HEP_RELEASE=${KEY4HEP_RELEASE:-2026-04-08}
RECO="$HERE/run_data_reco.sh"   # relocated as a sibling (was Delphi-Sim-Pipeline/container/run_data_reco.sh)
RAWBASE=/eos/experiment/delphi/castor2015/rawd/y94
ALBASE=/eos/experiment/delphi/castor2015/tape

[[ -d $EDMBIN ]] || {
  echo "ERROR: EDM4hep binary directory not found: $EDMBIN" >&2
  exit 2
}
EDMBIN=$(realpath -- "$EDMBIN") || exit 2
for binary in delphi_sdst_pass delphi_fdst_pass; do
  [[ -f $EDMBIN/$binary && -x $EDMBIN/$binary && ! -L $EDMBIN/$binary ]] || {
    echo "ERROR: required converter is not a regular executable: $EDMBIN/$binary" >&2
    exit 2
  }
done
[[ -f $EDMBIN/delphi_btag_check && -x $EDMBIN/delphi_btag_check && \
   ! -L $EDMBIN/delphi_btag_check ]] || {
  echo "ERROR: required b-tag checker is not a regular executable: " \
       "$EDMBIN/delphi_btag_check" >&2
  exit 2
}
WORKLIST=$(realpath -- "$WORKLIST") || exit 2
WORKLIST_SHA256=$(sha256sum -- "$WORKLIST")
WORKLIST_SHA256=${WORKLIST_SHA256%% *}
SDST_BINARY_SHA256=$(sha256sum -- "$EDMBIN/delphi_sdst_pass")
SDST_BINARY_SHA256=${SDST_BINARY_SHA256%% *}
FDST_BINARY_SHA256=$(sha256sum -- "$EDMBIN/delphi_fdst_pass")
FDST_BINARY_SHA256=${FDST_BINARY_SHA256%% *}
BTAG_CHECKER_SHA256=$(sha256sum -- "$EDMBIN/delphi_btag_check")
BTAG_CHECKER_SHA256=${BTAG_CHECKER_SHA256%% *}

# Bind all resumable products to immutable campaign inputs. N/PHASE are
# deliberately absent: a caller may safely resume any prefix of this same full
# worklist, but cannot switch b-tag mode, release, binaries, or source roots in
# place.
EXPECTED_CONFIG=$(mktemp --tmpdir="$ROOT" .campaign.conf.XXXXXX.tmp) || exit 2
cleanup_config_tmp() { rm -f -- "$EXPECTED_CONFIG"; }
trap cleanup_config_tmp EXIT
{
  printf 'format=delphi-batch94c-v3\n'
  printf 'btag_mode=%s\n' "$BTAG_MODE"
  printf 'primary_vertex_policy=%s\n' "$PRIMARY_VERTEX_POLICY"
  printf 'worklist=%s\n' "$WORKLIST"
  printf 'worklist_sha256=%s\n' "$WORKLIST_SHA256"
  printf 'key4hep_release=%s\n' "$KEY4HEP_RELEASE"
  printf 'edmbin=%s\n' "$EDMBIN"
  printf 'sdst_binary_sha256=%s\n' "$SDST_BINARY_SHA256"
  printf 'fdst_binary_sha256=%s\n' "$FDST_BINARY_SHA256"
  printf 'btag_checker_sha256=%s\n' "$BTAG_CHECKER_SHA256"
  printf 'image=%s\n' "$IMAGE"
  printf 'raw_base=%s\n' "$RAWBASE"
  printf 'tape_base=%s\n' "$ALBASE"
} > "$EXPECTED_CONFIG"
if [[ -e $ROOT/campaign.conf || -L $ROOT/campaign.conf ]]; then
  [[ -f $ROOT/campaign.conf && ! -L $ROOT/campaign.conf ]] || {
    echo "ERROR: campaign.conf is not a regular file" >&2
    exit 2
  }
  cmp -s -- "$EXPECTED_CONFIG" "$ROOT/campaign.conf" || {
    echo "ERROR: campaign configuration mismatch: $ROOT/campaign.conf" >&2
    diff -u -- "$ROOT/campaign.conf" "$EXPECTED_CONFIG" >&2 || true
    exit 2
  }
  rm -f -- "$EXPECTED_CONFIG"
else
  # Never attach an unbound pre-existing product to the current binaries and
  # worklist merely because this is the first run of the hardened driver.
  shopt -s nullglob
  unbound_products=(
    "$INT"/inter_*.root "$INT"/inter_*.root.complete
    "$EDM"/run*.edm4hep.root "$EDM"/run*.edm4hep.root.complete
  )
  shopt -u nullglob
  if ((${#unbound_products[@]} != 0)); then
    echo "ERROR: campaign.conf is absent but resumable products already exist; " \
         "use a fresh ROOT or audit/migrate the old campaign explicitly" >&2
    exit 2
  fi
  mv -- "$EXPECTED_CONFIG" "$ROOT/campaign.conf" || exit 2
fi
CAMPAIGN_SHA256=$(sha256sum -- "$ROOT/campaign.conf")
CAMPAIGN_SHA256=${CAMPAIGN_SHA256%% *}
trap - EXIT

head -n "$N" "$WORKLIST" > "$ROOT/worklist.run"
selected=$(wc -l < "$ROOT/worklist.run")
((selected == N)) || {
  echo "ERROR: requested $N worklist rows, but only $selected are available" >&2
  exit 2
}

# ---------- Phase A: build cached pass1 intermediates for the needed .al ----------
awk '{n=split($3,a,","); for(i=1;i<=n;i++) print a[i]}' "$WORKLIST" | LC_ALL=C sort -u > "$ROOT/al.all"
awk '{n=split($3,a,","); for(i=1;i<=n;i++) print a[i]}' "$ROOT/worklist.run" | LC_ALL=C sort -u > "$ROOT/al.run"
echo "=== Phase A: $(wc -l < "$ROOT/al.run") unique .al -> intermediates (par=$PAR) ==="

positive_harness_count () {
  local log=$1 line count= matches=0
  [[ -f $log && ! -L $log ]] || return 1
  while IFS= read -r line; do
    if [[ $line =~ ^delphi_edm4hep::harness:[[:space:]]+wrote[[:space:]]+([0-9]+)[[:space:]]+events[[:space:]]+to([[:space:]]|$) ]]; then
      count=${BASH_REMATCH[1]}
      matches=$((matches + 1))
    fi
  done < "$log"
  ((matches == 1)) || return 1
  count=$((10#$count))
  ((count > 0)) || return 1
  printf '%d\n' "$count"
}

positive_btag_check_summary () {
  local log=$1 expected_events=$2 expected_source=$3
  local line summary= matches=0 entries= counter
  [[ -f $log && ! -L $log ]] || return 1
  while IFS= read -r line; do
    if [[ $line =~ ^status=(PASS|FAIL)[[:space:]] ]]; then
      summary=$line
      matches=$((matches + 1))
    fi
  done < "$log"
  ((matches == 1)) || return 1
  [[ $summary =~ ^status=PASS[[:space:]] ]] || return 1
  [[ $summary == *" source=$expected_source "* ]] || return 1
  [[ $summary == *" identity_source=sDST_EVT "* ]] || return 1
  [[ $summary == *" btag_mode=$BTAG_MODE "* ]] || return 1
  [[ $summary == *" chi2_pv_contract=attached-only-v1 "* ]] || return 1
  [[ $summary == *" chi2_pv_roundoff_tolerance=0.25 "* ]] || return 1
  [[ $summary == *" provenance_schema=source-local-v1 "* ]] || return 1
  [[ $summary == *" primary_vertex_policy=$PRIMARY_VERTEX_POLICY "* ]] || return 1
  [[ $summary == *" primary_vertex_policy_expected=$PRIMARY_VERTEX_POLICY "* ]] || return 1
  [[ $summary == *" iflpvt=0 "* ]] || return 1
  [[ $summary == *" primary_vertex_policy_failures=0 "* ]] || return 1
  [[ $summary == *" failures=0 "* ]] || return 1
  for counter in \
      off_payload_presence_failures \
      bank_payload_empty_failures \
      track_impact_nonfinite_failures \
      track_error_domain_failures \
      track_chi2_domain_failures \
      track_momentum_domain_failures \
      track_integer_domain_failures \
      pv_primary_flag_failures \
      pv_algorithm_type_failures \
      pv_nonfinite_failures \
      pv_ndf_domain_failures; do
    [[ " $summary " == *" $counter=0 "* ]] || return 1
  done
  if [[ $summary =~ (^|[[:space:]])entries=([0-9]+)($|[[:space:]]) ]]; then
    entries=$((10#${BASH_REMATCH[2]}))
  else
    return 1
  fi
  ((entries == expected_events && entries > 0)) || return 1
  printf '%s\n' "$summary"
}

run_btag_check () {
  local candidate=$1 source=$2 validation_log=$3
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$ROOT:$ROOT" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
      set -eo pipefail
      set +u
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      exec /edmbin/delphi_btag_check --source "$3" \
        --primary-vertex-policy "$5" "$2" data "$4"
    ' batch_94c "$KEY4HEP_RELEASE" "$candidate" "$source" "$BTAG_MODE" \
      "$PRIMARY_VERTEX_POLICY" \
    > "$validation_log" 2>&1
}

render_completion_marker () {
  local phase=$1 item=$2 output=$3 events=$4 size_bytes=$5 output_sha=$6
  local sdst_summary=$7 fdst_summary=$8
  printf 'format=delphi-batch94c-complete-v2\n'
  printf 'phase=%s\n' "$phase"
  printf 'item=%s\n' "$item"
  printf 'output=%s\n' "${output##*/}"
  printf 'events=%s\n' "$events"
  printf 'output_size_bytes=%s\n' "$size_bytes"
  printf 'output_sha256=%s\n' "$output_sha"
  printf 'btag_mode=%s\n' "$BTAG_MODE"
  printf 'primary_vertex_policy=%s\n' "$PRIMARY_VERTEX_POLICY"
  printf 'btag_checker_sha256=%s\n' "$BTAG_CHECKER_SHA256"
  printf 'sdst_btag_check_summary=%s\n' "$sdst_summary"
  printf 'fdst_btag_check_summary=%s\n' "$fdst_summary"
  printf 'campaign_sha256=%s\n' "$CAMPAIGN_SHA256"
}

# Validate a product against the converter's unique positive "wrote N events"
# footer, its SHA-256, and prefix-specific direct checker summaries. Phase B
# always reopens the product and validates both copied sDST content and live
# fDST content; a completion marker is never treated as sufficient evidence.
validate_or_upgrade_completion () {
  local output=$1 marker=$2 log=$3 phase=$4 item=$5
  local sdst_log=$6 fdst_log=${7:-}
  local events size_bytes output_sha expected_marker
  local sdst_summary fdst_summary=not-applicable
  [[ -s $output && -f $output && ! -L $output ]] || return 1
  events=$(positive_harness_count "$log") || {
    echo "ERROR: no unique positive harness count in $log" >&2
    return 1
  }
  run_btag_check "$output" sDST "$sdst_log" || {
    echo "ERROR: direct sDST b-tag check failed for $output" >&2
    return 1
  }
  if [[ $phase == B ]]; then
    run_btag_check "$output" fDST "$fdst_log" || {
      echo "ERROR: direct fDST b-tag check failed for $output" >&2
      return 1
    }
  fi
  sdst_summary=$(positive_btag_check_summary "$sdst_log" "$events" sDST) || {
    echo "ERROR: no unique passing sDST b-tag check for $events events in $sdst_log" >&2
    return 1
  }
  if [[ $phase == B ]]; then
    fdst_summary=$(positive_btag_check_summary "$fdst_log" "$events" fDST) || {
      echo "ERROR: no unique passing fDST b-tag check for $events events in $fdst_log" >&2
      return 1
    }
  fi
  size_bytes=$(stat -c %s -- "$output") || return 1
  output_sha=$(sha256sum -- "$output") || return 1
  output_sha=${output_sha%% *}
  expected_marker=$(mktemp --tmpdir="${marker%/*}" ".${marker##*/}.XXXXXX.tmp") \
    || return 1
  if ! render_completion_marker "$phase" "$item" "$output" "$events" \
      "$size_bytes" "$output_sha" "$sdst_summary" "$fdst_summary" \
      > "$expected_marker"; then
    rm -f -- "$expected_marker"
    return 1
  fi
  if [[ -e $marker || -L $marker ]]; then
    if [[ ! -f $marker || -L $marker ]]; then
      echo "ERROR: completion marker is not a regular file: $marker" >&2
      rm -f -- "$expected_marker"
      return 1
    fi
    if [[ -s $marker ]]; then
      if cmp -s -- "$expected_marker" "$marker"; then
        rm -f -- "$expected_marker"
        return 0
      fi
      echo "ERROR: completion marker does not match product/campaign: $marker" >&2
      rm -f -- "$expected_marker"
      return 1
    fi
  fi
  if mv -f -- "$expected_marker" "$marker"; then
    echo "upgraded completion marker: $marker (events=$events)"
    return 0
  fi
  rm -f -- "$expected_marker"
  return 1
}

build_intermediate () {
  local alseq=$1                       # e.g. Y13709.41
  local out=$INT/inter_${alseq}.root
  local done=$out.complete
  local tmp=$INT/.inter_${alseq}.${BASHPID}.tmp.root
  local sdst_check=$LOG/A_${alseq}.sdst.validation.log
  if [[ -e $out || -L $out ]]; then
    if validate_or_upgrade_completion "$out" "$done" \
        "$LOG/A_$alseq.log" A "$alseq" "$sdst_check"; then
      echo "skip $alseq (validated cached product)"
      return 0
    fi
    echo "FAIL $alseq (cached product lacks valid completion evidence)" >&2
    return 1
  fi
  if [[ -e $done || -L $done ]]; then
    echo "FAIL $alseq (marker exists without its product: $done)" >&2
    return 1
  fi
  local yvid=${alseq%%.*}
  local al=$ALBASE/$yvid/$alseq.al
  [[ -f $al && ! -L $al ]] || { echo "MISSING al $al" >&2; return 1; }
  local w=$SCR/A_${alseq}.${BASHPID}
  mkdir -p "$w" || return 1
  if ! cp -- "$al" "$w/in.al"; then
    rm -rf -- "$w"
    return 1
  fi
  local rc=0
  # All values used inside the container are positional arguments. Keeping the
  # script body single-quoted prevents paths or mode strings from becoming
  # shell syntax.
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$w:$w" --bind "$INT:$INT" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
      set -eo pipefail
      set +u
      source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      cd -- "$2"
      # Cache the full tape (no -n): Phase B matches by (run,event).
      exec /edmbin/delphi_sdst_pass in.al "$3" --btag "$4"
    ' batch_94c "$KEY4HEP_RELEASE" "$w" "$tmp" "$BTAG_MODE" \
    > "$LOG/A_$alseq.log" 2>&1 || rc=$?
  if ((rc == 0)) && [[ -s $tmp ]]; then
    if positive_harness_count "$LOG/A_$alseq.log" >/dev/null &&
       run_btag_check "$tmp" sDST "$sdst_check" &&
       mv -- "$tmp" "$out" &&
       validate_or_upgrade_completion "$out" "$done" \
         "$LOG/A_$alseq.log" A "$alseq" "$sdst_check"; then
      echo "OK $alseq"
    else
      rc=1
    fi
  else
    ((rc != 0)) || rc=1
  fi
  if ((rc != 0)); then
    echo "FAIL $alseq (exit $rc; log: $LOG/A_$alseq.log)" >&2
    rm -f -- "$tmp"
  fi
  rm -rf -- "$w"
  return "$rc"
}
export -f positive_harness_count positive_btag_check_summary run_btag_check
export -f render_completion_marker
export -f validate_or_upgrade_completion build_intermediate
export ROOT INT SCR ALBASE EDMBIN IMAGE LOG BTAG_MODE PRIMARY_VERTEX_POLICY KEY4HEP_RELEASE CAMPAIGN_SHA256
export BTAG_CHECKER_SHA256

phase_a_rc=0
xargs -r -P "$PAR" -n 1 bash -c 'build_intermediate "$1"' batch_94c \
  < "$ROOT/al.run" || phase_a_rc=$?

validate_intermediates () {
  local -A allowed=() selected_set=()
  local alseq path marker name failures=0 selected_complete=0 cached_complete=0
  while IFS= read -r alseq; do
    [[ -n $alseq ]] || continue
    allowed["inter_${alseq}.root"]=1
    allowed["inter_${alseq}.root.complete"]=1
  done < "$ROOT/al.all"
  while IFS= read -r alseq; do
    [[ -n $alseq ]] || continue
    selected_set["$alseq"]=1
  done < "$ROOT/al.run"

  # Validate every selected product and every previously cached product that is
  # part of the full immutable worklist. This permits prefix resumption without
  # treating valid work from a previous, larger prefix as an unexpected extra.
  while IFS= read -r alseq; do
    [[ -n $alseq ]] || continue
    path=$INT/inter_${alseq}.root
    marker=${path}.complete
    if [[ -n ${selected_set[$alseq]+present} || -e $path || -L $path || \
          -e $marker || -L $marker ]]; then
      if validate_or_upgrade_completion "$path" "$marker" \
          "$LOG/A_$alseq.log" A "$alseq" \
          "$LOG/A_${alseq}.sdst.validation.log"; then
        if [[ -n ${selected_set[$alseq]+present} ]]; then
          selected_complete=$((selected_complete + 1))
        else
          cached_complete=$((cached_complete + 1))
        fi
      else
        echo "ERROR: invalid Phase-A product/marker pair: $path" >&2
        failures=$((failures + 1))
      fi
    fi
  done < "$ROOT/al.all"

  shopt -s nullglob
  for path in "$INT"/inter_*.root "$INT"/inter_*.root.complete; do
    name=${path##*/}
    if [[ -z ${allowed[$name]+present} ]]; then
      echo "ERROR: unexpected Phase-A product: $path" >&2
      failures=$((failures + 1))
    fi
  done
  shopt -u nullglob

  printf 'Phase-A inventory: selected=%d selected_complete=%d cached_complete=%d allowed=%d\n' \
    "$(wc -l < "$ROOT/al.run")" "$selected_complete" "$cached_complete" \
    "$(wc -l < "$ROOT/al.all")"
  ((failures == 0))
}

validate_intermediates || phase_a_rc=1
if ((phase_a_rc != 0)); then
  echo "ERROR: Phase A did not produce a valid selected intermediate set" >&2
  exit 1
fi

if [ "$PHASE" = sdst ]; then
  echo "=== SDST PHASE DONE: $(find "$INT" -maxdepth 1 -name 'inter_*.root.complete' | wc -l) complete intermediates in $INT ==="
  du -sh "$INT" 2>/dev/null
  exit 0
fi

# ---------- Phase B: per run reco + pass2 -> EDM4hep ----------
echo "=== Phase B: $N runs -> EDM4hep (par=$PAR) ==="
awk '{print "run" $2 "_" $1 ".edm4hep.root"}' "$WORKLIST" > "$ROOT/outputs.all"
awk '{print "run" $2 "_" $1 ".edm4hep.root"}' "$ROOT/worklist.run" \
  > "$ROOT/outputs.run"
do_run () {
  local edseq=$1 run=$2 altapes=$3      # ED0151.18 44249 Y13709.41,Y13709.42
  local out=$EDM/run${run}_${edseq}.edm4hep.root
  local done=$out.complete
  local tag=${edseq//./_}                # unique per segment (run may span many)
  local pass2_log=$LOG/B_${tag}_pass2.log
  local sdst_check=$LOG/B_${tag}.sdst.validation.log
  local fdst_check=$LOG/B_${tag}.fdst.validation.log
  local item=${edseq}:${run}
  if [[ -e $out || -L $out ]]; then
    if validate_or_upgrade_completion "$out" "$done" "$pass2_log" \
        B "$item" "$sdst_check" "$fdst_check"; then
      echo "skip run$run ($edseq; validated cached product)"
      return 0
    fi
    echo "FAIL run$run (cached product lacks valid completion evidence)" >&2
    return 1
  fi
  if [[ -e $done || -L $done ]]; then
    echo "FAIL run$run (marker exists without its product: $done)" >&2
    return 1
  fi
  # A run's official short-DST events are split across several .al tapes -> pass
  # the UNION of their intermediates to pass2, else segments whose events live in
  # a non-listed tape match 0 and write an empty (metadata-only) file. (Requires
  # delphi_fdst_pass built with comma-separated-intermediate support, pr-1.)
  local inter="" t
  local -a tape_list=()
  IFS=',' read -r -a tape_list <<< "$altapes"
  for t in "${tape_list[@]}"; do
    [[ -s $INT/inter_${t}.root && ! -L $INT/inter_${t}.root && \
       -f $INT/inter_${t}.root.complete && ! -L $INT/inter_${t}.root.complete ]] \
      || { echo "no complete intermediate for run$run ($t)" >&2; return 1; }
    inter="$inter,$INT/inter_${t}.root"
  done
  inter=${inter#,}
  local vid=${edseq%%.*}
  local raw=$RAWBASE/$vid/$edseq.sl
  [[ -f $raw && ! -L $raw ]] || { echo "MISSING raw $raw" >&2; return 1; }
  local w=$SCR/B_${tag}.${BASHPID}
  local tmp=$EDM/.run${run}_${edseq}.${BASHPID}.tmp.root
  local rc=0
  mkdir -p "$w" || return 1
  # 1. reco -> full DST
  RECO_TIMEOUT=600 MBLIMI=4000 SHORTDST=0 IMAGE=$IMAGE "$RECO" "$raw" "b$tag" "$w" 4000 94c > "$LOG/B_${tag}_reco.log" 2>&1
  rc=$?
  if ((rc != 0)); then
    echo "FAIL reco run$run ($edseq; exit $rc)" >&2
    rm -rf -- "$w"
    return "$rc"
  fi
  local dst=$w/b${tag}_delana.dst
  if [[ ! -s $dst ]]; then
    echo "FAIL reco run$run ($edseq; no nonempty full DST)" >&2
    rm -rf -- "$w"
    return 1
  fi
  # 2. pass2 -> EDM4hep
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$w:$w" --bind "$INT:$INT" --bind "$EDM:$EDM" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
      set -eo pipefail
      set +u
      source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      cd -- "$2"
      exec /edmbin/delphi_fdst_pass "$3" "$4" "$5" -n 20000 --btag "$6"
    ' batch_94c "$KEY4HEP_RELEASE" "$w" "$inter" "$dst" "$tmp" "$BTAG_MODE" \
    > "$pass2_log" 2>&1 || rc=$?
  if ((rc == 0)) && [[ -s $tmp ]]; then
    if positive_harness_count "$pass2_log" >/dev/null &&
       mv -- "$tmp" "$out" &&
       validate_or_upgrade_completion "$out" "$done" "$pass2_log" \
         B "$item" "$sdst_check" "$fdst_check"; then
      echo "OK run$run ($edseq)"
    else
      rc=1
    fi
  else
    ((rc != 0)) || rc=1
  fi
  if ((rc != 0)); then
    echo "FAIL pass2 run$run ($edseq; exit $rc)" >&2
    rm -f -- "$tmp"
  fi
  rm -rf -- "$w"                            # delete the full DST + scratch
  return "$rc"
}
export -f do_run
export EDM INT SCR RAWBASE RECO IMAGE EDMBIN LOG BTAG_MODE PRIMARY_VERTEX_POLICY KEY4HEP_RELEASE
phase_b_rc=0
xargs -r -P "$PAR" -L 1 bash -c 'do_run "$@"' batch_94c \
  < "$ROOT/worklist.run" || phase_b_rc=$?

validate_outputs () {
  local -A allowed=() selected_set=()
  local edseq run _ output_name path marker tag item name failures=0
  local selected_complete=0 cached_complete=0
  while IFS= read -r name; do
    [[ -n $name ]] || continue
    allowed["$name"]=1
    allowed["$name.complete"]=1
  done < "$ROOT/outputs.all"
  while IFS= read -r name; do
    [[ -n $name ]] || continue
    selected_set["$name"]=1
  done < "$ROOT/outputs.run"

  while read -r edseq run _; do
    output_name=run${run}_${edseq}.edm4hep.root
    path=$EDM/$output_name
    marker=${path}.complete
    if [[ -n ${selected_set[$output_name]+present} || -e $path || -L $path || \
          -e $marker || -L $marker ]]; then
      tag=${edseq//./_}
      item=${edseq}:${run}
      if validate_or_upgrade_completion "$path" "$marker" \
          "$LOG/B_${tag}_pass2.log" B "$item" \
          "$LOG/B_${tag}.sdst.validation.log" \
          "$LOG/B_${tag}.fdst.validation.log"; then
        if [[ -n ${selected_set[$output_name]+present} ]]; then
          selected_complete=$((selected_complete + 1))
        else
          cached_complete=$((cached_complete + 1))
        fi
      else
        echo "ERROR: invalid Phase-B product/marker pair: $path" >&2
        failures=$((failures + 1))
      fi
    fi
  done < "$WORKLIST"

  shopt -s nullglob
  for path in "$EDM"/run*.edm4hep.root "$EDM"/run*.edm4hep.root.complete; do
    name=${path##*/}
    if [[ -z ${allowed[$name]+present} ]]; then
      echo "ERROR: unexpected Phase-B product: $path" >&2
      failures=$((failures + 1))
    fi
  done
  shopt -u nullglob

  printf 'Phase-B inventory: selected=%d selected_complete=%d cached_complete=%d allowed=%d\n' \
    "$(wc -l < "$ROOT/outputs.run")" "$selected_complete" "$cached_complete" \
    "$(wc -l < "$ROOT/outputs.all")"
  ((failures == 0))
}

validate_outputs || phase_b_rc=1

if ((phase_b_rc != 0)); then
  echo "ERROR: Phase B did not complete every selected worklist row" >&2
  exit 1
fi

echo "=== BATCH DONE: $N selected EDM4hep files are complete in $EDM ==="
du -sh "$EDM" 2>/dev/null
