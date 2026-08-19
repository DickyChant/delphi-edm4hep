# delphi_edm4hep

Convert DELPHI ZEBRA reconstruction (shortDST / fullDST) to
[EDM4hep](https://github.com/key4hep/EDM4hep). A per-domain C++ library plus
three command-line tools, organised as a two-pass pipeline.

- **Pass 1** reads a shortDST (`.sdst`) and writes an intermediate EDM4hep
  file with `sDST_*` collections.
- **Pass 2** reads that intermediate file plus the matching fullDST
  (`.fadana`), copies the `sDST_*` collections through, and adds `fDST_*`
  collections (fullDST-only detector detail, plus hybrid collections that
  re-stitch sDST objects onto fullDST tracks).
- A standalone post-processing tool derives a per-run beamspot from the
  reconstructed primary vertices.

Collection names follow `<source>_<BANK>_<ReadableName>`, where `<source>`
is `sDST` or `fDST`, `<BANK>` is the DELPHI PA-module or SKELANA-common
mnemonic, and `<ReadableName>` uses DELPHI terminology. Positions are in
**mm**, momenta/energy in **GeV**, times in **ns**, angles in **rad**.

---

## 1. Build and run

### Prerequisites

- A key4hep environment (provides EDM4hep, podio, ROOT):
  ```sh
  source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08
  ```
  The release is **pinned** in `CMakeLists.txt` (`KEY4HEP_RELEASE`); configure
  fails if the sourced stack differs, so a `latest` drift can't silently swap
  EDM4hep/podio/ROOT versions. To migrate, bump the pin (or pass
  `-DKEY4HEP_RELEASE=<release>`; `-DKEY4HEP_RELEASE_STRICT=OFF` demotes the
  mismatch to a warning). CI reads the release out of the pin, so a bump is
  CI-verified automatically — just update the `-r` in the README build
  snippets and the key4hep badge in the top-level README alongside.
- The DELPHI almalinux-9 Fortran libraries (PHDST / SKELANA / DSTANA …),
  located by `cmake/FindDelphiAL9.cmake`. Source the DELPHI environment
  (`source /cvmfs/delphi.cern.ch/setup.sh`) **before configuring**: the find
  module pins the library directories from `$DELPHI_LIB` / `$CERN_LIB`,
  resolving cvmfs symlinks (`latest`, `pro`) to concrete release paths so a
  later `latest` bump can't silently change or break the build. Without the
  env it falls back to discovery under `-DDELPHI_AL9_ROOT`; override the pins
  directly with `-DDELPHI_AL9_LIB_DIR=...` / `-DCERN_AL9_LIB_DIR=...`.
- The `delphi-analysis` C++ wrapper headers (`phdst/*.hpp`, `skelana/*.hpp`)
  are vendored in-tree (`extern/delphi-analysis/`, copied from
  [delphi-nanoaod](https://github.com/DickyChant/delphi-nanoaod) — provenance
  in the README there), so no submodule fetch is needed. Override with
  `-DDELPHI_ANALYSIS_INC=/path/to/delphi-analysis/include` to build against
  an external checkout. (Only the two PHDST-driven passes need these;
  `delphi_bs_fit` does not.)

### Compile

```sh
unset CXXFLAGS CFLAGS LDFLAGS     # see Note — must precede `cmake -S`
cmake -S . -B build
cmake --build build -j
```

> **Note — strip the DELPHI env's compiler flags before *configuring*.** Sourcing
> a DELPHI release setup (`source /cvmfs/delphi.cern.ch/setup.sh`, needed at
> *runtime* for the Fortran libs) exports `CXXFLAGS` / `CFLAGS` carrying
> CERNLIB-era options — notably `-ftemplate-depth-25` and `-ansi` — that break the
> C++20 / podio / nlohmann-json build (`template instantiation depth exceeds
> maximum of 25`). CMake bakes `$CXXFLAGS` into the cache at the **configure**
> step, so they must be stripped there; stripping only at `cmake --build` is too
> late. Either `unset` them as above, or `env -u CXXFLAGS -u CFLAGS -u LDFLAGS
> cmake -S . -B build`.

### Run

```sh
# Pass 1 : shortDST -> intermediate EDM4hep (sDST_* collections)
./build/delphi_sdst_pass  input.sdst  out_sdst.edm4hep.root  [-n MAX_EVENTS]

# Pass 2 : intermediate + fullDST -> final EDM4hep (sDST_* + fDST_*)
./build/delphi_fdst_pass  out_sdst.edm4hep.root  input.fadana \
                          out_final.edm4hep.root  [-n MAX_EVENTS]

# Post-processing : per-run beamspot from aggregated primary vertices
./build/delphi_bs_fit     out_final.edm4hep.root  beamspot_by_run.csv
```

Pass 2 matches each fullDST event to the intermediate frame by
`(runNumber, eventNumber)`, and matches tracks within an event by PA.TRAC
perigee geometry (the PA index is not stable across DST levels).

### Tests

```sh
ctest --test-dir build              # everything
ctest --test-dir build -R cli_sdst  # a subset, by name regex
```

Two kinds of test:

- **CLI argument-contract checks** — each pass must exit nonzero on missing
  arguments and on a non-numeric / non-positive `-n` (declared `WILL_FAIL`,
  so `ctest` passes iff the binary rejects). These need no data files.
- **`tests/align_audit.py`** — audits a converted EDM4hep file for the
  regression class where a UserData array is labelled parallel to the wrong
  collection, or a relation (e.g. RecDqdx → Track) is left unset. It is a
  no-op (exit 0) unless `DELPHI_EDM4HEP_SAMPLE` points at a converted file:
  ```sh
  DELPHI_EDM4HEP_SAMPLE=out_final.edm4hep.root ctest --test-dir build -R alignment_audit
  ```

---

## 2. Output collections

This section is self-contained — it describes the physical content of every
collection and the meaning/units of every field, so the original DELPHI bank
documentation is not needed to use the output.

### 2.0 EDM4hep field conventions used here

How each EDM4hep datatype is populated (units: mm, GeV, ns, rad throughout):

- **Track** — the helix lives in `trackStates`, each a
  `(D0, phi, omega, Z0, tanLambda, time)` tuple with `D0`,`Z0` in mm,
  `omega` (signed curvature) in 1/mm, `phi`/`tanLambda` dimensionless, plus a
  6×6 lower-triangular covariance in those parameters. `chi2`/`ndf` are the
  DELPHI track-fit values. Charge and momentum are **not** on the Track — they
  are on the associated ReconstructedParticle.
- **ReconstructedParticle** — `momentum` (px,py,pz), `energy`, `mass` (GeV);
  `charge` in units of e (0 when the DELPHI charge code is "undefined");
  `tracks` / `clusters` / `particleIDs` relations.
- **Vertex** — `position` (mm); `covMatrix` is the 6-element lower triangle
  `(XX, XY, YY, XZ, YZ, ZZ)` in mm²; `chi2`, `ndf`; `primary` flag;
  `algorithmType`; `particles` relation to the constituent ReconstructedParticles.
- **Cluster** — `energy`; `position` (mm) or, for direction-only detectors,
  `iTheta`/`iPhi` (rad); `type` is a sub-detector bit-mask
  (**bit 0 = HPC, bit 1 = EMF, bit 2 = HCAL, bit 3 = STIC, bit 4 = CCA**);
  `subdetectorEnergies` holds the per-layer (HPC) or per-hit (HCAL) energy
  profile; `shapeParameters` holds the parallel layer indices (HCAL) or extra
  scalars.
- **ParticleID** — `algorithmType` identifies the detector/algorithm (values
  given per collection below); `parameters` is an ordered `float` vector whose
  layout is given per collection; `setParticle` links to the
  ReconstructedParticle.
- **TrackerHit3D** — `position` (mm), `cellID`, `type`, `eDep`.
- **CalorimeterHit** — `energy`, `position` (mm), `type`, `cellID`, `time` (ns).
- **MCParticle** — `PDG`, `generatorStatus`, `momentum`/`mass` (GeV),
  `vertex` (production point, mm), `charge`, `parents`/`daughters`.
- **RecoMCParticleLink** — `from` (ReconstructedParticle) → `to` (MCParticle),
  with a `weight`.
- **UserDataCollection&lt;T&gt;** — a flat array stored parallel (index-aligned)
  to the collection named in its description.

### 2.1 Event-level Frame parameters (`sDST_EVT_*`)

Per-event scalars stored as podio Frame parameters:

- Identifiers: `runNumber`, `eventNumber`, `fileSeq`, `date` (yymmdd),
  `time` (hhmmss), `fillNumber` (LEP fill), `experiment`, `dstVersion`.
- Event topology (team-4 reconstruction): `hadronicTagTeam4` (hadronic-Z
  flag), `nChargedTeam4`, `nCharged`, `nNeutral`.
- Energies (GeV): `ECMS` (centre-of-mass), `EChargedTotal`, `ENeutralEM`,
  `ENeutralHad`.
- Beam spot: `BeamSpotX/Y/Z` and `BeamSpotSigmaX/Y/Z` (mm),
  `BeamSpotErrorCode` (0 if the beamspot bank is valid).
- Magnetic field: `BField` (Tesla) and `BFieldGevPerCm` (the
  curvature-to-momentum conversion factor).

### 2.2 Pass-1 collections (`sDST_*`)

**Truth**

- `sDST_LUJ_GenParticles` (MCParticle) — the generator (LUND/JETSET) event
  record: `PDG`, `generatorStatus`, momentum/mass (GeV), production vertex
  (mm), charge, and parent links.
- `sDST_TBL_RecoToGen` (RecoMCParticleLink) — exact reconstructed→generated
  correspondence from the DELPHI association tables (not a geometric match);
  `from` = `sDST_MAIN_Particles`, `to` = `sDST_LUJ_GenParticles`.

**Tracks & particles**

- `sDST_TRAC_Tracks` (Track) — one charged track per reconstructed charged
  particle. A single `AtIP` TrackState carries the perigee helix
  (`D0` = −ε with DELPHI→LCIO sign flip, `Z0`, `phi`, `omega`, `tanLambda`)
  with the 5×5 covariance obtained by inverting the DELPHI weight matrix and
  rotating into helix parameters. `chi2`/`ndf` are the with-VD fit when
  available, else the without-VD fit.
- `sDST_TRAC_d0PV`, `sDST_TRAC_z0PV`, `sDST_TRAC_d0BS` (UserData&lt;float&gt;) —
  impact parameters of each track w.r.t. the primary vertex (`d0PV`, `z0PV`)
  and the beam spot (`d0BS`), mm; parallel to `sDST_TRAC_Tracks` (charged
  only — neutrals have no entry), NaN when no PV/BS-corrected value is
  available for that track.
- `sDST_VECP_LVLOCK` (UserData&lt;int32&gt;) — per-particle track-quality
  bit-mask (a set bit marks calorimeter-overlap / re-use); −1 for neutrals.
  Parallel to `sDST_MAIN_Particles`.
- `sDST_MAIN_Particles` (ReconstructedParticle) — charged and neutral
  particles. The 4-momentum and mass come from the SKELANA combined-momentum
  vector (mass-hypothesis aware). `charge` = +1/−1 from the DELPHI charge code;
  the "undefined" code maps to 0. Charged particles link to their
  `sDST_TRAC_Tracks` entry.

**Vertices**

- `sDST_PV_PrimaryVertex` (Vertex) — the event primary vertex (position + 6
  covariance terms in mm², `chi2`, `ndf`, `primary=true`).
- `sDST_PV_Vertices` (Vertex) + `sDST_PV_Vertices_StatusBits`
  (UserData&lt;int32&gt;) — the full vertex chain (primary + secondary +
  simulation vertices); the parallel array carries the raw DELPHI per-vertex
  status word (secondary / hadronic-secondary / simulation / flavour-tag bits).
- `sDST_BSP_BeamSpot` (Vertex, 1 entry) — the official beamspot: position with
  a diagonal covariance built from the beam widths; `algorithmType = 2` marks
  "beamspot bank, not a fit". (See also `delphi_bs_fit` in §3.)
- `sDST_V0_V0Candidates` (Vertex) — the official DELPHI V0 vertices (K⁰s / Λ /
  γ-conversion candidates); `position` from the V0 fit, with the two daughter
  particles in the `particles` relation. (Covariance is left zero — the bank's
  weight matrix is in a non-standard basis.)
- `sDST_PHC_PhotonConversions` (Vertex) — photon-conversion (γ→e⁺e⁻) vertices,
  e⁺/e⁻ in the `particles` relation.

**Calorimeter showers**

- `sDST_EMNC_Showers` (Cluster) — electromagnetic showers (HPC barrel and FEMC
  endcap, distinguished by `type` bits 0/1); `energy`, `position`, and the
  per-layer energy profile in `subdetectorEnergies`.
- `sDST_HCNC_Showers` (Cluster) — hadron-calorimeter showers (`type` bit 2);
  per-hit energies in `subdetectorEnergies`, the parallel layer indices in
  `shapeParameters`.

**Particle identification** (all ParticleID; `setParticle` → `sDST_MAIN_Particles`)

- `sDST_HAID_dEdx` (algType 1) — TPC truncated-mean dE/dx.
  `params`: `[0]` dE/dx (MIP-normalised), `[1]` σ. Also emitted in EDM4hep's
  typed `RecDqdx` form as `sDST_HAID_dEdx_RecDqdx` (type 1).
- `sDST_HAID_HadronID` (algType 4) — combined hadron ID, 18 params:
  `[0]` kaon-RICH tag, `[1]` proton-RICH, `[2]` pion-RICH, `[3]` kaon-dE/dx,
  `[4]` proton-dE/dx, `[5]` combined kaon likelihood, `[6]` combined proton
  likelihood, `[7]` RICH quality, `[8]` θ_C gas (rad), `[9]` σθ gas,
  `[10]` N photo-electrons gas, `[11]` N expected gas, `[12]` gas flag
  (`FLAGG` = `KGRIC(5)`, RING/VETO quality word carried as a float; read
  via `int(round(v))`), `[13..16]` the same four quantities for the liquid
  radiator, `[17]` liquid flag (`FLAGL` = `KLRIC(5)`, same convention).
- `sDST_HAID_AltTags` (algType 40) — alternate hadron-ID tag tables, 26
  integer tags: NEWTAG π/K/p/heavy `[0..3]`, track-selection `[4..7]`,
  RICH-probability `[8..13]`, dE/dx-probability `[14..19]`, combined RICH+TPC
  `[20..25]`. Each tag: −1 = no info, 0 = not this species, 1/2/3 =
  loose/standard/tight.
- `sDST_HAID_dEdxVD` (algType 7) — VD-only dE/dx. `params`: `[0]` VD dE/dx,
  `[1]` number of VD hits used.
- `sDST_MUID_MuonID` (algType 2) — `[0]` muon tag (MUCAL2: 1 very-loose …
  4 tight, 5 HCAL), `[1]` global χ² of the very-loose refit, `[2]` hit pattern.
- `sDST_ELID_ElectronID` (algType 3) — `[0]` electron tag (0 not run, 1 not-e,
  2 very-loose, 3 loose, 4 standard, 5 tight), `[1]` γ-conversion tag.
- `sDST_PHOT_PhotonID` (algType 30) — HPC photon-ID scores: energy-weighted
  shower depth, n clusters, first layer, n layers, max consecutive layers,
  transverse fluctuation, longitudinal-fit value (up to 7 params).
- `sDST_PHOT_Pi0ID` (algType 111) — π⁰→γγ HPCANA fit, 26 params (tensor-fit
  mass / rotation / eigenvalues, connected & expected maxima, two-Gaussian fit
  parameters, shower θ/φ, OD-link & stray-shower counts, fit χ², σφ/σθ).
- `sDST_ODHI_OuterDetector` (algType 29) — Outer-Detector per-track hit
  summary (up to 7 raw bank words).
- `sDST_MUFI_RefitMuon` (algType 27) — refitted-muon fit summary: detector
  (14=MUB/17=MUS/30=MUF), n layers, ndof, global χ², first-layer x/y,
  expected-missing-layers, chambers-alone χ², extrapolated x/y/θ/φ and their
  errors.

**Other detectors**

- `sDST_ELTR_RefitTracks` (Track) + `sDST_ELTR_ParticleIndex`
  (UserData&lt;int32&gt;) — the electron-hypothesis refitted track (same perigee
  + covariance treatment as `sDST_TRAC_Tracks`); the parallel index gives the
  `sDST_MAIN_Particles` entry it belongs to.
- `sDST_SSTC_Showers` (Cluster) — STIC (small-angle) calorimeter showers:
  `energy`, direction `iTheta`/`iPhi`; `type` bit 3.
- `sDST_TDVD_VDPoints` (TrackerHit3D) — unassociated Vertex-Detector hits.
- `sDST_TDVD_VDHits` (TrackerHit3D) + `sDST_TDVD_VDHits_TrackIndex`
  (UserData&lt;int32&gt;) — VD hits associated to a track; the parallel index
  gives the owning particle.
  For both VD collections `position` is a **cylindrical-mixed** triple
  `(R, slot2, slot4)` in mm, **not Cartesian** — the module→φ table needed for
  global (x,y) is not in the DST, so that conversion is left to the consumer.
  `cellID` = signed module number (sign = Z side); `type` bit 0 marks an R-Z
  measurement; `eDep` carries the signal-to-noise ratio.

### 2.3 Pass-2 pure-fullDST collections (`fDST_*`)

- `fDST_MAIN_MatchProvenance` (UserData&lt;int32&gt;, parallel to
  `fDST_MAIN_Particles` — one entry per reconstructed particle, charged and
  neutral, NOT parallel to `fDST_TRAC_Tracks` which is charged-only) —
  per-particle provenance from the pass-2 perigee match: `+1` charged
  particle matched to a fullDST PA, `0` charged particle with no fullDST
  counterpart (post-DST V0 daughter, photon-conversion daughter, or hadronic
  secondary that exists only in the shortDST), `−1` neutral particle (no
  perigee match applies).
- `fDST_TRAC_Tracks` (Track) — the shortDST track with extra TrackStates
  appended: one `AtFirstHit` (reference point = first measured point, mm) and
  one `AtOther` per track-element detector (TEID/TETP/TEOD/TEFA/TEFB and the
  forward-RICH TERF). Each TE state's reference point is the measured
  `(c1,c2,c3)` (mm) and its helix parameters + 6×6 covariance are the
  push-forward of the TE-bank measurement.
- `fDST_TRAC_Tracks_FitQuality` (ParticleID, companion to the TE TrackStates) —
  `algorithmType` = TE detector label (12 TEID, 13 TETP, 14 TEOD, 15 TEFA,
  16 TEFB, 21 TERF); `params`: `[0]` charge (±1/0), `[1]` B field (T),
  `[2]` TE descriptor word, `[3]` ndf, `[4]` χ², `[5]` track length (cm),
  `[6]` number of stored covariance entries. (`[0]` and `[1]` let you recover
  momentum from the state's `omega` without external lookups.)
- `fDST_TRAX_ExtrapPoints` (ParticleID, algType 20) — one entry per track
  extrapolation surface; `params`: `[0]` detector id, `[1]` measurement code
  (0 plane / 1 cylinder), `[2..4]` reference point (mm), `[5]` θ, `[6]` φ,
  `[7]` 1/P, `[8..22]` the 15-element (5×5) covariance.
- `fDST_TOF_TimeOfFlight` (ParticleID, algType 5) — `[0]` time of flight (ns),
  `[1]` σ_t (ns).
- `fDST_MTPC_dEdxExtended` (ParticleID, algType 6) + `fDST_MTPC_dEdx_RecDqdx` —
  extended TPC dE/dx, 10 params: `[0]` 80%-truncated mean, `[1]` σ80,
  `[2]` 65%-truncated mean, `[3]` σ65, `[4]` integrated 80% dE/dx, `[5]` n pads,
  `[6]` n wires, `[7]` n saturated, `[8]` n empty, `[9]` pad-row pattern.
- `fDST_MU_MuonChambers` (ParticleID, algType 4) — raw muon-chamber refit
  summary, 12 params: detector, n layers, ndof, global χ², first-layer x/y,
  expected hit pattern, chambers-alone χ², extrapolated x/y/θ/φ.
- `fDST_EL_ElectronExtra` (ParticleID, algType 5) — `[0]` detector id
  (9 HPC / 26 EMF), `[1]` number of showers.
- `fDST_TDID_DriftCalib` (ParticleID, algType 17) — `[0]` signed jet sector,
  `[1]` number of valid drift wires, `[2]` sum of drift times.
- `fDST_EMCA_HPCClusters` (CalorimeterHit) — per-pad HPC: `energy` =
  photo-electrons, `energyError` = σ_z, `type` = layer (1..10), `position` mm.
- `fDST_EMCA_FEMCLayers` (CalorimeterHit) — per-layer FEMC: `energy` = layer
  energy, `type` = layer, `cellID` = n hits, `position` = shower centroid.
- `fDST_HCAL_Towers` (CalorimeterHit) — per-tower HCAL: `energy` = tower
  amplitude, `type` = layer, `cellID` = packed `LAY·10000 + JU·100 + JV`.
- `fDST_TDHA_HcalTimeHits` (CalorimeterHit) — per-layer HCAL time-digitisation
  hits: `energy` = TD energy, `type` = HCAL layer, `cellID` = 0 barrel/1
  endcap, `position` mm (barrel R/Rφ converted to x,y); no per-hit time at this
  DST level.
- `fDST_TEAD_TOFHits` (CalorimeterHit) — unassociated barrel-TOF hits
  (neutral candidates): `position` mm (R/Rφ→cartesian), `time` (ns).
- `fDST_TEAD_HOFHits` (CalorimeterHit) — unassociated forward-HOF hits:
  `position` mm; time not decoded at this DST level.
- `fDST_STIC_Showers` (Cluster) — STIC showers from the fullDST (same content
  as `sDST_SSTC_Showers`).
- `fDST_CCAL_Showers` (Cluster) — combined-calorimetry showers (the reconciled
  EMF/HPC/HAC overlap): `energy`, `position` (mm), direction `iTheta`/`iPhi`;
  `type` bit 4.

### 2.4 Pass-2 hybrid collections (`fDST_*`)

These are element-by-element copies of the corresponding `sDST_*` collection
with their cross-collection relations re-pointed onto the fullDST objects, so
the file holds two internally-consistent views (a pure-shortDST view and a
shortDST+fullDST view). Field contents are otherwise identical to the `sDST_*`
originals described in §2.2.

- `fDST_MAIN_Particles` — `tracks` now reference `fDST_TRAC_Tracks`.
- `fDST_PV_PrimaryVertex`, `fDST_PV_Vertices`, `fDST_V0_V0Candidates`,
  `fDST_PHC_PhotonConversions` — `particles` re-pointed to `fDST_MAIN_Particles`.
- `fDST_HAID_HadronID`, `fDST_MUID_MuonID`, `fDST_ELID_ElectronID`,
  `fDST_HAID_dEdx` (+ `_RecDqdx`) — `setParticle` re-pointed to
  `fDST_MAIN_Particles`.
- `fDST_EMNC_Showers`, `fDST_HCNC_Showers` — shower clones.
- `fDST_TBL_RecoToGen` — `from` re-pointed to `fDST_MAIN_Particles`.

---

## 3. Code structure

The translation logic is a library (`libdelphi_edm4hep`) of per-domain
*writer* classes over shared infrastructure; the binaries are thin harnesses.

```
delphi_edm4hep/
├── include/delphi_edm4hep/
│   │   Helix.h  CollectionWriter.h  PhdstHarness.h  BankPrefix.h
│   │   PerigeeMatch.h  TeBank.h  internal/{PaWalk,HpcPadDecoder}.h
│   ├── Event/  Truth/  Tracking/  Vertex/  Calorimeter/  Pid/   (writer headers)
├── src/   (mirrors include/; shared .cpp at top level, writers in src/<Domain>/)
└── bin/   delphi_sdst_pass.cpp  delphi_fdst_pass.cpp  delphi_bs_fit.cpp
```

Each writer subclasses `CollectionWriter`, reads one DELPHI domain, and emits
its collections; the binaries simply run the writer chain for their pass.
Cross-writer state (truth links, the tracking output, the PA→particle maps)
is threaded through a per-event `EventContext`.

### Domains

| Domain | Responsibility |
|---|---|
| **Event** | per-event scalars (run/event/fill, energies, beamspot, B field) |
| **Truth** | generator particles (LUND) and exact reco↔gen links |
| **Tracking** | charged-track helix + covariance, particles, impact parameters, TE/extrapolation TrackStates, VD hits, electron-refit tracks, the sDST↔fDST match, and the hybrid particle/vertex re-pointing |
| **Vertex** | primary-vertex chain, beamspot, official V0s, photon conversions |
| **Calorimeter** | EM/HCAL/STIC/combined showers (condensed sDST + per-pad/per-tower fullDST), TOF/HOF hits, and the shower hybrid |
| **Pid** | dE/dx, muon/electron/hadron ID, RICH, π⁰, TOF, and the PID hybrid |

### Shared infrastructure

| Unit | Role |
|---|---|
| `PhdstHarness` | PHDST init + event loop; `(run,event)` matching for pass 2; podio I/O |
| `CollectionWriter` | writer base class + `EventContext`; builds canonical collection names |
| `pawalk` | PA-bank chain walk (`lphpa` / `iphreq` / `forEachPA`) |
| `BankPrefix` | the `<source>_<BANK>_<ReadableName>` naming table |
| `PerigeeMatch` | binds a fullDST PA to its shortDST track by perigee geometry |
| `TeBank` | decodes the variable-length PA.TE* track-element bank |
| `HpcPadDecoder` | unpacks HPC PXHGET pad words |
| `Helix` | track-parameter conversion (below) |

### `Helix` — track-parameter conversion

`delphi_edm4hep::Helix` is the single value type for DELPHI ↔ EDM4hep track
parameters. Named factories convert *into* the canonical EDM4hep helix basis
`(D0, phi, omega, Z0, tanLambda, time)` + 6×6 covariance; accessors convert
*out*:

```cpp
Helix::fromPerigee(d0,z0,theta,phi,1/R, weightMatrix)   // PA.TRAC / PA.ELTR
Helix::fromTrackElement(c1,c2,c3,theta,phi,1/P, invPt, cov, q, B)  // PA.TE* / PA.TRAX
Helix::fromHelix(D0,phi,omega,Z0,tanLambda)
   -> .params() / .cov() / .momentum(B,q) / .toTrackState(location)
```

with `omega = kOmega · q · B · (1/|p_T|)` (the transverse curvature), `kOmega =
2.99792458e-4`. The TE bank momentum word is `1/|p_T|` or `1/|p|` per its descriptor,
so `fromTrackElement` takes an `invPt` flag and divides by `sin(theta)` in the `1/|p|`
case; the perigee path and `momentum()` treat `omega` as curvature too, so all are
consistent. The covariance is a Jacobian push-forward (`J · C · Jᵀ`). The header is public
so analysis code can convert track parameters (and recover momentum from
`omega` given B and charge) without running the converter. Raw bank *parsing*
(`TeBank`, `HpcPadDecoder`) is separate and feeds the factories.

### `delphi_bs_fit`

Standalone tool (pure podio/ROOT) over the converter output. Groups
`sDST_PV_PrimaryVertex` positions by run, takes a Tukey-biweight robust mean
as the beamspot **centre** (uncertainty shrinks as 1/√N), keeps the physical
beam **width** from the per-event beamspot parameters, and writes one line per
run. This re-derives a self-consistent beamspot for data/MC closure; it is a
companion to `sDST_BSP_BeamSpot` and does not replace it. Run it once per
sample (data and MC separately).

---

## 4. Scope

The converter emits DELPHI-original bank values. In-converter algorithms that
synthesise non-bank quantities (alternative vertex finders, a second
particle-flow, empirical covariance rescaling, shower-shape moments) are not
applied here; where a downstream recipe is useful it is provided as a separate
tool (e.g. `delphi_bs_fit`) beside the original collection. Event-level summary
banks without a clean EDM4hep type (jets, trigger, b-tag, run quality) and a
few rare/forward per-PA modules are not currently emitted.
