# SKELANA-free converter design

The production `delphi_sdst_pass` and `delphi_fdst_pass` executables no longer
call `PSINI`, `PSBEG`, or any other SKELANA entry point. Both link through the
DELPHI archive group that deliberately omits `libskelanaxx`.

The native Code4hep `DelphiSource` uses these same production pipelines. Its
`delphiRun` launcher also links only the archive group without
`libskelanaxx`; SKELANA is not hidden in the plugin boundary.

SKELANA remains available only as an optional, non-installed validation oracle
when configuring with `-DDELPHI_BUILD_SKELANA_REFERENCE=ON`. Its adapter is a
separate static target and is not part of `libdelphi_edm4hep`.

## Converter-owned event preparation

For every accepted PHDST record, the harness now performs this sequence:

1. `EventInfo` reads the processing tag with `DSTQID`, the DST version and
   centre-of-mass energy from the pilot record, and the field with `BPILOT`.
2. The VD package is initialized once with `VDIDST`. Beam defaults formerly in
   SKELANA's `PSCBSD` deck are supplied to `SETBS`, then `VDBSPT` provides the
   data or simulated event beamspot.
3. The stored BTAG bank is decoded directly. AABTAG recalculation calls
   `AADATA`, `AABTGS`, and `AAHEMI` exactly once with the same converter-owned
   beamspot that is written to EDM4hep.
4. For short DSTs, code-120 secondary hadronic interactions receive the same
   `MAKEMOD8(...,.FALSE.,...)` repair that `PSBEG` performed.
5. Domain writers decode the current PA/PV structures directly and publish
   converter-owned maps keyed by raw PA addresses.

`SETBS` and `MAKEMOD8` pass their arguments through old LOCB/LOCF machinery.
Their C++ call arguments therefore use persistent static storage, matching the
lifetime of the old Fortran DATA/local variables; stack-backed arguments are
rejected by the 64-bit compatibility check.

## Replacements for the SKELANA commons

- Event scalars and beamspot: direct pilot-record, `DSTQID`, `BPILOT`, and VD
  package calls.
- Tracking: direct PA `MAIN`/`TRAC` view, charged-first correspondence map,
  direct `TBDCAE` impact parameters, and C++ ports of `PSPGBM`/`PSRDCA`, track
  selection for charged tracks, primary-vertex refits, and mammoth recovery.
  Primary-vertex
  refits use the standalone DELPHI `CONFPV` and `FKMI5` services.
- Vertices, V0s, and conversions: direct PV/PA structure traversal.
- Simulation truth: direct compact/full truth-structure decoding and raw
  PA-to-simulation links.
- VD hits: direct `MVDH` decoding, grouped by PA rather than VECP slot.
- Particle identification: direct `MUID`, `ELID`, `HAID`, `PHOT`, and related
  PA modules, plus standalone dE/dx and RICH services.
- STIC: direct `STIC`/`SSTC` rows associated by PA. Wrapped SSTC azimuths use
  the shipped `PXCONS.PI` bit pattern, preserving the legacy single-precision
  result rather than substituting the one-ULP-larger C++ value.
- B tagging: direct stored-bank reader and direct AABTAG invocation.

This removes event-to-event dependence on PSC common-block contents. Raw PA
addresses are the stable relation key; transient VECP indices are retained
only where an output compatibility field needs their ordering.

Inside Code4hep, Podio Frame parameters are temporarily materialized as typed
event products because Stitched's product registry transports collections,
not Frame metadata. `PodioOutputModule` reverses that representation before
writing. This keeps the direct `DSTQID`, `BPILOT`, VD beamspot, and BTAG
configuration results as normal Podio parameters in the final file.

## Native scheduled-module migration

`DelphiEventSummaryProducer` is the first conversion calculation scheduled by
Code4hep after `DelphiSource`. The source transcribes the raw PA.MAIN charge
code into `sDST_MAIN_Particles_ChargeCode`; the producer consumes that immutable
collection and independently publishes `native_EVT_nCharged` and
`native_EVT_nNeutral`. The integration test requires those values to match the
legacy event summary. This dual-output pattern is the migration seam for moving
the remaining derived calculations out of the PHDST callback before deleting
the corresponding legacy implementation.

## Native simulation geometry migration

The authoritative DELSIM detector description is not GDML. For v94c,
`SXDDAP` selects detector/date/level records and invokes `DEFGEO` on the
readable CARGO snapshot `CERNSNAP2001_94DELSIM.ASC`. That snapshot contains
7,703 `GEOM` records and 202 `MATC` records; shape, placement, material, and
replacement directives are stored as fields such as `SHAP`, `REFR`, `MATS`,
and `REPL`.

