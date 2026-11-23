#!/usr/bin/env bash
# Exact, resumable conversion of the official 1994 leptonic LONG-DST stream
# lolept94_c2 (Y13718.1.al .. Y13718.132.al). Each input is used directly for
# both passes; inputs are never copied into the campaign.

set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: batch_leptonic_long_94c.sh [options]

  -o, --output-dir DIR  Campaign directory
  -j, --jobs N          Parallel tapes, 1..8 (default: 3)
      --source-base DIR Official Y13718 directory
      --manifest FILE   Exact audited two-column input inventory
      --image PATH      Singularity image/directory
      --edmbin DIR      Converter/checker build directory
      --key4hep TAG     Key4hep release (default: 2026-04-08)
      --dry-run          Validate the complete inventory and runtime only
  -h, --help             Show help

Production is fixed to recalculated AABTAG; there is no bank/off option. A
final file is complete only after the current checker proves positive equal
event counts and exact ordered (run,event,fileSeq) identity to its pass-1
intermediate, and audit_lepton_pid.py passes its schema/relation checks.
Existing products are revalidated on resume.
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
need_value() { [[ $# -ge 2 && -n $2 ]] || die "$1 requires a value"; }

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
OUTPUT_DIR=${OUTPUT_DIR:-$REPO_ROOT/reruns/lepton94c/lolept94_c2_recalc_full}
JOBS=${JOBS:-3}
SOURCE_BASE=${SOURCE_BASE:-/eos/experiment/delphi/castor2015/tape/Y13718}
MANIFEST=${MANIFEST:-$SCRIPT_DIR/leptonic_long_94c_y13718.manifest.tsv}
IMAGE=${IMAGE:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el9:x86_64}
EDMBIN=${EDMBIN:-$REPO_ROOT/build}
KEY4HEP_RELEASE=${KEY4HEP_RELEASE:-2026-04-08}
AUDITOR=$SCRIPT_DIR/audit_lepton_pid.py
DRY_RUN=0
PRIMARY_VERTEX_POLICY=keep-delana
readonly PRIMARY_VERTEX_POLICY

EXPECTED_FILES=132
EXPECTED_INPUT_BYTES=12076784640
# Full-payload scan of the exact 132-file manifest.  The CERN catalog record
# remains useful provenance, but is not the payload acceptance count: the
# files contain 2,151 more event occurrences, all unique by the full
# (run,event,fileSeq) identity.
EXPECTED_EVENTS=831002
CATALOG_EVENTS=828851
CATALOG_EVENT_DISCREPANCY=2151
EXPECTED_MANIFEST_SHA256=68096b0346f93f4952c5a119b7cfe28858882b6947a1da1f6773198add02c54b

while (($#)); do
  case $1 in
    -o|--output-dir) need_value "$@"; OUTPUT_DIR=$2; shift 2 ;;
    --output-dir=*) OUTPUT_DIR=${1#*=}; [[ -n $OUTPUT_DIR ]] || die 'empty output-dir'; shift ;;
    -j|--jobs) need_value "$@"; JOBS=$2; shift 2 ;;
    --jobs=*) JOBS=${1#*=}; [[ -n $JOBS ]] || die 'empty jobs'; shift ;;
    --source-base) need_value "$@"; SOURCE_BASE=$2; shift 2 ;;
    --source-base=*) SOURCE_BASE=${1#*=}; [[ -n $SOURCE_BASE ]] || die 'empty source-base'; shift ;;
    --manifest) need_value "$@"; MANIFEST=$2; shift 2 ;;
    --manifest=*) MANIFEST=${1#*=}; [[ -n $MANIFEST ]] || die 'empty manifest'; shift ;;
    --image) need_value "$@"; IMAGE=$2; shift 2 ;;
    --image=*) IMAGE=${1#*=}; [[ -n $IMAGE ]] || die 'empty image'; shift ;;
    --edmbin) need_value "$@"; EDMBIN=$2; shift 2 ;;
    --edmbin=*) EDMBIN=${1#*=}; [[ -n $EDMBIN ]] || die 'empty edmbin'; shift ;;
    --key4hep) need_value "$@"; KEY4HEP_RELEASE=$2; shift 2 ;;
    --key4hep=*) KEY4HEP_RELEASE=${1#*=}; [[ -n $KEY4HEP_RELEASE ]] || die 'empty key4hep'; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ $JOBS =~ ^[1-8]$ ]] || die "jobs must be in 1..8 (got: $JOBS)"
for command in realpath sha256sum stat awk xargs flock singularity python3; do
  command -v "$command" >/dev/null 2>&1 || die "$command is not available on PATH"
done
[[ -f $MANIFEST && ! -L $MANIFEST ]] || die "manifest is not a regular file: $MANIFEST"
[[ -d $SOURCE_BASE ]] || die "source directory not found: $SOURCE_BASE"
[[ -e $IMAGE ]] || die "Singularity image/directory not found: $IMAGE"
[[ -d $EDMBIN ]] || die "converter build directory not found: $EDMBIN"
[[ -f $AUDITOR && ! -L $AUDITOR ]] || die "lepton auditor not found: $AUDITOR"
for binary in delphi_sdst_pass delphi_fdst_pass delphi_btag_check; do
  [[ -x $EDMBIN/$binary && ! -L $EDMBIN/$binary ]] || \
    die "required regular executable not found: $EDMBIN/$binary"
done

MANIFEST=$(realpath -- "$MANIFEST")
SOURCE_BASE=$(realpath -- "$SOURCE_BASE")
EDMBIN=$(realpath -- "$EDMBIN")
AUDITOR=$(realpath -- "$AUDITOR")
OUTPUT_DIR=$(realpath -m -- "$OUTPUT_DIR")
[[ $OUTPUT_DIR != / ]] || die 'refusing to use / as output-dir'
[[ $OUTPUT_DIR != "$SOURCE_BASE" ]] || die 'output-dir must differ from source-base'

MANIFEST_SHA256=$(sha256sum -- "$MANIFEST" | awk '{print $1}')
[[ $MANIFEST_SHA256 == "$EXPECTED_MANIFEST_SHA256" ]] || \
  die "manifest SHA-256 is not the audited lolept94_c2 inventory: $MANIFEST_SHA256"

rows=0
input_bytes=0
while IFS=$'\t' read -r filename expected_size extra; do
  rows=$((rows + 1))
  [[ -z ${extra:-} && $filename == "Y13718.${rows}.al" && \
     $expected_size =~ ^[1-9][0-9]*$ ]] || die "invalid/out-of-order manifest row $rows"
  input=$SOURCE_BASE/$filename
  [[ -f $input && ! -L $input ]] || die "official input not found: $input"
  actual_size=$(stat -c %s -- "$input")
  [[ $actual_size == "$expected_size" ]] || \
    die "input size mismatch for $filename: expected $expected_size, got $actual_size"
  input_bytes=$((input_bytes + expected_size))
done <"$MANIFEST"
[[ $rows -eq $EXPECTED_FILES ]] || die "manifest has $rows rows, expected $EXPECTED_FILES"
[[ $input_bytes -eq $EXPECTED_INPUT_BYTES ]] || \
  die "manifest totals $input_bytes bytes, expected $EXPECTED_INPUT_BYTES"

SDST_SHA256=$(sha256sum -- "$EDMBIN/delphi_sdst_pass" | awk '{print $1}')
FDST_SHA256=$(sha256sum -- "$EDMBIN/delphi_fdst_pass" | awk '{print $1}')
CHECKER_SHA256=$(sha256sum -- "$EDMBIN/delphi_btag_check" | awk '{print $1}')
AUDITOR_SHA256=$(sha256sum -- "$AUDITOR" | awk '{print $1}')

if ((DRY_RUN)); then
  printf 'status=PASS action=dry-run dataset=lolept94_c2 files=%d input_bytes=%d expected_events=%d catalog_events=%d catalog_event_discrepancy=%d btag_mode=recalc jobs=%d\n' \
    "$rows" "$input_bytes" "$EXPECTED_EVENTS" "$CATALOG_EVENTS" \
    "$CATALOG_EVENT_DISCREPANCY" "$JOBS"
  printf 'manifest=%s\nmanifest_sha256=%s\nsource_base=%s\noutput_dir=%s\n' \
    "$MANIFEST" "$MANIFEST_SHA256" "$SOURCE_BASE" "$OUTPUT_DIR"
  printf 'first=Y13718.1.al last=Y13718.132.al input_copy_policy=direct-read-only\n'
  exit 0
fi

mkdir -p -- "$OUTPUT_DIR"
INT_DIR=$OUTPUT_DIR/intermediates
FINAL_DIR=$OUTPUT_DIR/edm4hep
LOG_DIR=$OUTPUT_DIR/logs
AUDIT_DIR=$OUTPUT_DIR/audits
SCRATCH_DIR=$OUTPUT_DIR/.scratch
LOCK_DIR=$OUTPUT_DIR/.locks
mkdir -p -- "$INT_DIR" "$FINAL_DIR" "$LOG_DIR" "$AUDIT_DIR" "$SCRATCH_DIR" "$LOCK_DIR"

exec {campaign_lock_fd}>"$OUTPUT_DIR/.campaign.lock"
flock -n "$campaign_lock_fd" || die "campaign is already active: $OUTPUT_DIR"

config_tmp=$(mktemp --tmpdir="$OUTPUT_DIR" .campaign.conf.XXXXXX.tmp)
trap 'rm -f -- "$config_tmp"' EXIT
{
  printf 'format=delphi-lolept94-c2-recalc-v2\n'
  printf 'dataset=lolept94_c2\nbtag_mode=recalc\nrecalculated=1\n'
  printf 'primary_vertex_policy=%s\n' "$PRIMARY_VERTEX_POLICY"
  printf 'file_count=%d\ninput_bytes=%d\nexpected_events=%d\n' \
    "$EXPECTED_FILES" "$EXPECTED_INPUT_BYTES" "$EXPECTED_EVENTS"
  printf 'catalog_events=%d\ncatalog_event_discrepancy=%d\n' \
    "$CATALOG_EVENTS" "$CATALOG_EVENT_DISCREPANCY"
  printf 'manifest_sha256=%s\nsource_base=%s\n' "$MANIFEST_SHA256" "$SOURCE_BASE"
  printf 'key4hep_release=%s\nimage=%s\n' "$KEY4HEP_RELEASE" "$IMAGE"
  printf 'sdst_binary_sha256=%s\nfdst_binary_sha256=%s\n' "$SDST_SHA256" "$FDST_SHA256"
  printf 'checker_sha256=%s\nauditor_sha256=%s\n' "$CHECKER_SHA256" "$AUDITOR_SHA256"
  printf 'input_copy_policy=direct-read-only\n'
} >"$config_tmp"
if [[ -e $OUTPUT_DIR/campaign.conf || -L $OUTPUT_DIR/campaign.conf ]]; then
  [[ -f $OUTPUT_DIR/campaign.conf && ! -L $OUTPUT_DIR/campaign.conf ]] || die 'campaign.conf is not a regular file'
  cmp -s -- "$config_tmp" "$OUTPUT_DIR/campaign.conf" || die "campaign configuration mismatch: $OUTPUT_DIR/campaign.conf"
  rm -f -- "$config_tmp"
else
  shopt -s nullglob
  unbound=("$INT_DIR"/*.root "$INT_DIR"/*.complete "$FINAL_DIR"/*.root "$FINAL_DIR"/*.complete)
  shopt -u nullglob
  ((${#unbound[@]} == 0)) || die 'unbound products exist without campaign.conf; use a fresh output-dir'
  mv -- "$config_tmp" "$OUTPUT_DIR/campaign.conf"
fi
trap - EXIT
CAMPAIGN_SHA256=$(sha256sum -- "$OUTPUT_DIR/campaign.conf" | awk '{print $1}')
if [[ -e $OUTPUT_DIR/inputs.manifest.tsv || -L $OUTPUT_DIR/inputs.manifest.tsv ]]; then
  [[ -f $OUTPUT_DIR/inputs.manifest.tsv && ! -L $OUTPUT_DIR/inputs.manifest.tsv ]] || die 'campaign manifest copy is not a regular file'
  cmp -s -- "$MANIFEST" "$OUTPUT_DIR/inputs.manifest.tsv" || die 'campaign manifest copy differs'
else
  cp -- "$MANIFEST" "$OUTPUT_DIR/inputs.manifest.tsv"
fi

checker_events() {
  local log=$1 source=$2 line summary= matches=0 entries=
  [[ -f $log && ! -L $log ]] || return 1
  while IFS= read -r line; do
    [[ $line == status=* ]] && { summary=$line; matches=$((matches + 1)); }
  done <"$log"
  ((matches == 1)) || return 1
  [[ $summary == status=PASS* && $summary == *' btag_mode=recalc '* && \
     $summary == *" source=$source "* && \
     $summary == *' identity_source=sDST_EVT '* && \
     $summary == *' recalculated_expected=1 '* && \
     $summary == *' provenance_schema=source-local-v1 '* && \
     $summary == *" primary_vertex_policy=$PRIMARY_VERTEX_POLICY "* && \
     $summary == *" primary_vertex_policy_expected=$PRIMARY_VERTEX_POLICY "* && \
     $summary == *' iflpvt=0 '* && \
     $summary == *' primary_vertex_policy_failures=0 '* && \
     $summary == *' failures=0 '* ]] || return 1
  [[ $summary =~ (^|[[:space:]])entries=([0-9]+)($|[[:space:]]) ]] || return 1
  entries=$((10#${BASH_REMATCH[2]})); ((entries > 0)) || return 1
  printf '%d\n' "$entries"
}

run_checker() {
  local candidate=$1 source=$2 reference=$3 log=$4
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$OUTPUT_DIR:$OUTPUT_DIR" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
      set +u; set -eo pipefail
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      if [[ -n "$4" ]]; then
        exec /edmbin/delphi_btag_check --source "$3" \
          --primary-vertex-policy "$5" "$2" data recalc "$4"
      fi
      exec /edmbin/delphi_btag_check --source "$3" \
        --primary-vertex-policy "$5" "$2" data recalc
    ' batch_leptonic_long_94c "$KEY4HEP_RELEASE" "$candidate" "$source" \
      "$reference" "$PRIMARY_VERTEX_POLICY" >"$log" 2>&1
}

run_lepton_audit() {
  local candidate=$1 json=$2 log=$3
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$OUTPUT_DIR:$OUTPUT_DIR" --bind "$SCRIPT_DIR:$SCRIPT_DIR:ro" "$IMAGE" bash -c '
      set +u; set -eo pipefail
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      exec python3 "$2" "$3" --output "$4"
    ' batch_leptonic_long_94c "$KEY4HEP_RELEASE" "$AUDITOR" "$candidate" "$json" >"$log" 2>&1
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); raise SystemExit(0 if d.get("status")=="PASS" else 1)' "$json"
}

write_marker() {
  local marker=$1 phase=$2 tape=$3 input_size=$4 output=$5 events=$6
  local sdst_check_log=$7 fdst_check_log=${8:-} audit_json=${9:-}
  local tmp audit_sha=not-run identity=not-applicable output_sha
  [[ -z $audit_json ]] || audit_sha=$(sha256sum -- "$audit_json" | awk '{print $1}')
  [[ $phase != final ]] || identity=exact-ordered-run-event-fileSeq
  output_sha=$(sha256sum -- "$output" | awk '{print $1}')
  tmp=$(mktemp --tmpdir="${marker%/*}" ".${marker##*/}.XXXXXX.tmp")
  {
    printf 'format=delphi-lolept94-c2-complete-v2\nphase=%s\ntape=%s\n' "$phase" "$tape"
    printf 'input_size_bytes=%s\noutput=%s\noutput_size_bytes=%s\noutput_sha256=%s\nevents=%s\n' \
      "$input_size" "${output##*/}" "$(stat -c %s -- "$output")" \
      "$output_sha" "$events"
    printf 'btag_mode=recalc\nrecalculated=1\nprimary_vertex_policy=%s\nidentity_check=%s\n' \
      "$PRIMARY_VERTEX_POLICY" "$identity"
    printf 'lepton_schema_audit_sha256=%s\nchecker_sha256=%s\nauditor_sha256=%s\n' \
      "$audit_sha" "$CHECKER_SHA256" "$AUDITOR_SHA256"
    printf 'campaign_sha256=%s\nsdst_validation=%s\n' \
      "$CAMPAIGN_SHA256" "$(grep '^status=' "$sdst_check_log")"
    if [[ -n $fdst_check_log ]]; then
      printf 'fdst_validation=%s\n' "$(grep '^status=' "$fdst_check_log")"
    else
      printf 'fdst_validation=not-applicable\n'
    fi
  } >"$tmp"
  mv -f -- "$tmp" "$marker"
}

