# data-reco / EDM4hep driver scripts

Relocated here from `Delphi-Sim-Pipeline` (per the PR #4 review: these data-reco /
EDM4hep driver scripts don't belong in the generator-pipeline repo). They drive
the DELPHI **data** reconstruction and the EDM4hep conversion that the
`delphi_edm4hep` converter performs.

| script | what it does |
|---|---|
| `run_data_reco.sh` | Reconstruct DELPHI **real raw data** (`.sl`) → full DST (→ short DST) locally in the `cmssw/el9` singularity container on CVMFS. Data-side twin of sim-pipeline's `run_singularity.sh`: feeds real detector raw straight into DELANA (`delana43_94c` / `delana43_rd.exe`). |
| `run_data_twopass.sh` | Recalculated-AABTAG-only two-pass EDM4hep conversion on **data**: the official short DST supplies the SDST-level collections, and our reproduced full DST (from `run_data_reco.sh`) supplies the genuinely-full-DST collections (EMCA HPC clusters, HCAL towers, TOF, TDHA, TRAX extrap, TDID drift-calib, MU chambers, dE/dx, …). |
| `batch_94c.sh` | Recalculated-AABTAG-only, resumable, parallel 94c data → EDM4hep batch. Phase A: per unique official `.al`, pass1 → cached intermediate. Phase B: per run, raw `.sl` → full DST → pass2 with the cached intermediate → EDM4hep. Use the `sdst` phase to stop after Phase A. |
| `audit_sdst_data_recalc_94c.py` | Read-only final audit for the exact 429-tape `delphi-batch94c-v3` Phase-A recalculation. It binds every ROOT size/SHA-256 and source-local all-frame checker summary to the producer-recorded campaign/checker hashes, aggregates the expected 5,756,545 events, and atomically writes a JSON report. |
| `archive_legacy_batch_sdst_data_bank_94c.sh` | Explicitly archived reproducer for the completed 429-tape stored-BTG diagnostic. It is retained for provenance, not for new production. |
| `archive_legacy_audit_sdst_data_bank_94c.py` | Read-only exact-inventory audit for that archived data-bank diagnostic. |
| `batch_sdst_mc.sh` | Recalculated-AABTAG-only conversion of explicitly selected official v94c `qqps` SDST MC files. Every event is integrity/provenance checked before an atomic publish and `.root.complete` marker. |
| `audit_sdst_mc_campaign.py` | Audits or directly revalidates the exact qqps campaign inventory, including current-checker provenance and payload/content manifests. |
| `batch_leptonic_long_94c.sh` | Exact 132-tape `lolept94_c2` LONG-DST two-pass conversion. It is fixed to prefix-isolated AABTAG recalculation and has no bank/off mode. |
| `audit_lepton_pid.py` | Full-file, fail-closed audit of the converted sDST muon/electron PID relations and fixed parameter contracts, with JSON counters for MUID bits, ELID/conversion tags, high-momentum opposite-sign pairs, and the target.pdf dE/dx/RICH selections. |
| `summarize_lepton_pid_campaign.py` | Verifies every per-tape lepton audit against its recalculation completion marker and aggregates the exact official 132-file campaign without rereading the ROOT payloads. |
| `plot_lepton_pid_validation.py` | Fail-closed rendering of the frozen target-response/PID counters plus opposite-sign high-momentum dimuon and dielectron mass diagnostics. Pair energies are recomputed from the measured track three-momenta under explicit muon/electron mass hypotheses; outputs are raw populations, not efficiency or background-corrected measurements. |
| `audit_lolept94_event_inventory.py` | Read-only supplemental full-event audit of the frozen 132-tape campaign: exact live inventories, both pass totals, full `(run,event,fileSeq)` uniqueness, empty scratch/temp state, and interrupted-product quarantine integrity. |
| `compare_aabtag_recalc.py` | Strict same-event comparison of two recalculated productions, joined by `(runNumber,eventNumber,fileSeq)`. It validates the raw-status/invocation/validity contract before comparing every AABTAG field; `--allow-left-legacy-schema` keeps older evidence explicitly distinguishable. |
| `stage_btag_edm4hep_to_eos.py` | Verified EOS publisher. Its default collection set is current-schema recalculated AABTAG only; selecting a historical stored-bank collection requires the explicit `--archive-legacy-bank-comparison` acknowledgement. |
| `build_worklist_94c.sh` | Builds the 94c run worklist consumed by `batch_94c.sh` (one line `ED-VID.seq  run  Ytape1,Ytape2,…` per staged raw segment that has a matching official short DST). |
| `run_singularity_direct.sh` | Direct-modern MC wrapper: Pythia → DELSIM → SDST → EDM4hep (direct, in-process via the PHDST loop). Delegates Stages 1–3 to sim-pipeline's `run_singularity.sh` and adds a Stage 4 that runs `delphi_sdst_to_edm4hep`. |
| `dump_hadron_tagging.py` | Reads a DELPHI nanoAOD `t` tree and writes a slim parquet of hadron-tagging features (event-level labels/counts where present, per-particle flavour flags + hemisphere-split variants). |

The `compare_bank_recalc_*.py` programs are archived evidence readers for the
completed apple-to-apple study. They cannot launch conversion and are not
current production or publication recommendations.

## Machine-specific paths (heads-up)

These are personal integration drivers, not portable tooling — they hardcode
absolute paths into this machine's worktree layout. Before running on another
machine, review/override:

- `RUN_SINGULARITY` (in `run_singularity_direct.sh`) → sim-pipeline's
  `container/run_singularity.sh`. **`run_singularity.sh` and the
  `config_z_*.txt` configs stay in `Delphi-Sim-Pipeline`** — they were not
  relocated. Override `RUN_SINGULARITY` if that wrapper lives elsewhere.
- `EDMBIN` / `DIRECT_BIN` → the `delphi_edm4hep` converter build and the
  `delphi_sdst_to_edm4hep` binary (both built from this repo).
- `IMAGE` → the `cmssw-el9` `.sif`.
- `ROOT` / output dirs under your scratch area; data under
  `/eos/experiment/delphi/...`.

## Lepton PID and target-response audit

Source the same key4hep release used for conversion, then scan one or more
converted ROOT files (quoted globs are expanded by the audit itself):

```bash
source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08
scripts/data-reco/audit_lepton_pid.py \
  'reruns/leptons/inter_*.root' \
  --output reruns/leptons/lepton_pid_audit.json
```

For long lists, pass `--manifest files.txt` (one path or glob per non-comment
line; relative paths are resolved from the manifest directory). The script
reads every event and exits nonzero for an unreadable file, a missing required
collection, an unresolved/wrong Particle relation, or an unexpected
`algorithmType`/parameter-vector contract. Population and opposite-sign-pair
counters are diagnostic and are recorded in the JSON rather than used as
acceptance cuts.

### Frozen lolept94_c2 event inventory

The exact 132-file payload inventory contains **831,002 event occurrences** in
both the intermediate and final passes. The CERN catalog value of 828,851 is
retained as provenance metadata, with an explicit payload-minus-catalog
discrepancy of +2,151; it is not used as the payload acceptance count. A full
final-payload scan finds 831,002 unique `(runNumber,eventNumber,fileSeq)` keys,
zero duplicate full keys, 830,724 unique `(runNumber,eventNumber)` pairs, and
278 repeat occurrences distinguished by `fileSeq` across 259 repeated-key
groups and 1,896 runs.

The frozen campaign authority (`campaign.conf`, manifest, resume script,
ROOTs, markers, per-tape audits, and build) remains unchanged. Reproduce the
supplemental read-only report inside the pinned Key4hep environment with:

```bash
scripts/data-reco/audit_lolept94_event_inventory.py --jobs 6 \
  reruns/lepton94c/lolept94_c2_recalc_full_v3
```

The default report is
`reruns/lepton94c/lolept94_c2_recalc_full_v3/supplemental_reports/lolept94_c2_event_inventory.json`.
The completed report has SHA-256
`c416a1f5f8245721e582c7678117c877b0b754e7cb580f7e65b0e6b23f0c3dd1`.
It additionally requires the exact 132 intermediate ROOTs and markers, 132
final ROOTs and markers, 132 frozen PID audits, 660 logs, 132 tape locks, no
live scratch or temporary products, and intact checksummed interrupted-product
quarantine contents.

## AABTAG recalculation campaigns

All new b-tagging validation inputs are produced with prefix-isolated AABTAG
recalculation, not by copying a possibly absent or incompatible stored BTG
bank. The data, MC, and lepton production wrappers are hard-locked to
`recalc`; setting `BTAG_MODE=bank|off` or passing `--btag-mode bank|off` is an
error. Bank production was retired after the apple-to-apple legacy diagnostic
was completed. Its reproducer and audit have explicit `archive_legacy_`
filenames, while the low-level converter/checker retain bank readability. Bank
must not be used for new campaigns, EOS publications, or physics plots. None
of these wrappers passes `--btag-pv`: the recalculated AABTAG primary vertex
is kept separate from the DELANA primary vertex.

To build only the complete per-tape SDST inputs for a prepared 94c worklist:

```bash
ROOT=/absolute/campaign/directory \
  scripts/data-reco/batch_94c.sh all 5 sdst
```

Only consume an intermediate when both `inter_<tape>.root` and its
`inter_<tape>.root.complete` marker exist.  Temporary or interrupted files are
not valid production inputs.

The completed stored-BTG transcription and its audit are archived under the
legacy-closure output area. `archive_legacy_batch_sdst_data_bank_94c.sh` and
`archive_legacy_audit_sdst_data_bank_94c.py` are retained solely to make that
result reproducible; there is no production instruction to rerun them.

For a representative five-file Z→qq MC sample at 91.25 GeV:

```bash
scripts/data-reco/batch_sdst_mc.sh \
  --output-dir /absolute/output/directory \
  --jobs 2 \
  21000-21004
```

The MC outputs are likewise valid only with their `.root.complete` markers.
`batch_sdst_mc.sh` does not trust a marker by itself: it runs
`delphi_btag_check --source sDST --primary-vertex-policy keep-delana` over
every frame of every existing or newly converted file.
The check covers the negative run, mode/recalculated provenance, event
probability triplets and thrust, and, for `recalc`, the AABTAG primary vertex,
all 16 parallel track arrays, probability domains, truncation, particle-index,
attached-track consistency, and the explicit raw-status/invocation/validity
contract. A valid PV must be primary with `algorithmType=3`, finite
position/covariance/chi2 and `0 <= ndf <= 200`; track impact values must be
finite, errors and momenta positive finite, and `Chi2VD` nonnegative finite.
`Chi2PV` follows its legacy relation contract: for `AttachedToPV=1` it must
be finite and at least -0.25 (small CCFVT2 subtraction residuals are reported
as nonfatal roundoff), while for `AttachedToPV=0` the raw word is undefined
and counted diagnostically rather than domain-checked. The legacy flags and
signed VD counts must stay in their documented domains.
Stable per-domain failure counters make each corruption class auditable. The
stable aggregate `key=value` line is
saved in both `logs/*.validation.log` and the completion marker. Older recalc
outputs that predate `AlgorithmInvoked` and `Valid` cannot be upgraded by a
marker refresh: they require reconversion with the current writer.

For two-pass products, the b-tag payloads are distinct validation domains.
`batch_94c.sh` and `batch_leptonic_long_94c.sh` run explicit `--source sDST`
and `--source fDST` checks over every final file. Only the sDST check may use a
pass-1 identity reference; both report identity as `sDST_EVT`. Current
production checks also require `primary_vertex_policy=keep-delana`, raw
`iflpvt=0`, and zero policy mismatches. Current
completion markers contain the product SHA-256 and both direct summaries, so
prefix resumption cannot succeed from an old size/log marker alone. The
checker can inspect frozen pre-provenance fDST output only when an operator
explicitly supplies `--legacy-fdst-beamspot-fallback`; the summary labels that
downgrade, its exact beamspot-status source, and whether fallback was requested
and used. Legacy identity references need the independent
`--legacy-reference-beamspot-fallback` flag. Current production wrappers never
enable either fallback; the archived stored-bank reproduction wrapper enables
only the reference fallback because its frozen recalculated references predate
the source-local fields.

The exact 166-file CERN-origin v94c qqps set is selected explicitly (file
21091 is not in that dataset). Produce only the recalculated campaign:

```bash
# Authoritative recalculated-only production.
scripts/data-reco/batch_sdst_mc.sh --jobs 6 \
  21000-21090 21092-21166

scripts/data-reco/audit_sdst_mc_campaign.py \
  --mode recalc \
  reruns/btag_recalc/mc/qqps_v94c_91p25
```

### Historical local 2026-08-24 campaign record

**Status:** the 2026-08-24 recalculated Data product is retained as exact
inventory and historical first-frame evidence only. It predates the current
raw-`BadEventCode` plus `AlgorithmInvoked`/`Valid` contract, and the current
all-frame `delphi_btag_check` rejects it. In particular, 48,448 events on 53
tapes have `IERRBS != 0`; PSFBTG skipped AABTGS for those events and left the
raw `IBAD` common stale. It is therefore **not** a current physics validation
sample. A current-head 429-tape regeneration and all-frame scan must supersede
it before current Data conclusions are made.

The local, ignored `reruns/btag_recalc/batch94c` SDST-only campaign completed
all 429 unique official tape inputs. The campaign artifacts are not shipped in
the repository; the durable counts and digests are recorded here. Its
machine-readable audit was
`reruns/btag_recalc/batch94c/AUDIT_SDST_AABTAG_2026-08-24.json` (SHA-256
`795ab1a311d0ffaf6546031c43b7a7ffad4018f10bd8440f5bb45093f54691da`).
It records exact manifest/root/marker/log sets, opens every canonical ROOT
file, checks every ROOT count against its per-file log, and validates AABTAG
provenance and required payloads on the first event of every file.

The canonical result is 429 ROOT files, 5,756,545 events, and
22,925,467,500 bytes. All checks implemented by that historical audit passed;
this is not equivalent to the current all-frame check. Twenty-one first-event
uncomputed-value cases are retained as diagnostics (20 have only an
uncomputed thrust value; one also has a beamspot error and uncomputed
probability triplets). Four interrupted hidden temporary files totaling
50,608,676 bytes were excluded from the audit totals and subsequently removed
from the canonical campaign directory; no temporary file remains in
`intermediates`.

The top-level campaign log lacks its success footer because its long-running
driver encountered a shell parse error only after all workers had returned
(`361 OK + 68 cached = 429`). The checked per-file logs, exact completion
markers, ROOT/podio readability, and matching event counts are the completion
authority. The checked-in working copy of `batch_94c.sh` passes `bash -n`.

The paired stored-bank data campaign also contains all 429 files and all
5,756,545 ordered event occurrences. Its all-frame audit is
`reruns/btag_recalc/legacy_closure/data_full_94c/AUDIT_SDST_BANK_2026-08-24.json`
(SHA-256 `7fca06a7c47fbc9899b19f2a578b101ebd8402fd90317cf7c6cc16eed40eeba4`).
Every bank file matches its recalculated counterpart exactly in ordered
`(runNumber,eventNumber,fileSeq)` identity.

The complete official v94c qqps MC production contains 166 files (IDs
21000--21090 and 21092--21166) and 488,468 payload events. The recalculated
campaign audit is
`reruns/btag_recalc/mc/qqps_v94c_91p25/AUDIT_QQPS_V94C_91P25_RECALC.json`
(SHA-256 `6961b77059c530c802bd9ba3b90466b4aa944e7767929c71d9411b041e5fbc50`);
the paired stored-bank audit is
`reruns/btag_recalc/legacy_closure/mc_full_qqps_v94c_91p25/AUDIT_QQPS_V94C_91P25_BANK.json`
(SHA-256 `2f75cb16bc171afd1381012d981f53c724574bd3d9910f109b7bff09eb86c2bc`).
Both scan every frame, have zero required failure counters, and agree on the
exact event total. The recalculated output occupies 6,416,380,688 bytes and
the stored-bank output 6,011,562,836 bytes. Recalculated logs record the known
GETTPARA calibration probes and successful fallback to
`MC:P94C2FMC.610`; unmatched charged-PFO zero-momentum warnings are recorded
separately because they can affect the independent FCC thrust check but do not
alter the AABTAG probability arrays.

## Relocation fixups applied

Only the two references the move itself broke were changed; all other absolute
paths are pre-existing and untouched:

- `batch_94c.sh`: `RECO` now resolves to its sibling `run_data_reco.sh`
  (was an absolute path into `Delphi-Sim-Pipeline/container/`).
- `run_singularity_direct.sh`: the Stage 1–3 delegate is now the overridable
  `RUN_SINGULARITY` (was `$HERE/run_singularity.sh`, which assumed the wrapper
  was a sibling in `container/`).
