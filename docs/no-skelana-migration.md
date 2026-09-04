# Removing the SKELANA runtime dependency

This branch is an incremental migration of the DELPHI converter from SKELANA
COMMON blocks to direct DELPHI package and PHDST-bank access. Each step must
remain event-content equivalent before the next part of `PSBEG` is replaced.

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

Event, vertex, tracking-status, and AABTAG-status code no longer includes or
reads `PSCBSP`. The stored BTAG bank is decoded directly (including the old
pilot-record representation) and `PSHBTG` is no longer called by the writer.

`PSBEG` and `PSINI` are deliberately still present at this checkpoint. They
populate the remaining tracking, vertex, calorimeter, PID, truth, and
recalculated-AABTAG COMMON blocks. Consequently this branch is not yet ready to
drop `libskelanaxx` from the link line.

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

The current boundary was compared with the pre-migration converter using five
events from real 94C2 data and five events from 94C2 simulation. A detailed
decoded `podio-dump` of every collection, relation, and frame parameter was
identical for both samples. The normal CTest suite also passes; fixture-based
tests remain skipped when their external fixtures are unavailable.

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
   then repeat data/MC content-equivalence validation from a clean Code4hep
   superbuild.
