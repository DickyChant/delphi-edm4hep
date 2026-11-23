#!/usr/bin/env bash
# Convert selected official DELPHI v94c qqps SDST MC files to EDM4hep.
#
# No IDs are selected by default: callers must give an explicit range/list.
# Each output is written beside its final destination under a unique temporary
# name, scanned event-by-event for run/mode/b-tag integrity, and then atomically
# renamed. A validated *.complete marker makes subsequent invocations resume.

set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage:
  batch_sdst_mc.sh [options] ID_SPEC [ID_SPEC ...]

ID_SPEC is a single numeric file ID, an inclusive range, or a comma-separated
mixture, for example 21000, 21002-21004, or 21000-21004,21010.

Options:
  -o, --output-dir DIR  Output directory
  -j, --jobs N          Number of parallel conversions (default: 1)
      --btag-mode MODE  Compatibility spelling; only recalc is accepted
      --ids ID_SPEC     Add an ID specification (may be repeated)
      --source-dir DIR  Official SDST directory
      --image PATH      Singularity image/directory
      --edmbin DIR      Directory containing delphi_sdst_pass
      --key4hep TAG     Key4hep release tag (default: 2026-04-08)
      --dry-run         Validate and print exact input/output paths only
  -h, --help            Show this help

Defaults may also be set with OUTPUT_DIR, JOBS, SOURCE_DIR, IMAGE, EDMBIN,
and KEY4HEP_RELEASE. BTAG_MODE, when present for compatibility, must be
`recalc`. Outputs are named
qqps_91.25_ID.edm4hep.root; per-file logs live in OUTPUT_DIR/logs and
completion markers end in .root.complete. This production driver always runs
prefix-isolated AABTAG recalculation. Historical stored-bank reproduction is
kept only in explicitly archive-labelled tooling.

Example:
  scripts/data-reco/batch_sdst_mc.sh --jobs 2 21000-21004
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 2
}

need_value() {
    [[ $# -ge 2 && -n $2 ]] || die "$1 requires a value"
}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)

SOURCE_DIR=${SOURCE_DIR:-/eos/opendata/delphi/simulated-data/cern/qqps/v94c/91.25}
OUTPUT_DIR=${OUTPUT_DIR:-}
JOBS=${JOBS:-1}
BTAG_MODE=${BTAG_MODE-recalc}
PRIMARY_VERTEX_POLICY=keep-delana
IMAGE=${IMAGE:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el9:x86_64}
EDMBIN=${EDMBIN:-$REPO_ROOT/build}
KEY4HEP_RELEASE=${KEY4HEP_RELEASE:-2026-04-08}
DRY_RUN=0
ID_SPECS=()

while (($#)); do
    case $1 in
        -o|--output-dir)
            need_value "$@"
            OUTPUT_DIR=$2
            shift 2
            ;;
        --output-dir=*)
            OUTPUT_DIR=${1#*=}
            [[ -n $OUTPUT_DIR ]] || die '--output-dir requires a value'
            shift
            ;;
        -j|--jobs)
            need_value "$@"
            JOBS=$2
            shift 2
            ;;
        --jobs=*)
            JOBS=${1#*=}
            [[ -n $JOBS ]] || die '--jobs requires a value'
            shift
            ;;
        --ids)
            need_value "$@"
            ID_SPECS+=("$2")
            shift 2
            ;;
        --ids=*)
            ID_SPECS+=("${1#*=}")
            shift
            ;;
        --btag-mode)
            need_value "$@"
            BTAG_MODE=$2
            shift 2
            ;;
        --btag-mode=*)
            BTAG_MODE=${1#*=}
            [[ -n $BTAG_MODE ]] || die '--btag-mode requires a value'
            shift
            ;;
        --source-dir)
            need_value "$@"
            SOURCE_DIR=$2
            shift 2
            ;;
        --source-dir=*)
            SOURCE_DIR=${1#*=}
            [[ -n $SOURCE_DIR ]] || die '--source-dir requires a value'
            shift
            ;;
        --image)
            need_value "$@"
            IMAGE=$2
            shift 2
            ;;
        --image=*)
            IMAGE=${1#*=}
            [[ -n $IMAGE ]] || die '--image requires a value'
            shift
            ;;
        --edmbin)
            need_value "$@"
            EDMBIN=$2
            shift 2
            ;;
        --edmbin=*)
            EDMBIN=${1#*=}
            [[ -n $EDMBIN ]] || die '--edmbin requires a value'
            shift
            ;;
        --key4hep)
            need_value "$@"
            KEY4HEP_RELEASE=$2
            shift 2
            ;;
        --key4hep=*)
            KEY4HEP_RELEASE=${1#*=}
            [[ -n $KEY4HEP_RELEASE ]] || die '--key4hep requires a value'
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            ID_SPECS+=("$@")
            break
            ;;
        -*)
            die "unknown option: $1"
            ;;
        *)
            ID_SPECS+=("$1")
            shift
            ;;
    esac
