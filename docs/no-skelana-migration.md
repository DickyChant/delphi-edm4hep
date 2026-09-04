# Removing the SKELANA runtime dependency

The converter is being moved, step by step, from SKELANA COMMON blocks to
direct DELPHI package and PHDST-bank access (issue #19). Each step must remain
event-content equivalent before the next part of `PSBEG` is replaced.

## Current boundary

The converter now owns a process-global `EventInfo` service, refreshed once per
accepted PHDST event. It provides:

- the four-character processing tag from `DSTQID`;
- the DST version and centre-of-mass energy from the pilot record;
- the magnetic field and curvature factor from `BPILOT`;
- the data/MC beamspot from `VDIDST`, `SETBS`, and `VDBSPT`, including the
  `PSCBSD` defaults formerly hidden in SKELANA;
- the multiplicities, energy sums, and Team-4 hadronic flag formerly read from
  `PSCEVT`.

Event, vertex, tracking-status, AABTAG-status and beam-spot-status code no
longer includes or reads `PSCBSP`. The stored BTAG bank is decoded directly (including the old
pilot-record representation) and `PSHBTG` is no longer called by the writer.

`PSBEG` and `PSINI` are deliberately still present at this checkpoint. They
populate the remaining tracking, vertex, calorimeter, PID, truth, and
recalculated-AABTAG COMMON blocks. Consequently the converter is not yet ready
to drop `libskelanaxx` from the link line.

`PSBEAM` therefore still calls `VDBSPT` for every event, and `EventInfo` calls it
again afterwards. That second call returns the same beam spot: `VDBSPT` keeps
the result for the current event (`VDMCBS` for simulation, the same-run path of
`VDBMCA` for data), so it neither repeats the lookup nor draws new random
numbers for the simulated smear.

## Why the event sequence is load-bearing

`PSBEG` is not just a convenience wrapper. It clears many COMMON blocks, fixes
secondary-interaction tracks, establishes the PA/VECP view, and invokes
packages in a specific order. In particular, `PSBEAM` and `PSFBTG` run before
track selection and PID.

An attempted intermediate cut that disabled the two flags and called
`VDBSPT`/`AABTGS` after `PSBEG` changed MC beamspots and downstream PID. Calling
`AABTGS` twice also exposed the arbitrary thrust-axis sign by swapping the two
hemispheres. The migration must therefore replace the event orchestrator in
order, not append duplicate package calls after it.

## Validation checkpoint

The current boundary converts the five samples of the conversion-identity test
(`tests/samples.yaml`: LEP1 and LEP2, data and simulation, short, long and
extended-short DSTs) to output identical to the pre-migration converter, so
`refs.lock` is unchanged. So is the first pass over 1993 data.

One difference is intended. The writer used to call `PSHBTG` after reading the
recalculated tag, to load the stored one. For a DST version below 102 `PSHBTG`
does not read the BTAG bank: it runs `AABTGS` again and then copies the stored
tag from the `IDEN` pilot blocklet. A full DST has no `IDEN` blocklet, so it
reports version 0, and every event of the second pass ran AABTAG twice. The
event and hemisphere tags were read from the first run, the per-track words and
AABTAG's primary vertex from the second. The second run also changed the next
event's first run, so the values read from it, the event tags and the AABTAG
track states, differ too; the thrust axis can flip and the two hemispheres
swap. `BtagInfo` now reads the stored tag from the `IDEN` blocklet itself, so
AABTAG runs once per event, as in `PSBEG`.

On a two-pass conversion of LEP2 simulation (`207_cern_a0u`, run -20281: xshort
`EE1086.16.sl` and full DST `EE1085.85.sl`, 1500 events), the first pass is
identical. In the second, the stored tag is identical and the `fDST_AABTAG_*`
output differs as described: the recalculated probabilities in 546 events, the
thrust axis in 429, the number of tracks attached to the vertex in 21.
Restoring the `PSHBTG` call reproduces the old output exactly.

## Remaining sequence

1. Extract the `PSBEG` reset and short-DST orchestration into converter-owned
   calls, retaining the original order.
2. Move the already implemented beamspot service into that sequence and pass
   its values directly to a single `AABTGS` invocation.
3. Replace the recalculated `PSCBTG` snapshot with direct `AABTGS`/`AAHEMI`
   results while preserving `NAMDST`, `IFK0ST`, and `IFRFIX` semantics.
4. Replace the remaining PSC readers domain by domain with PHDST-bank readers
   or direct package calls.
5. Keep the `MAKEMOD8` secondary-hadronic-interaction fix in the replacement
   sequence.
6. Remove `PSINI`, `PSBEG`, the SKELANA headers, and finally `libskelanaxx`,
   then repeat the data/MC content-equivalence validation.