convert_one() {
  local filename=$1 expected_size=$2
  local tape=${filename%.al} input=$SOURCE_BASE/$filename
  local inter=$INT_DIR/inter_${tape}.root inter_marker=$INT_DIR/inter_${tape}.root.complete
  local final=$FINAL_DIR/lolept94_c2_${tape}.edm4hep.root
  local final_marker=${final}.complete
  local pass1_log=$LOG_DIR/${tape}.pass1.log
  local pass1_check=$LOG_DIR/${tape}.pass1.sdst.validation.log
  local pass2_log=$LOG_DIR/${tape}.pass2.log
  local final_sdst_check=$LOG_DIR/${tape}.final.sdst.validation.log
  local final_fdst_check=$LOG_DIR/${tape}.final.fdst.validation.log
  local audit_json=$AUDIT_DIR/${tape}.lepton_pid.json audit_log=$LOG_DIR/${tape}.lepton_pid.log
  local lock=$LOCK_DIR/${tape}.lock lock_fd rc=0 inter_events final_events fdst_events
  # These must outlive the function for the worker shell's EXIT trap. Bash
  # removes local variables before running that trap after a failed function.
  work=
  tmp=
  exec {lock_fd}>"$lock"; flock "$lock_fd"
  [[ -f $input && ! -L $input && $(stat -c %s -- "$input") == "$expected_size" ]] || {
    printf 'FAIL %s (input changed after preflight)\n' "$tape" >&2; return 1;
  }

  if [[ -e $inter || -L $inter ]]; then
    rm -f -- "$inter_marker"
    [[ -s $inter && -f $inter && ! -L $inter ]] || { printf 'FAIL %s (invalid existing intermediate)\n' "$tape" >&2; return 1; }
    run_checker "$inter" sDST '' "$pass1_check" || { printf 'FAIL %s (existing intermediate recalc check)\n' "$tape" >&2; return 1; }
    inter_events=$(checker_events "$pass1_check" sDST) || return 1
    write_marker "$inter_marker" intermediate "$tape" "$expected_size" "$inter" "$inter_events" "$pass1_check"
  else
    rm -f -- "$inter_marker"
    work=$(mktemp -d --tmpdir="$SCRATCH_DIR" "${tape}.pass1.XXXXXX")
    tmp=$(mktemp --tmpdir="$INT_DIR" ".inter_${tape}.XXXXXX.tmp.root")
    trap 'rm -f -- "$tmp"; rm -rf -- "$work"' EXIT INT TERM
    singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
      --bind "$SOURCE_BASE:$SOURCE_BASE:ro" --bind "$OUTPUT_DIR:$OUTPUT_DIR" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
        set +u; set -eo pipefail
        source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
        source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
        export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
        cd -- "$2"; exec /edmbin/delphi_sdst_pass "$3" "$4" --btag recalc
      ' batch_leptonic_long_94c "$KEY4HEP_RELEASE" "$work" "$input" "$tmp" >"$pass1_log" 2>&1 || rc=$?
    if ((rc != 0)) || [[ ! -s $tmp ]]; then printf 'FAIL %s (pass1 exit=%d; log=%s)\n' "$tape" "$rc" "$pass1_log" >&2; return 1; fi
    run_checker "$tmp" sDST '' "$pass1_check" || { printf 'FAIL %s (pass1 recalc check)\n' "$tape" >&2; return 1; }
    inter_events=$(checker_events "$pass1_check" sDST) || return 1
    mv -- "$tmp" "$inter"
    write_marker "$inter_marker" intermediate "$tape" "$expected_size" "$inter" "$inter_events" "$pass1_check"
    rm -rf -- "$work"; trap - EXIT INT TERM
  fi

  if [[ -e $final || -L $final ]]; then
    rm -f -- "$final_marker"
    [[ -s $final && -f $final && ! -L $final ]] || { printf 'FAIL %s (invalid existing final)\n' "$tape" >&2; return 1; }
    run_checker "$final" sDST "$inter" "$final_sdst_check" || { printf 'FAIL %s (existing final sDST identity/recalc check)\n' "$tape" >&2; return 1; }
    final_events=$(checker_events "$final_sdst_check" sDST) || return 1
    [[ $final_events == "$inter_events" ]] || return 1
    run_checker "$final" fDST '' "$final_fdst_check" || { printf 'FAIL %s (existing final fDST content/recalc check)\n' "$tape" >&2; return 1; }
    fdst_events=$(checker_events "$final_fdst_check" fDST) || return 1
    [[ $fdst_events == "$final_events" ]] || return 1
    run_lepton_audit "$final" "$audit_json" "$audit_log" || { printf 'FAIL %s (existing final lepton schema audit)\n' "$tape" >&2; return 1; }
    write_marker "$final_marker" final "$tape" "$expected_size" "$final" \
      "$final_events" "$final_sdst_check" "$final_fdst_check" "$audit_json"
    printf 'SKIP %s (revalidated events=%s)\n' "$tape" "$final_events"; return 0
  fi

  rm -f -- "$final_marker"
  work=$(mktemp -d --tmpdir="$SCRATCH_DIR" "${tape}.pass2.XXXXXX")
  tmp=$(mktemp --tmpdir="$FINAL_DIR" ".lolept94_c2_${tape}.XXXXXX.tmp.root")
  trap 'rm -f -- "$tmp"; rm -rf -- "$work"' EXIT INT TERM
  rc=0
  singularity exec --cleanenv --bind /cvmfs --bind /lib64:/host_lib64:ro \
    --bind "$SOURCE_BASE:$SOURCE_BASE:ro" --bind "$OUTPUT_DIR:$OUTPUT_DIR" --bind "$EDMBIN:/edmbin:ro" "$IMAGE" bash -c '
      set +u; set -eo pipefail
      source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
      source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
      export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
      cd -- "$2"; exec /edmbin/delphi_fdst_pass "$3" "$4" "$5" --btag recalc
    ' batch_leptonic_long_94c "$KEY4HEP_RELEASE" "$work" "$inter" "$input" "$tmp" >"$pass2_log" 2>&1 || rc=$?
  if ((rc != 0)) || [[ ! -s $tmp ]]; then printf 'FAIL %s (pass2 exit=%d; log=%s)\n' "$tape" "$rc" "$pass2_log" >&2; return 1; fi
  run_checker "$tmp" sDST "$inter" "$final_sdst_check" || { printf 'FAIL %s (final sDST identity/recalc check)\n' "$tape" >&2; return 1; }
  final_events=$(checker_events "$final_sdst_check" sDST) || return 1
  [[ $final_events == "$inter_events" ]] || return 1
  run_checker "$tmp" fDST '' "$final_fdst_check" || { printf 'FAIL %s (final fDST content/recalc check)\n' "$tape" >&2; return 1; }
  fdst_events=$(checker_events "$final_fdst_check" fDST) || return 1
  [[ $fdst_events == "$final_events" ]] || return 1
  run_lepton_audit "$tmp" "$audit_json" "$audit_log" || { printf 'FAIL %s (final lepton schema audit)\n' "$tape" >&2; return 1; }
  mv -- "$tmp" "$final"
  write_marker "$final_marker" final "$tape" "$expected_size" "$final" \
    "$final_events" "$final_sdst_check" "$final_fdst_check" "$audit_json"
  rm -rf -- "$work"; trap - EXIT INT TERM
  printf 'OK   %s events=%s\n' "$tape" "$final_events"
}

