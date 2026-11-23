# AABTAG v94c MC correction provenance

This note records the legacy DELPHI behavior used by the local 2026-08
94c data/MC b-tagging validation. It is based on the installed DSTANA source,
not on the DELPHI Open Data web catalogue or the non-authoritative
`delphi-nanoaod` conversion.

## Authoritative installed source

- Source:
  `/cvmfs/delphi.cern.ch/releases/almalinux-9-x86_64/v24072026-1/dstana/161018/src/car/aabtagxx.car`
- SHA-256:
  `c43c19d5ea32fc3c8c43990d490a6feddcab4ac5c1aec6868926fe63e1fca0ec`
- AABTAG version initialized by that source: `714` (lines 505--507).

The converter build links the installed static archive
`/cvmfs/delphi.cern.ch/releases/almalinux-9-x86_64/v24072026-1/dstana/161018/lib/libskelanaxx.a`
(SHA-256
`0664a9fa2d28c730e639de0a8b167b8d909488419aa2ddc53dc1321ba47f6004`).
The runtime logs independently report `Start of BTAG (V.7.14)` and the same
configuration described by the source below.

Line numbers below refer to that exact file and digest.

## What is hardcoded and active

- The default flags and analysis cuts are in the Fortran steering itself
  (lines 508--547). In particular, beamspot handling and impact-parameter
  resolution fixing are enabled (`IFSPOT=.TRUE.`, `IFRFIX=.TRUE.`).
- The data/MC branch is selected from the run-number sign. Positive runs use
  the data path and negative runs use the simulation path (for example lines
  670--703 and 3567--3574). Official MC inputs already encode DELPHI's
  negative-run convention; the converter preserves that run number, and the
  batch validator checks it against the selected file ID.
- For 1994 MC, AABTAG constructs a Gaussian beamspot constraint around the
  generator vertex using hardcoded widths `(0.012, 0.001, 0.710) cm`
  (lines 579--581 and 687--703). Data instead calls `VDBSPT` for the calibrated
  beamspot (lines 688--689). This is the concrete implementation behind the
  expected data/MC beamspot-domain difference.
- `BBCR94` contains processing-dependent numerical parameterizations for
  impact-parameter error correction. For MC it additionally changes the track
  parameters and adds Gaussian/tail smearing to reproduce the data resolution
  (routine beginning at line 6475). The `94C*` processing selects parameter
  set 2 at line 6577.
- The 1994 VD post-selection includes an MC-only stochastic efficiency
  correction. For the `94C*` processing the first z-pattern class uses
  efficiency `0.9231` (lines 8733--8757).

These stochastic legacy corrections mean a rerun must retain the original
AABTAG initialization and DELPHI event seeding. For MC, `AARNID` derives and
resets the random seed from the absolute run number and event number (lines
1248--1282), making the stochastic corrections event-reproducible. Reimplementing
only the final probability formula would not be equivalent.

## What is external

Track-probability lookup curves are read using `PHOPEN` from the default
DELPHI calibration area (`AAOPEN`, lines 3657--3697). AABTAG constructs a
processing-, resolution-fix-, and data/MC-specific name, then tries the
hardcoded suffix sequence `.NBS`, `.710`, `.703`, `.701`, `.612`, `.611`,
`.610`, `.606`, `.604`, `.601`, `.DAT` (`AANAME`, lines 3701--3751).

For the official v94c qqps 91.25 GeV sample, the production logs show the
earlier probes failing and the successful payload:

```text
AAOPEN - Open file of type MC:P94C2FMC.610
AAOPEN - From the default DELPHI directory
```

Thus no calibration is fetched from a website at runtime. The catalogue is
only used to define the dataset inventory; AABTAG reads its installed DELPHI/CVMFS
payload through the CVMFS environment.

The name is selected from the embedded DST processing identifier, not from the
generator or basename. A complete 3,000-event cross-generator cross-check of
the official file `kk2f4145_qqpy_91.25_1000.sdst` under
`cern/kk2f4145/v94c/91.25` reported run `-1000` and resolved the same
`MC:P94C2FMC.610` payload as the v94c `qqps` files. Both stored-bank and
recalculated conversions passed the then-current all-frame checker, all 3,000 exact event
keys joined with zero hadronic-tag mismatches, and 2,872 hadronic events had
complete paired score/thrust payloads. The all-IP event score retained a
Pearson correlation of 0.953, with mean recalculated-minus-stored shift
-0.176 and normalized-shape total variation 5.75%.

That recalculated file predates the explicit `AlgorithmInvoked`/`Valid`
contract and therefore does not pass the current checker without regeneration.

This is a complete-file generator-portability and bank/rerun closure
cross-check, not target.pdf page 13's absolute-PV reproduction or a full KK2f
campaign validation. KK2f samples reconstructed under other processing
versions must retain their own embedded processing identifier and
corresponding calibration.

## Modern-Pythia qualification

The locally generated modern-Pythia sample is structurally usable by DELSIM,
the converter, and recalculated AABTAG. Both 500-event legs passed the
then-current checker, with 481 Team-4 hadronic events; the rerun carries 9,040 track rows
with zero failures or unresolved particle indices. The stored and recalculated
ROOT files have SHA-256
`28d820c2661bf3178a9954ca7fea16f3ee974ed8acda4130e06cd4061bf2cfa3` and
`d94f0a653cc33ca8d5d0f2639f67ebddfe290f5ce690532ba57c07b1afa02508`,
respectively. Its stored bank is not an apple-to-apple closure reference
because the two legs use different legacy configurations:

The predecessor checker result is retained as historical evidence; the
recalculated file predates `AlgorithmInvoked`/`Valid` and is not a
current-schema validation product.

| leg | AABTAG | processing | `IFRFIX` | calibration |
|---|---|---|---|---|
| stored DELSIM/DELANA bank | v7.12 | 94C | false | `MC:P94CMC.606` |
| conversion-time rerun | v7.14 | 94C2 | true | `MC:P94C2FMC.610` |

For the 481 selected events, the bank/rerun event-score correlations are
0.663 (all), 0.585 (positive), and 0.599 (negative), while the corresponding
coarse normalized-shape total variations are 4.78%, 4.37%, and 4.57%. The
recalculated-Pythia versus official-KK2f shape comparison is also diagnostic:
the negative-event shape is close (TV 3.88%), whereas positive/all-event
shapes differ materially (TV 21.43%/18.65%) for 481 versus 2,872 selected
events. The metrics JSON has SHA-256
`d643d54b76296f545c5d15eb668a89553ebf6fdf40593a3a819bca8dbacd4f33`.

The observed bank/rerun movement is therefore a configuration comparison, not
evidence of Pythia generator corruption or filename-based calibration routing.
A bank-closure test would require both legs to be produced with the same
AABTAG version, processing identifier, correction flags, and calibration.
This structural check also does not supply the absolute `zPV`/`rhoPV`
validation with Pythia 8 and the plotted selection shown on target.pdf page 13.

## Present but inactive default

The source contains heavy-hadron lifetime scale constants (lines 609--616),
but their controlling default is `IFTCOR=.FALSE.` (line 510). The campaign
logs confirm that value. They are therefore not an active correction in this
rerun unless a user explicitly overrides the legacy default.

## Validation consequence

The full validation keeps three questions separate:

1. structural correctness of every converted file and every event;
2. closure of rerun AABTAG against the stored legacy BTG probabilities;
3. data/MC distribution agreement after the active legacy MC tuning above.

A residual data/MC beamspot difference is a known domain difference, not by
itself a conversion failure. It remains an explicit diagnostic in the target
plots and summaries.
