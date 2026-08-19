# delphi-edm4hep

[![CI](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml)
[![key4hep build](https://img.shields.io/endpoint?url=https%3A%2F%2Fdelphi-fulldst-edm4hep.github.io%2Fdelphi-edm4hep%2Fbadges%2Fkey4hep.json)](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml)
[![DELPHI libs build](https://img.shields.io/endpoint?url=https%3A%2F%2Fdelphi-fulldst-edm4hep.github.io%2Fdelphi-edm4hep%2Fbadges%2Fdelphi.json)](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml)
[![docs](https://img.shields.io/badge/docs-API%20%2B%20guides-blue)](https://delphi-fulldst-edm4hep.github.io/delphi-edm4hep/)

The installable software: the dual-pass **DELPHI SDST/FDST → EDM4hep
converter** (`delphi_edm4hep/`) and the data-reconstruction drivers that
feed it (`scripts/data-reco/`).

## Build

```sh
git clone https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep.git
cd delphi-edm4hep

source /cvmfs/delphi.cern.ch/setup.sh                  # DELPHI runtime (pdl2pdl, $DELPHI_DAT)
source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08
unset CXXFLAGS CFLAGS LDFLAGS                          # MUST precede cmake: the DELPHI env
                                                       # injects -ftemplate-depth-25
cmake -S delphi_edm4hep -B build
cmake --build build -j
```

## Run

```sh
# pass 1: shortDST-level collections
./build/delphi_sdst_pass  simana.sdst  inter.edm4hep.root

# pass 2: full-DST collections, (run,evt)-matched onto pass 1
./build/delphi_fdst_pass  inter.edm4hep.root  simana.fadana  final.edm4hep.root
```

Source **both** environments at runtime too (DELPHI first, then key4hep —
the converter reads DELPHI files via PHDST). `delphi_edm4hep/README.md`
documents the full collection schema; `scripts/data-reco/README.md`
documents the 94c data drivers and their environment knobs.

## Dependency versions

The two release badges above report the latest CI result together with the
exact releases that run built against (CI regenerates them on every push to
`dev`).

| Dependency | Version | How it is controlled |
| --- | --- | --- |
| key4hep stack | **2026-04-08** | Pinned by `KEY4HEP_RELEASE` in `delphi_edm4hep/CMakeLists.txt`; configure fails on mismatch. Provides EDM4hep 1.0.0, podio 1.7.0, ROOT 6.38.04, gcc 14.2.0, CMake 3.31 (≥ 3.24 required). |
| EDM4hep / podio | ≥ 1.0 / ≥ 1.7 | Version floors in `find_package`; actual versions come with the stack and are printed at configure time. |
| DELPHI Fortran libs + CERNLIB | follows the sourced env (cvmfs `latest`) | `cmake/FindDelphiAL9.cmake` resolves `$DELPHI_LIB` / `$CERN_LIB` to concrete dated cvmfs paths at configure time and prints the pick; override with `-DDELPHI_AL9_LIB_DIR` / `-DCERN_AL9_LIB_DIR`. The DELPHI badge shows the release CI last resolved. |
| PHDST/SKELANA wrapper headers | vendored @ `fde7b95f` | In-tree under `delphi_edm4hep/extern/delphi-analysis/` (provenance in its README); override with `-DDELPHI_ANALYSIS_INC`. |

When migrating the key4hep pin, update `KEY4HEP_RELEASE`, the `-r` in the
build snippets, and this table — CI verifies the bump automatically.

## License

Not yet chosen. This package vendors the PHDST/SKELANA wrapper headers from
the [`delphi-nanoaod`](https://github.com/DickyChant/delphi-nanoaod) analysis
package (see `delphi_edm4hep/extern/delphi-analysis/README.md` for the exact
provenance), which as far as we know carries no explicit license; until that
is clarified we have deliberately not attached a license here either. Until
one is added, the default "all rights reserved" applies — contact the authors
for use beyond reading.
