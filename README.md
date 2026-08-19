# delphi-edm4hep

[![CI](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/delphi-fullDST-edm4hep/delphi-edm4hep/actions/workflows/ci.yml)
[![key4hep](https://img.shields.io/badge/key4hep-2026--04--08-blue)](https://key4hep.github.io/key4hep-doc/)
[![DELPHI](https://img.shields.io/badge/DELPHI%20libs-cvmfs%20latest-blue)](https://delphi.web.cern.ch/)

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

## License

Not yet chosen. This package vendors the PHDST/SKELANA wrapper headers from
the [`delphi-nanoaod`](https://github.com/DickyChant/delphi-nanoaod) analysis
package (see `delphi_edm4hep/extern/delphi-analysis/README.md` for the exact
provenance), which as far as we know carries no explicit license; until that
is clarified we have deliberately not attached a license here either. Until
one is added, the default "all rights reserved" applies — contact the authors
for use beyond reading.
