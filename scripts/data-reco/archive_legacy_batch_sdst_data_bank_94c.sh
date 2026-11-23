#!/usr/bin/env bash
# ARCHIVED HISTORICAL REPRODUCER: exact 94c data tapes -> stored-BTG EDM4hep.
#
# The tape manifest is derived from batch94c's official worklist.  A file is
# published only after every output frame is checked against the corresponding
# recalculated SDST frame for the same ordered (run,event,fileSeq) identity.
# Existing outputs are never trusted from their marker alone: they are scanned
# again, and a validated marker is then written atomically.

set -Eeuo pipefail

usage() {
    cat <<'EOF'
Usage: archive_legacy_batch_sdst_data_bank_94c.sh [options]

Options:
  -o, --output-dir DIR   Bank-output campaign directory
  -j, --jobs N           Number of parallel tape conversions (default: 1)
      --worklist FILE    Official batch94c worklist (must resolve to 429 tapes)
      --reference-dir D  Audited recalculated per-tape EDM4hep directory
      --source-base DIR  Official DELPHI tape base directory
      --image PATH       Singularity image/directory
      --edmbin DIR       Directory containing converter and validator
      --key4hep TAG      Key4hep release tag (default: 2026-04-08)
      --dry-run          Run the exact 429-tape preflight; convert nothing
  -h, --help             Show this help

This is archived evidence tooling, not a production entrypoint. The b-tag mode
is deliberately fixed to the legacy stored `bank` diagnostic. OUTPUT_DIR,
JOBS, WORKLIST, REFERENCE_DIR, SOURCE_BASE, IMAGE, EDMBIN, and KEY4HEP_RELEASE
may also be set in the environment. Each valid output requires its
`.root.complete` marker. New campaigns must use recalculated AABTAG instead.
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

OUTPUT_DIR=${OUTPUT_DIR:-$REPO_ROOT/reruns/btag_recalc/legacy_closure/data_full_94c}
JOBS=${JOBS:-1}
WORKLIST=${WORKLIST:-$REPO_ROOT/reruns/btag_recalc/batch94c/worklist.txt}
REFERENCE_DIR=${REFERENCE_DIR:-$REPO_ROOT/reruns/btag_recalc/batch94c/intermediates}
SOURCE_BASE=${SOURCE_BASE:-/eos/experiment/delphi/castor2015/tape}
IMAGE=${IMAGE:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el9:x86_64}
EDMBIN=${EDMBIN:-$REPO_ROOT/build}
KEY4HEP_RELEASE=${KEY4HEP_RELEASE:-2026-04-08}
EXPECTED_TAPES=429
EXPECTED_WORKLIST_SHA256=5e6c2c0992a0ebfa34236779d7b2f0ac424fab459446bce4cb3758539162920e
EXPECTED_MANIFEST_SHA256=ab7776cd4d92b5248a74bf2d3a20628854299fc3b2bec67fbac4c0c210934d80
DRY_RUN=0

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
        --worklist)
            need_value "$@"
            WORKLIST=$2
            shift 2
            ;;
        --worklist=*)
            WORKLIST=${1#*=}
            [[ -n $WORKLIST ]] || die '--worklist requires a value'
            shift
            ;;
        --reference-dir)
            need_value "$@"
            REFERENCE_DIR=$2
            shift 2
            ;;
        --reference-dir=*)
            REFERENCE_DIR=${1#*=}
            [[ -n $REFERENCE_DIR ]] || die '--reference-dir requires a value'
            shift
            ;;
        --source-base)
            need_value "$@"
            SOURCE_BASE=$2
            shift 2
            ;;
        --source-base=*)
            SOURCE_BASE=${1#*=}
            [[ -n $SOURCE_BASE ]] || die '--source-base requires a value'
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
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[[ $JOBS =~ ^[1-9][0-9]*$ ]] || die "jobs must be a positive integer: $JOBS"
[[ -f $WORKLIST ]] || die "worklist not found: $WORKLIST"
[[ -d $REFERENCE_DIR ]] || die "reference directory not found: $REFERENCE_DIR"
[[ -d $SOURCE_BASE ]] || die "source base not found: $SOURCE_BASE"

WORKLIST=$(realpath -- "$WORKLIST")
REFERENCE_DIR=$(realpath -- "$REFERENCE_DIR")
SOURCE_BASE=$(realpath -- "$SOURCE_BASE")
OUTPUT_DIR=$(realpath -m -- "$OUTPUT_DIR")
[[ $OUTPUT_DIR != / ]] || die 'refusing to use / as the output directory'
[[ $OUTPUT_DIR != "$REFERENCE_DIR" ]] || \
    die 'bank output directory must differ from the recalculated reference directory'

PREFLIGHT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/archive_legacy_sdst_bank_94c.XXXXXX")
cleanup_preflight() {
    rm -rf -- "$PREFLIGHT_DIR"
}
trap cleanup_preflight EXIT

TAPE_MANIFEST=$PREFLIGHT_DIR/tapes.manifest
if ! awk '
    NF != 3 || $1 !~ /^ED[0-9]+\.[0-9]+$/ || $2 !~ /^[0-9]+$/ {
        printf "invalid worklist line %d: %s\\n", NR, $0 > "/dev/stderr"
        bad=1
        next
    }
    {
        n=split($3, tapes, ",")
        for (i=1; i<=n; ++i) {
            if (tapes[i] !~ /^Y[0-9]+\.[0-9]+$/) {
                printf "invalid tape at worklist line %d: %s\\n", NR, tapes[i] \
                    > "/dev/stderr"
                bad=1
            } else {
                print tapes[i]
            }
        }
    }
    END { exit bad ? 1 : 0 }
' "$WORKLIST" | LC_ALL=C sort -u >"$TAPE_MANIFEST"; then
    die 'worklist format validation failed'
fi

mapfile -t TAPES <"$TAPE_MANIFEST"
((${#TAPES[@]} == EXPECTED_TAPES)) || \
    die "official manifest must contain exactly $EXPECTED_TAPES unique tapes; found ${#TAPES[@]}"

missing=0
for tape in "${TAPES[@]}"; do
    yvid=${tape%%.*}
    input=$SOURCE_BASE/$yvid/${tape}.al
    reference=$REFERENCE_DIR/inter_${tape}.root
    reference_marker=${reference}.complete
    if [[ ! -f $input ]]; then
        printf 'ERROR: input not found: %s\n' "$input" >&2
        missing=$((missing + 1))
    fi
    if [[ ! -s $reference ]]; then
        printf 'ERROR: nonempty recalculated reference not found: %s\n' \
            "$reference" >&2
        missing=$((missing + 1))
    fi
    if [[ ! -f $reference_marker ]]; then
        printf 'ERROR: recalculated completion marker not found: %s\n' \
            "$reference_marker" >&2
        missing=$((missing + 1))
    fi
done
((missing == 0)) || die "$missing input/reference preflight check(s) failed"

command -v sha256sum >/dev/null 2>&1 || die 'sha256sum is not available on PATH'
WORKLIST_SHA256=$(sha256sum -- "$WORKLIST" | awk '{print $1}')
MANIFEST_SHA256=$(sha256sum -- "$TAPE_MANIFEST" | awk '{print $1}')
[[ $WORKLIST_SHA256 == "$EXPECTED_WORKLIST_SHA256" ]] || \
    die "worklist is not the audited official 94c worklist (SHA-256 $WORKLIST_SHA256)"
[[ $MANIFEST_SHA256 == "$EXPECTED_MANIFEST_SHA256" ]] || \
    die "derived tape manifest is not the audited official manifest (SHA-256 $MANIFEST_SHA256)"

if ((DRY_RUN)); then
    printf 'status=PASS action=dry-run btag_mode=bank tapes=%d worklist_sha256=%s manifest_sha256=%s\n' \
        "${#TAPES[@]}" "$WORKLIST_SHA256" "$MANIFEST_SHA256"
    printf 'source_base=%s\nreference_dir=%s\noutput_dir=%s\n' \
        "$SOURCE_BASE" "$REFERENCE_DIR" "$OUTPUT_DIR"
    printf 'first_tape=%s last_tape=%s\n' \
        "${TAPES[0]}" "${TAPES[${#TAPES[@]}-1]}"
    exit 0
fi

command -v singularity >/dev/null 2>&1 || die 'singularity is not available on PATH'
command -v flock >/dev/null 2>&1 || die 'flock is not available on PATH'
[[ -e $IMAGE ]] || die "Singularity image not found: $IMAGE"
[[ -d $EDMBIN ]] || die "EDM4hep binary directory not found: $EDMBIN"
EDMBIN=$(realpath -- "$EDMBIN")
[[ -x $EDMBIN/delphi_sdst_pass ]] || \
    die "converter is not executable: $EDMBIN/delphi_sdst_pass"
[[ -x $EDMBIN/delphi_btag_check ]] || \
    die "validator is not executable: $EDMBIN/delphi_btag_check"
CHECKER_SHA256=$(sha256sum -- "$EDMBIN/delphi_btag_check")
CHECKER_SHA256=${CHECKER_SHA256%% *}
[[ $CHECKER_SHA256 =~ ^[0-9a-f]{64}$ ]] || \
    die "could not hash validator: $EDMBIN/delphi_btag_check"

mkdir -p -- "$OUTPUT_DIR"
LOG_DIR=$OUTPUT_DIR/logs
SCRATCH_DIR=$OUTPUT_DIR/.scratch
LOCK_DIR=$OUTPUT_DIR/.locks
mkdir -p -- "$LOG_DIR" "$SCRATCH_DIR" "$LOCK_DIR"

# Keep two invocations from changing campaign metadata or auditing an output
# directory while the other's workers are still publishing files.
exec {campaign_lock_fd}>"$OUTPUT_DIR/.campaign.lock"
flock "$campaign_lock_fd"

EXPECTED_CONFIG=$PREFLIGHT_DIR/campaign.conf
{
    printf 'format=delphi-data-btag-campaign-v1\n'
    printf 'btag_mode=bank\n'
    printf 'expected_recalculated=0\n'
    printf 'tape_count=%s\n' "${#TAPES[@]}"
    printf 'worklist=%s\n' "$WORKLIST"
    printf 'worklist_sha256=%s\n' "$WORKLIST_SHA256"
    printf 'manifest_sha256=%s\n' "$MANIFEST_SHA256"
    printf 'source_base=%s\n' "$SOURCE_BASE"
    printf 'reference_dir=%s\n' "$REFERENCE_DIR"
    printf 'reference_btag_mode=recalc\n'
    printf 'key4hep_release=%s\n' "$KEY4HEP_RELEASE"
} >"$EXPECTED_CONFIG"

publish_or_match() {
    local expected=$1 destination=$2 temporary
    if [[ -e $destination || -L $destination ]]; then
        [[ -f $destination && ! -L $destination ]] || \
            die "campaign metadata is not a regular file: $destination"
        cmp -s -- "$expected" "$destination" || \
            die "campaign metadata mismatch: $destination"
        return 0
    fi
    temporary=$(mktemp --tmpdir="$OUTPUT_DIR" ".$(basename "$destination").XXXXXX.tmp")
    cp -- "$expected" "$temporary"
    mv -f -- "$temporary" "$destination"
}

publish_or_match "$EXPECTED_CONFIG" "$OUTPUT_DIR/campaign.conf"
publish_or_match "$TAPE_MANIFEST" "$OUTPUT_DIR/tapes.manifest"

run_checker() {
    local candidate=$1 reference=$2 validation_log=$3
    singularity exec --cleanenv \
        --bind /cvmfs \
        --bind /lib64:/host_lib64:ro \
        --bind "$OUTPUT_DIR:$OUTPUT_DIR" \
        --bind "$REFERENCE_DIR:$REFERENCE_DIR:ro" \
        --bind "$EDMBIN:/edmbin:ro" \
        "$IMAGE" bash -c '
            set -eo pipefail
            set +u
            source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$1" >/dev/null 2>&1
            export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
            exec /edmbin/delphi_btag_check --source sDST \
                --legacy-reference-beamspot-fallback \
                "$2" data bank "$3"
        ' archive_legacy_sdst_bank_94c "$KEY4HEP_RELEASE" "$candidate" "$reference" \
        >"$validation_log" 2>&1
}

write_marker() {
    local marker=$1 input=$2 tape=$3 output=$4 reference=$5 validation_log=$6
    local marker_tmp size_bytes input_size_bytes reference_size_bytes
    local validated_utc validation_summary
    marker_tmp=$(mktemp --tmpdir="$OUTPUT_DIR" ".$(basename "$marker").XXXXXX.tmp")
    size_bytes=$(stat -c %s -- "$output") || {
        rm -f -- "$marker_tmp"
        return 1
    }
    input_size_bytes=$(stat -c %s -- "$input") || {
        rm -f -- "$marker_tmp"
        return 1
    }
    reference_size_bytes=$(stat -c %s -- "$reference") || {
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
    if ! {
        printf 'format=delphi-data-btag-complete-v1\n'
        printf 'tape=%s\n' "$tape"
        printf 'input=%s\n' "$input"
        printf 'input_size_bytes=%s\n' "$input_size_bytes"
        printf 'identity_reference=%s\n' "$reference"
        printf 'identity_reference_size_bytes=%s\n' "$reference_size_bytes"
        printf 'btag_mode=bank\n'
        printf 'recalculated=0\n'
        printf 'output_size_bytes=%s\n' "$size_bytes"
        printf 'manifest_sha256=%s\n' "$MANIFEST_SHA256"
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
    local tape=$1 yvid input reference output marker log validation_log lock
    local lock_fd work tmp cleanup_cmd rc
    tape=${tape//$'\r'/}
    yvid=${tape%%.*}
    input=$SOURCE_BASE/$yvid/${tape}.al
    reference=$REFERENCE_DIR/inter_${tape}.root
    output=$OUTPUT_DIR/inter_${tape}.root
    marker=${output}.complete
    log=$LOG_DIR/${tape}.bank.log
    validation_log=$LOG_DIR/${tape}.bank.validation.log
    lock=$LOCK_DIR/${tape}.lock

    exec {lock_fd}>"$lock"
    flock "$lock_fd"

    # A marker is advisory.  Re-scan the actual file so a recalc output copied
    # into this directory can never be mistaken for a stored-bank product.
    if [[ -e $output || -L $output ]]; then
        # Withdraw any prior success claim until the current binary has proved
        # both the content mode and its exact reference identity again.
        rm -f -- "$marker"
        if [[ ! -f $output || -L $output ]]; then
            printf 'FAIL %s (existing output is not a regular file: %s)\n' \
                "$tape" "$output" >&2
            return 1
        fi
        if run_checker "$output" "$reference" "$validation_log"; then
            {
                printf '%s\n' '--- delphi_btag_check ---'
                cat -- "$validation_log"
            } >>"$log" || {
                printf 'FAIL %s (could not append checker summary to %s)\n' \
                    "$tape" "$log" >&2
                return 1
            }
            write_marker "$marker" "$input" "$tape" "$output" \
                "$reference" "$validation_log"
            printf 'SKIP %s (validated bank mode and exact frame identity)\n' "$tape"
            return 0
        fi
        printf 'FAIL %s (existing output failed bank/identity validation; log: %s)\n' \
            "$tape" "$validation_log" >&2
        return 1
    fi

    # Recover the inverse crash window (marker publish without a visible
    # output, e.g. after an external move) without ever treating it as done.
    rm -f -- "$marker"

    [[ -f $input ]] || {
        printf 'FAIL %s (input disappeared: %s)\n' "$tape" "$input" >&2
        return 1
    }
    [[ -s $reference && -f ${reference}.complete ]] || {
        printf 'FAIL %s (reference disappeared or lost marker: %s)\n' \
            "$tape" "$reference" >&2
        return 1
    }

    work=$(mktemp -d --tmpdir="$SCRATCH_DIR" "${tape}.XXXXXX")
    tmp=$(mktemp --tmpdir="$OUTPUT_DIR" ".inter_${tape}.XXXXXX.tmp.root")
    printf -v cleanup_cmd 'rm -f -- %q; rm -rf -- %q' "$tmp" "$work"
    trap "$cleanup_cmd" EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    if {
        printf 'input=%s\n' "$input"
        printf 'temporary_output=%s\n' "$tmp"
        printf 'identity_reference=%s\n' "$reference"
        printf 'btag_mode=bank\n'
        printf 'converter=/edmbin/delphi_sdst_pass INPUT OUTPUT --btag bank\n'
        singularity exec --cleanenv \
            --bind /cvmfs \
            --bind /lib64:/host_lib64:ro \
            --bind "$SOURCE_BASE:$SOURCE_BASE:ro" \
            --bind "$OUTPUT_DIR:$OUTPUT_DIR" \
            --bind "$EDMBIN:/edmbin:ro" \
            "$IMAGE" bash -c '
                set -eo pipefail
                set +u
                source /cvmfs/delphi.cern.ch/setup.sh >/dev/null 2>&1
                source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$4" >/dev/null 2>&1
                export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/host_lib64"
                cd -- "$1"
                exec /edmbin/delphi_sdst_pass "$2" "$3" --btag bank
            ' archive_legacy_sdst_bank_94c "$work" "$input" "$tmp" "$KEY4HEP_RELEASE"
    } >"$log" 2>&1; then
        rc=0
    else
        rc=$?
    fi

    if ((rc != 0)); then
        printf 'FAIL %s (converter exit %d; log: %s)\n' "$tape" "$rc" "$log" >&2
        return "$rc"
    fi
    if [[ ! -s $tmp ]]; then
        printf 'ERROR: converter exited successfully but produced no nonempty output\n' \
            >>"$log"
        printf 'FAIL %s (empty output; log: %s)\n' "$tape" "$log" >&2
        return 1
    fi

    if ! run_checker "$tmp" "$reference" "$validation_log"; then
        {
            printf 'ERROR: event-by-event bank/identity validation failed\n'
            cat -- "$validation_log"
        } >>"$log"
        printf 'FAIL %s (bank/identity check; log: %s)\n' "$tape" "$log" >&2
        return 1
    fi
    {
        printf '%s\n' '--- delphi_btag_check ---'
        cat -- "$validation_log"
    } >>"$log"

    mv -f -- "$tmp" "$output"
    write_marker "$marker" "$input" "$tape" "$output" "$reference" \
        "$validation_log"

    rm -rf -- "$work"
    trap - EXIT INT TERM
    printf 'OK   %s -> %s\n' "$tape" "$output"
}

export -f convert_one run_checker write_marker
export SOURCE_BASE REFERENCE_DIR OUTPUT_DIR LOG_DIR SCRATCH_DIR LOCK_DIR
export IMAGE EDMBIN KEY4HEP_RELEASE MANIFEST_SHA256 CHECKER_SHA256

batch_rc=0
if printf '%s\0' "${TAPES[@]}" \
    | xargs -0 -r -n 1 -P "$JOBS" \
        bash -c 'set -Eeuo pipefail; convert_one "$1"' archive_legacy_sdst_bank_94c; then
    batch_rc=0
else
    batch_rc=$?
fi

EXPECTED_OUTPUTS=$PREFLIGHT_DIR/expected.outputs
EXPECTED_MARKERS=$PREFLIGHT_DIR/expected.markers
printf 'inter_%s.root\n' "${TAPES[@]}" | LC_ALL=C sort >"$EXPECTED_OUTPUTS"
printf 'inter_%s.root.complete\n' "${TAPES[@]}" | LC_ALL=C sort >"$EXPECTED_MARKERS"

ACTUAL_OUTPUTS=$PREFLIGHT_DIR/actual.outputs
ACTUAL_MARKERS=$PREFLIGHT_DIR/actual.markers
find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'inter_*.root' -printf '%f\n' \
    | LC_ALL=C sort >"$ACTUAL_OUTPUTS"
find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'inter_*.root.complete' -printf '%f\n' \
    | LC_ALL=C sort >"$ACTUAL_MARKERS"

outputs_exact=1
markers_exact=1
cmp -s -- "$EXPECTED_OUTPUTS" "$ACTUAL_OUTPUTS" || outputs_exact=0
cmp -s -- "$EXPECTED_MARKERS" "$ACTUAL_MARKERS" || markers_exact=0
complete=$(wc -l <"$ACTUAL_MARKERS")

printf 'selected=%d complete=%d outputs_exact=%d markers_exact=%d output=%s\n' \
    "${#TAPES[@]}" "$complete" "$outputs_exact" "$markers_exact" "$OUTPUT_DIR"
if ((batch_rc != 0 || outputs_exact == 0 || markers_exact == 0 ||
     complete != EXPECTED_TAPES)); then
    exit 1
fi
