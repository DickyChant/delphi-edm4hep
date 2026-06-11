# data-reco / EDM4hep driver scripts

Relocated here from `Delphi-Sim-Pipeline` (per the PR #4 review: these data-reco /
EDM4hep driver scripts don't belong in the generator-pipeline repo). They drive
the DELPHI **data** reconstruction and the EDM4hep conversion that the
`delphi_edm4hep` converter performs.

| script | what it does |
|---|---|
| `run_data_reco.sh` | Reconstruct DELPHI **real raw data** (`.sl`) → full DST (→ short DST) locally in the `cmssw/el9` singularity container on CVMFS. Data-side twin of sim-pipeline's `run_singularity.sh`: feeds real detector raw straight into DELANA (`delana43_94c` / `delana43_rd.exe`). |
| `run_data_twopass.sh` | Two-pass EDM4hep conversion on **data**: the official short DST supplies the SDST-level collections, and our reproduced full DST (from `run_data_reco.sh`) supplies the genuinely-full-DST collections (EMCA HPC clusters, HCAL towers, TOF, TDHA, TRAX extrap, TDID drift-calib, MU chambers, dE/dx, …). |
| `batch_94c.sh` | Large-scale, resumable, parallel 94c data → EDM4hep batch. Phase A: per unique official `.al`, pass1 → cached intermediate. Phase B: per run, raw `.sl` → full DST → pass2 with the cached intermediate → EDM4hep. |
| `build_worklist_94c.sh` | Builds the 94c run worklist consumed by `batch_94c.sh` (one line `ED-VID.seq  run  Ytape1,Ytape2,…` per staged raw segment that has a matching official short DST). |
| `run_singularity_direct.sh` | Direct-modern MC wrapper: Pythia → DELSIM → SDST → EDM4hep (direct, in-process via the PHDST loop). Delegates Stages 1–3 to sim-pipeline's `run_singularity.sh` and adds a Stage 4 that runs `delphi_sdst_to_edm4hep`. |
| `dump_hadron_tagging.py` | Reads a DELPHI nanoAOD `t` tree and writes a slim parquet of hadron-tagging features (event-level labels/counts where present, per-particle flavour flags + hemisphere-split variants). |

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

## Relocation fixups applied

Only the two references the move itself broke were changed; all other absolute
paths are pre-existing and untouched:

- `batch_94c.sh`: `RECO` now resolves to its sibling `run_data_reco.sh`
  (was an absolute path into `Delphi-Sim-Pipeline/container/`).
- `run_singularity_direct.sh`: the Stage 1–3 delegate is now the overridable
  `RUN_SINGULARITY` (was `$HERE/run_singularity.sh`, which assumed the wrapper
  was a sibling in `container/`).