done

[[ $JOBS =~ ^[1-9][0-9]*$ ]] || die "jobs must be a positive integer: $JOBS"
[[ $BTAG_MODE == recalc ]] || \
    die "batch_sdst_mc.sh is recalculated-AABTAG-only; btag mode is not a production option: $BTAG_MODE"
readonly BTAG_MODE
readonly PRIMARY_VERTEX_POLICY
((${#ID_SPECS[@]} > 0)) || die 'at least one explicit ID_SPEC is required'

if [[ -z $OUTPUT_DIR ]]; then
    OUTPUT_DIR=$REPO_ROOT/reruns/btag_recalc/mc/qqps_v94c_91p25
fi

IDS=()
declare -A SEEN_IDS=()

add_id() {
    local raw=$1 id
    [[ $raw =~ ^[0-9]+$ ]] || die "invalid file ID: $raw"
    id=$((10#$raw))
    ((id > 0)) || die "file ID must be positive: $raw"
    if [[ -z ${SEEN_IDS[$id]+present} ]]; then
        SEEN_IDS[$id]=1
        IDS+=("$id")
    fi
}

parse_id_spec() {
    local spec=$1 token start end id
    local -a tokens=()
    IFS=',' read -r -a tokens <<< "$spec"
    ((${#tokens[@]} > 0)) || die "empty ID specification: $spec"
    for token in "${tokens[@]}"; do
        [[ -n $token ]] || die "empty item in ID specification: $spec"
        if [[ $token =~ ^([0-9]+)-([0-9]+)$ ]]; then
            start=$((10#${BASH_REMATCH[1]}))
            end=$((10#${BASH_REMATCH[2]}))
            ((start > 0)) || die "file ID must be positive: $token"
            ((end >= start)) || die "descending ID range is not allowed: $token"
            for ((id = start; id <= end; ++id)); do
                add_id "$id"
            done
        else
            add_id "$token"
        fi
    done
}

for spec in "${ID_SPECS[@]}"; do
    parse_id_spec "$spec"
done

[[ -d $SOURCE_DIR ]] || die "source directory not found: $SOURCE_DIR"
SOURCE_DIR=$(cd -- "$SOURCE_DIR" && pwd -P)

mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(cd -- "$OUTPUT_DIR" && pwd -P)
[[ $OUTPUT_DIR != / ]] || die 'refusing to use / as the output directory'
[[ $OUTPUT_DIR != "$SOURCE_DIR" ]] || die 'output directory must differ from the input directory'
[[ $OUTPUT_DIR != "$SOURCE_DIR"/* ]] || \
    die 'output directory must not be contained by the input directory'
[[ $SOURCE_DIR != "$OUTPUT_DIR"/* ]] || \
    die 'input directory must not be contained by the output directory'

LOG_DIR=$OUTPUT_DIR/logs
SCRATCH_DIR=$OUTPUT_DIR/.scratch
LOCK_DIR=$OUTPUT_DIR/.locks

missing=0
for id in "${IDS[@]}"; do
    input=$SOURCE_DIR/qqps_91.25_${id}.sdst
    if [[ ! -f $input ]]; then
        printf 'ERROR: input not found: %s\n' "$input" >&2
        missing=$((missing + 1))
    fi
done
((missing == 0)) || exit 2

if ((DRY_RUN)); then
    printf 'Validated %d input(s); btag_mode=%s; no conversion started.\n' \
        "${#IDS[@]}" "$BTAG_MODE"
    for id in "${IDS[@]}"; do
        printf '  %s/qqps_91.25_%s.sdst -> %s/qqps_91.25_%s.edm4hep.root\n' \
            "$SOURCE_DIR" "$id" "$OUTPUT_DIR" "$id"
    done
    exit 0
fi

command -v singularity >/dev/null 2>&1 || die 'singularity is not available on PATH'
[[ -e $IMAGE ]] || die "Singularity image not found: $IMAGE"
[[ -d $EDMBIN ]] || die "EDM4hep binary directory not found: $EDMBIN"
EDMBIN=$(cd -- "$EDMBIN" && pwd -P)
[[ -x $EDMBIN/delphi_sdst_pass ]] || die "converter is not executable: $EDMBIN/delphi_sdst_pass"
[[ -x $EDMBIN/delphi_btag_check ]] || die "validator is not executable: $EDMBIN/delphi_btag_check"
command -v flock >/dev/null 2>&1 || die 'flock is not available on PATH'
command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is not available on PATH'
CHECKER_SHA256=$(sha256sum -- "$EDMBIN/delphi_btag_check")
CHECKER_SHA256=${CHECKER_SHA256%% *}
[[ $CHECKER_SHA256 =~ ^[0-9a-f]{64}$ ]] || \
    die "could not hash validator: $EDMBIN/delphi_btag_check"
mkdir -p -- "$LOG_DIR" "$SCRATCH_DIR" "$LOCK_DIR"

run_checker() {
    local path=$1
    local id=$2
    local validation_log=$3

    singularity exec --cleanenv \
        --bind /cvmfs \
        --bind /lib64:/host_lib64:ro \
        --bind "$OUTPUT_DIR:$OUTPUT_DIR" \
        --bind "$EDMBIN:/edmbin:ro" \
        "$IMAGE" bash -c '
            set -eo pipefail
            set +u
            source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
            export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
            exec /edmbin/delphi_btag_check --source sDST \
                --primary-vertex-policy "$5" "$2" "$3" "$4"
        ' batch_sdst_mc "$KEY4HEP_RELEASE" "$path" "-$id" "$BTAG_MODE" \
          "$PRIMARY_VERTEX_POLICY" \
        >"$validation_log" 2>&1
}

write_marker() {
    local marker=$1
    local input=$2
    local id=$3
    local output=$4
    local validation_log=$5
    local marker_tmp
    local size_bytes
    local validated_utc
    local validation_summary
    marker_tmp=$(mktemp --tmpdir="$OUTPUT_DIR" ".$(basename "$marker").XXXXXX.tmp")
    size_bytes=$(stat -c %s -- "$output") || {
        rm -f -- "$marker_tmp"
        return 1
    }
    validated_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ) || {
        rm -f -- "$marker_tmp"
        return 1
    }
    validation_summary=$(tail -n 1 -- "$validation_log") || {
        rm -f -- "$marker_tmp"
        return 1
    }
    [[ $validation_summary == status=PASS* ]] || {
        rm -f -- "$marker_tmp"
        return 1
    }
    [[ $validation_summary == *' source=sDST '* && \
       $validation_summary == *' chi2_pv_contract=attached-only-v1 '* && \
       $validation_summary == *' chi2_pv_roundoff_tolerance=0.25 '* && \
       $validation_summary == *' primary_vertex_policy=keep-delana '* && \
       $validation_summary == *' primary_vertex_policy_expected=keep-delana '* && \
       $validation_summary == *' iflpvt=0 '* && \
       $validation_summary == *' primary_vertex_policy_failures=0 '* ]] || {
        rm -f -- "$marker_tmp"
        return 1
    }
    local counter
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
        [[ " $validation_summary " == *" $counter=0 "* ]] || {
            rm -f -- "$marker_tmp"
            return 1
        }
    done
    if ! {
        printf 'input=%s\n' "$input"
        printf 'run=-%s\n' "$id"
        printf 'btag_mode=%s\n' "$BTAG_MODE"
        printf 'source=sDST\n'
        printf 'primary_vertex_policy=%s\n' "$PRIMARY_VERTEX_POLICY"
        printf 'iflpvt=0\n'
        printf 'recalculated=1\n'
        printf 'size_bytes=%s\n' "$size_bytes"
        printf 'validated_utc=%s\n' "$validated_utc"
        printf 'validation_method=direct_delphi_btag_check\n'
        printf 'checker_sha256=%s\n' "$CHECKER_SHA256"
        printf 'validation=%s\n' "$validation_summary"
    } >"$marker_tmp"; then
        rm -f -- "$marker_tmp"
        return 1
    fi
    if ! mv -f -- "$marker_tmp" "$marker"; then
        rm -f -- "$marker_tmp"
        return 1
    fi
}

convert_one() {
    local id=$1
    local stem=qqps_91.25_${id}
    local input=$SOURCE_DIR/${stem}.sdst
    local output=$OUTPUT_DIR/${stem}.edm4hep.root
    local marker=${output}.complete
    local log=$LOG_DIR/${stem}.log
    local validation_log=$LOG_DIR/${stem}.${BTAG_MODE}.validation.log
    local lock=$LOCK_DIR/${stem}.lock
    local lock_fd

    exec {lock_fd}>"$lock"
    flock "$lock_fd"
    # Recover both old markers (which did not record btag_mode) and the narrow
    # crash window where the atomic output rename succeeded but marker publish
    # did not. Never overwrite an existing output merely because its marker is
    # absent: prove its contents first, or stop for manual quarantine.
    if [[ -e $output || -L $output ]]; then
        # A completion marker is only a claim about the most recent successful
        # scan. Withdraw it before examining the file so a failed recheck can
        # never leave a stale success claim behind.
        rm -f -- "$marker"
        if [[ ! -f $output || -L $output ]]; then
            printf 'FAIL %s (existing output is not a regular file: %s)\n' \
                "$id" "$output" >&2
            return 1
        fi
        if run_checker "$output" "$id" "$validation_log"; then
            write_marker "$marker" "$input" "$id" "$output" "$validation_log"
            printf 'SKIP %s (validated existing output; mode=%s)\n' "$id" "$BTAG_MODE"
            return 0
        fi
        printf 'FAIL %s (existing output failed %s validation; log: %s)\n' \
            "$id" "$BTAG_MODE" "$validation_log" >&2
        return 1
    fi

    [[ -f $input ]] || {
        printf 'FAIL %s (input disappeared: %s)\n' "$id" "$input" >&2
        return 1
    }

    local work
    local tmp
    local cleanup_cmd
    work=$(mktemp -d --tmpdir="$SCRATCH_DIR" "${stem}.XXXXXX")
    tmp=$(mktemp --tmpdir="$OUTPUT_DIR" ".${stem}.XXXXXX.tmp.root")

    # EXIT runs after convert_one has returned, when its local variables are no
    # longer in dynamic scope. Capture shell-escaped literal paths in the trap;
    # referring to $tmp/$work there would trip `set -u` and skip cleanup.
    printf -v cleanup_cmd 'rm -f -- %q; rm -rf -- %q' "$tmp" "$work"
    trap "$cleanup_cmd" EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    rm -f -- "$marker"

    local rc
    if {
        printf 'input=%s\n' "$input"
        printf 'temporary_output=%s\n' "$tmp"
        printf 'btag_mode=%s\n' "$BTAG_MODE"
        printf 'converter=/edmbin/delphi_sdst_pass INPUT OUTPUT --btag %s\n' "$BTAG_MODE"
        singularity exec --cleanenv \
            --bind /cvmfs \
            --bind /lib64:/host_lib64:ro \
            --bind "$SOURCE_DIR:$SOURCE_DIR:ro" \
            --bind "$OUTPUT_DIR:$OUTPUT_DIR" \
            --bind "$EDMBIN:/edmbin:ro" \
            "$IMAGE" bash -c '
                set -eo pipefail
                set +u
                source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
                source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$4" >/dev/null 2>&1
                export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
                cd -- "$1"
                exec /edmbin/delphi_sdst_pass "$2" "$3" --btag "$5"
            ' batch_sdst_mc "$work" "$input" "$tmp" "$KEY4HEP_RELEASE" "$BTAG_MODE"
    } >"$log" 2>&1; then
        rc=0
    else
        rc=$?
    fi

    if ((rc != 0)); then
        printf 'FAIL %s (converter exit %d; log: %s)\n' "$id" "$rc" "$log" >&2
        return "$rc"
    fi
    if [[ ! -s $tmp ]]; then
        printf 'ERROR: converter exited successfully but produced no nonempty output\n' >>"$log"
        printf 'FAIL %s (empty output; log: %s)\n' "$id" "$log" >&2
        return 1
    fi

    local observed_run=
    local run_re='delphi_edm4hep::harness: event[[:space:]]+[0-9]+[[:space:]]+run=(-?[0-9]+)'
    local line
    while IFS= read -r line; do
        if [[ $line =~ $run_re ]]; then
            observed_run=${BASH_REMATCH[1]}
            break
        fi
    done <"$log"

    if [[ $observed_run != "-$id" ]]; then
        printf 'ERROR: expected MC run -%s, observed %s\n' \
            "$id" "${observed_run:-no run in converter log}" >>"$log"
        printf 'FAIL %s (run-number check; log: %s)\n' "$id" "$log" >&2
        return 1
    fi

    if ! run_checker "$tmp" "$id" "$validation_log"; then
        {
            printf 'ERROR: event-by-event output validation failed\n'
            cat -- "$validation_log"
        } >>"$log"
        printf 'FAIL %s (%s integrity/provenance check; log: %s)\n' \
            "$id" "$BTAG_MODE" "$log" >&2
        return 1
    fi
    {
        printf '%s\n' '--- delphi_btag_check ---'
        cat -- "$validation_log"
    } >>"$log"

    mv -f -- "$tmp" "$output"
    write_marker "$marker" "$input" "$id" "$output" "$validation_log"

    rm -rf -- "$work"
    trap - EXIT INT TERM
    printf 'OK   %s -> %s\n' "$id" "$output"
}

export -f convert_one run_checker write_marker
export SOURCE_DIR OUTPUT_DIR LOG_DIR SCRATCH_DIR LOCK_DIR IMAGE EDMBIN KEY4HEP_RELEASE BTAG_MODE PRIMARY_VERTEX_POLICY CHECKER_SHA256

batch_rc=0
if printf '%s\0' "${IDS[@]}" \
    | xargs -0 -r -n 1 -P "$JOBS" bash -c 'set -Eeuo pipefail; convert_one "$1"' batch_sdst_mc; then
    batch_rc=0
else
    batch_rc=$?
fi

complete=0
for id in "${IDS[@]}"; do
    output=$OUTPUT_DIR/qqps_91.25_${id}.edm4hep.root
    if [[ -f $output && -f ${output}.complete ]]; then
        complete=$((complete + 1))
    fi
done

printf 'Selected: %d; complete: %d; output: %s\n' \
    "${#IDS[@]}" "$complete" "$OUTPUT_DIR"
if ((batch_rc != 0 || complete != ${#IDS[@]})); then
    exit 1
fi