export -f checker_events run_checker run_lepton_audit write_marker convert_one
export SOURCE_BASE OUTPUT_DIR INT_DIR FINAL_DIR LOG_DIR AUDIT_DIR SCRATCH_DIR LOCK_DIR
export IMAGE EDMBIN SCRIPT_DIR AUDITOR KEY4HEP_RELEASE PRIMARY_VERTEX_POLICY CHECKER_SHA256 AUDITOR_SHA256 CAMPAIGN_SHA256

batch_rc=0
while IFS=$'\t' read -r filename expected_size; do printf '%s\0%s\0' "$filename" "$expected_size"; done <"$MANIFEST" | \
  xargs -0 -r -n 2 -P "$JOBS" bash -c 'set -Eeuo pipefail; convert_one "$1" "$2"' batch_leptonic_long_94c || batch_rc=$?

complete=0
total_events=0
inventory_failures=0
while IFS=$'\t' read -r filename _; do
  tape=${filename%.al}
  inter=$INT_DIR/inter_${tape}.root
  final=$FINAL_DIR/lolept94_c2_${tape}.edm4hep.root
  marker=${final}.complete
  if [[ -s $inter && -f ${inter}.complete && -s $final && -f $marker ]]; then
    event_lines=$(awk -F= '$1=="events" {print $2}' "$marker")
    [[ $event_lines =~ ^[1-9][0-9]*$ ]] || { inventory_failures=$((inventory_failures + 1)); continue; }
    complete=$((complete + 1)); total_events=$((total_events + event_lines))
  else
    inventory_failures=$((inventory_failures + 1))
  fi
done <"$MANIFEST"

printf 'selected=%d complete=%d events=%d expected_events=%d btag_mode=recalc output=%s\n' \
  "$EXPECTED_FILES" "$complete" "$total_events" "$EXPECTED_EVENTS" "$OUTPUT_DIR"
if ((batch_rc != 0 || inventory_failures != 0 || complete != EXPECTED_FILES || total_events != EXPECTED_EVENTS)); then exit 1; fi
printf 'status=PASS dataset=lolept94_c2 files=%d events=%d\n' "$complete" "$total_events"
