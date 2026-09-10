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

The generic writer also supports the complete 81-node `/TPC*` hierarchy.
DELPHI `POL6` endplate sectors are reconstructed from the three radial edges
defined by `DLPOL6` and emitted as closed twelve-vertex tessellated solids;
the two `ARM2` sensing media (`ARC0` and `ARC1`) are tagged as step-preserving
Code4hep tracker-sensitive volumes with DELPHI's `TPCSTP=1` wire-spacing
transport limit: the calibrated `WSPTPC=0.4 cm` makes the effective maximum
step 0.4 cm. The original v94c beam-pipe
plus TPC output is accepted by the Code4hep Geant4 driver at 1.2312434 T and
produces persistent step-level physical tracker hits in the controlled
one-muon transport test.

`TpcReadoutGeometry` is the first native digitization service. It reads the 16
pad-row `LOCC`/`SIZC` calibration records and all 12 measured sector transforms
from that snapshot. Its pad locator reproduces `STAMPA`'s one-centimetre row
window, 60-degree sector coordinates, Fortran truncation, and asymmetric
zero-angle pad boundary. For v94c the audit requires 1,680 pads per sector,
20,160 pads in total, and a successful centre-pad round trip through every
aligned sector transform.

`DelphiTpcPadMapperProducer` schedules that service after `G4SimProducer`. It
consumes step-level `SimTrackerHit` objects, applies the calibrated sector and
row window, and publishes persistent `TrackerHit3D` pad hits with an explicit
endcap/sector/row/pad cell ID. This establishes the deterministic simulation to
readout boundary.

`TpcPadResponse` is the next deliberately framework-independent layer. It
reproduces STAMPA's deterministic induction onto the central pad and its two
neighbors on either side. The response width uses the v94c `STSPRF` constants,
the measured row pitch, drift distance, local track incidence, and DELPHI's
Lorentz-angle term. The drift half-length is read from the selected sector
geometry rather than duplicated as steering configuration. The returned signal
retains caller-defined units because the preceding primary-ionization and
Landau-fluctuation model has not yet been ported. Drift diffusion, time-bin
shaping, calibration-dependent pedestal noise, thresholds, and FADC response
also remain before claiming legacy digitization equivalence.

`TpcDigitizationConditions` now decodes the corresponding CARGO calibration
records without the legacy database runtime. It reads the global high voltage,
minimum-ionizing dE/dx and mean-pad-amplitude normalizations, both endcap drift
velocities, and the packed two-bit gate state for every physical sector. The
v94c audit fixes these values at 25,306 V, 254.5, 652.8, 6.998 cm/us, and
7.002 cm/us. It also decodes all 20,160 packed per-pad `CALP` records into
pedestal, low/high range slopes, gain ratio, crossover signal, electronics
channel, and status. This preserves STCALB's row-to-crate permutation, closed-
gate correction, and historical 0.494-to-4.94 database repair. The v94c audit
finds 736 nonzero pad statuses and a gain-ratio range of 4.052--5.286.

`TpcTimeResponse` ports the deterministic part of STDIPW: longitudinal
diffusion, track-step broadening, electronics shaping, the 73.82 ns clock,
13-bin sampling window, baseline term, and asymmetric pulse shape. Its two
truncated-Gaussian inputs are explicit arguments, so a scheduled digitizer can
own and seed the random stream without hiding global Fortran RNG state. FADC
noise, saturation, threshold clustering, and EDM4hep `TimeSeries` publication
remain to be connected.

`TpcFadc` ports STFADC's two-range calibrated conversion, common and
per-sample pedestal fluctuations, integer truncation, and 8-bit saturation.
Its zero-suppression step preserves STODIG's 20-count pad threshold, two past
samples, two future samples, five-below-sample closure, and 20-cluster limit.
As with the pulse shaper, Gaussian draws are inputs rather than hidden global
state.

`DelphiTpcDigitizerProducer` connects these services as a scheduled Code4hep
module. It converts Geant4 energy deposition using STDEDX's 20 eV/electron and
STLAND's 0.016 avalanche scale, applies Fano and avalanche fluctuations from a
run/event-derived local seed, aggregates every contribution by pad and time
bin, calibrates and zero-suppresses the result, and publishes surviving EDM4hep
`TimeSeries` waveforms. Two repeated controlled runs produce bit-identical
waveforms. Geant4 already supplies energy-loss fluctuations, so this path does
not also sample the legacy ETDEDX histogram. Exact physics closure still needs
comparison against DELSIM's track labels; native wire assignment and the
STDEDX/STLAND adjacent-wire leakage are now present, while those truth labels
must then be represented by a suitable EDM4hep truth-link collection.

`DelphiTpcHitReconstructionProducer` is the first native reconstruction module
on that output. For each zero-suppressed waveform it finds the peak sample,
converts drift time to z with the appropriate measured endcap velocity, places
the hit at the calibrated pad centre, propagates pad and time-bin dimensions to
a position covariance, and carries the channel status into hit quality. It
publishes ordinary EDM4hep `TrackerHit3D` objects for the later pattern-
recognition and track-fit stages; ADC amplitude is deliberately not mislabeled
as an energy deposit.

The snapshot path is retained as GDML auxiliary provenance. All modes reject a
missing or structurally different hierarchy instead of silently falling back.
Fine-grained TPC pad response and the other sensitive tracking and calorimeter
volumes remain subsequent detector-construction and digitization slices.

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