`delphi_geometry` is the first native replacement for that path. It parses the
CARGO records, validity intervals, fields, and continuation data without any
DELPHI or CERNLIB dependency. Its typed model now validates and decodes the
material definitions, two-material assignments, all `SHA*` shape payloads,
six-value `REF*` transforms, and variable-length `REPL` paths. On the original
v94c snapshot this yields 202 materials, 7,703 geometry nodes, 5,424 material
assignments, 6,220 shapes, 4,246 transforms, and 1,506 replacement directives.
The accepted shapes are DELPHI's documented `BRIK`, `CYL*`, `DUMY`, `FORB`,
`PARA`, `PLNM`, `POL*`, `SPHE`, and `WED4` families; the typed reader rejects
unknown tags and incorrect word counts with source-line diagnostics.

`delphi_geometry_audit` exercises both lossless parsing and typed decoding on
an original snapshot. Subsequent geometry work should translate this model
into DD4hep/GDML one detector subsystem at a time and compare the result
against the DELSIM database hierarchy; it must not substitute an illustrative
detector for the database geometry.

`delphi_geometry_export` renders `/DELF.B` as a GDML cylindrical world using
the snapshot's primary `SHAP` bounds (680 cm radius and 1,170 cm total length)
and its `AIR*` material parameters. With `--beam-pipe`, it also renders the
complete `/BEA*` hierarchy: 106 source nodes, all `CYL1`, `CYL3`, and `BRIK`
components, nested shapes, material assignments, `REFR` placements, and the
`MSK1 -> MSK2` replacement with inherited insert children. DELPHI's `DXMATR`
Euler convention is converted through its rotation matrix instead of treating
the three stored angles as GDML angles. The `VACU` zero-density sentinel is
mapped explicitly to a positive Geant4 transport vacuum of `1e-25 g/cm3`.

The snapshot path is retained as GDML auxiliary provenance. Both modes reject
a missing or structurally different hierarchy instead of silently falling
back. The original v94c beam-pipe output is accepted by the Code4hep Geant4
driver at 1.2312434 T. Sensitive tracking and calorimeter volumes remain the
next detector-construction slices.

The generic Code4hep Geant4 driver now requires `magneticFieldTesla` in its
detector configuration instead of hiding a 0.1 T value in C++. It persists
that value as the `sim_detector_magneticFieldTesla` Frame parameter. For the
v94c DELSIM default, `CURRX=5001` A maps through `UFCSCL` to 1.2312434 T at the
centre. This uniform value is only the first conditions seam: faithful
simulation still requires a native port of the spatial UFIELD map.

## Validation findings

On the five-event 94C2 simulation fixture, the direct sDST output agrees with
the migration baseline exactly for particle four-vectors, tracks, QTRAC impact
parameters, detector/reconstruction metadata, vertices, generated truth, VD
hits, standard PID, PID extras, calorimeter objects, AABTAG, and their normal
relations. A freshly built optional PSBEG oracle and the production executable
produce identical detailed `podio-dump` output for all five events.

Several differences from older common-block-backed dumps are intentional
corrections rather than lost information:

- legacy `IPAST` can retain duplicate reconstructed-to-truth associations
  that cannot be produced by the current event's raw PA/ST mapping; the direct
  relation contains only raw-supported links;
- legacy RICH fields can survive in HAID slots whose current PA has no matching
  gas/liquid descriptor; direct decoding leaves those absent fields empty;
- MTPC word 10 is a bit field, including a package-private random marker, not
  decimal packing; the direct decoder extracts its documented low bytes;
- two old LVLOCK bit-1 values in the fixture are not supported by any current
  track cut and repeat the same slot's preceding-event value; the direct flag
  is recomputed from the current PA only.

For full-DST simulation, removing the rest of `PSBEG` also removes unrelated
random-number consumption between events. The first event agrees with the
whole-PSBEG oracle; later simulated beamspot draws can differ because the old
global DELPHI random stream has advanced by a different amount. Within the
direct converter, each event uses one internally consistent beamspot for VD,
AABTAG, and EDM4hep output, and repeated direct runs are deterministic.

## Build and link checks

The default build keeps `DELPHI_BUILD_SKELANA_REFERENCE=OFF`. Validation should
check both production link files for absence of `skelanaxx`, scan the binaries
for `psini_`/`psbeg_`/`pshort_`, run CTest, and exercise representative data
and simulation conversions. Reference targets may be enabled for A/B studies,
but they are never installed.
