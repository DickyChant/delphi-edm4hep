# Stored BTG versus recalculated AABTAG

This note records the quantitative apple-to-apple comparison behind the
b-tagging implementation. It separates two questions that are easy to mix:

1. how much an event moves when its stored DELPHI BTG score is recalculated;
2. whether the recalculation improves the independently normalized Data/MC
   distributions.

The score throughout is

\[
s=-\log_{10}(\max(P,10^{-20})),\qquad
\Delta s=s_{\mathrm{recalculated}}-s_{\mathrm{stored}}.
\]

A positive delta therefore means that the rerun assigns a smaller probability
and a stronger tag. Events are joined within each source-file pair by the exact
`(runNumber,eventNumber,fileSeq)` key; truth is not used. Hemisphere indices
are swapped when the two thrust axes point in opposite directions.

## Historical full 1994C Data and v94c qqps campaigns

**Historical status:** the Data recalculation in this paired bundle predates
the current raw-`BadEventCode` plus `AlgorithmInvoked`/`Valid` serialization
contract and is rejected by the current all-frame checker. The affected Data
scope is 48,448 beamspot-error events on 53 tapes; on those events PSFBTG did
not call AABTGS and the raw `IBAD` snapshot is not current-event status.
Consequently, both Data/qqps tables below are retained only as a
content-addressed measurement of the earlier bank-to-rerun movement; they are
not current-head physics validation. An active current-head 429-tape Data
regeneration and all-frame scan will supersede these results. No digest or
result from that unfinished campaign is claimed here.

The input inventory is 429 Data tapes (5,756,545 event occurrences) and 166
official qqps files (488,468 events). The table uses the Team-4 hadronic tag
and only events with complete probability triplets and thrust payloads:
1,390,351 Data events and 467,290 MC events. Counts, correlations, means,
MAE/RMSE, and binned shape distances are exact. Quantiles are deterministic
100,000-entry reservoir estimates.

| sample | observable | entries | Pearson r | mean delta s | median abs(delta s) | 95% abs(delta s) | MAE | RMSE | shape TV |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Data | negative-IP event | 1,390,351 | 0.708 | +0.057 | 0.117 | 0.789 | 0.222 | 0.370 | 4.47% |
| Data | positive-IP event | 1,390,351 | 0.951 | +0.301 | 0.186 | 2.064 | 0.502 | 1.106 | 4.17% |
| Data | all-IP event | 1,390,351 | 0.952 | +0.285 | 0.166 | 1.778 | 0.447 | 1.000 | 5.35% |
| qqps MC | negative-IP event | 467,290 | 0.572 | +0.013 | 0.170 | 0.962 | 0.287 | 0.450 | 1.43% |
| qqps MC | positive-IP event | 467,290 | 0.952 | -0.162 | 0.253 | 2.232 | 0.569 | 1.089 | 1.99% |
| qqps MC | all-IP event | 467,290 | 0.951 | -0.158 | 0.226 | 2.097 | 0.526 | 1.026 | 2.12% |

`shape TV` is one half of the L1 distance between separately unit-normalized
80-bin score histograms over 0--20, including underflow and overflow. It is a
bulk-shape diagnostic, not an eventwise metric.

The corresponding hemisphere results are:

| sample | observable | entries | Pearson r | mean delta s | median abs(delta s) | 95% abs(delta s) | MAE | RMSE | shape TV |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Data | negative-IP hemisphere | 2,780,702 | 0.703 | +0.053 | 0.086 | 0.790 | 0.201 | 0.366 | 4.35% |
| Data | positive-IP hemisphere | 2,780,702 | 0.936 | +0.188 | 0.131 | 1.435 | 0.366 | 0.837 | 3.80% |
| Data | all-IP hemisphere | 2,780,702 | 0.939 | +0.176 | 0.126 | 1.271 | 0.331 | 0.765 | 4.28% |
| qqps MC | negative-IP hemisphere | 934,580 | 0.578 | +0.022 | 0.145 | 0.945 | 0.266 | 0.440 | 2.58% |
| qqps MC | positive-IP hemisphere | 934,580 | 0.937 | -0.080 | 0.203 | 1.649 | 0.441 | 0.852 | 2.55% |
| qqps MC | all-IP hemisphere | 934,580 | 0.936 | -0.085 | 0.193 | 1.561 | 0.418 | 0.808 | 1.95% |

The positive/all-IP event ordering is strongly retained, but the tails move by
order-one score units. Negative-IP correlations are lower even though their
mean shifts and shape distances are small: those scores occupy a narrow range,
so modest event-by-event reshuffling has a large effect on Pearson r.

Within this historical bundle, Data moves toward stronger tags on average
while qqps MC moves toward weaker tags. The exact all-event cut fractions from
the paired ROOT histograms, including underflow and overflow in the totals,
make the scale of that movement concrete:

| sample | score cut | stored bank | recalculated | change |
|---|---:|---:|---:|---:|
| Data | score >= 3 | 12.52% | 14.70% | +2.17 percentage points |
| Data | score >= 5 | 7.37% | 9.18% | +1.80 percentage points |
| qqps MC | score >= 3 | 15.30% | 14.13% | -1.17 percentage points |
| qqps MC | score >= 5 | 10.17% | 8.83% | -1.34 percentage points |

Those opposite movements reduced the historical normalized Data/MC
total-variation distance from 3.45% to 1.47% for the all-IP event score. This
is useful evidence that the rerun can improve closure without being
bit-identical to the stored score, but it remains a historical result pending
the current-head regeneration.

## Official KK2f cross-check

One complete official v94c KK2f file provides an independent 3,000-event
generator check. Both stored-bank and recalculated conversions passed the
then-current all-frame validation; 2,872 hadronic events have complete paired
payloads. The recalculated file predates `AlgorithmInvoked`/`Valid`, so these
numbers are historical until that file is regenerated and passes the current
contract checker.

| observable | Pearson r | mean delta s | median abs(delta s) | MAE | RMSE | shape TV | max CDF distance |
|---|---:|---:|---:|---:|---:|---:|---:|
| negative-IP event | 0.579 | +0.011 | 0.167 | 0.282 | 0.441 | 2.65% | 1.57% |
| positive-IP event | 0.956 | -0.183 | 0.259 | 0.569 | 1.061 | 5.71% | 1.74% |
| all-IP event | 0.953 | -0.176 | 0.227 | 0.524 | 1.016 | 5.75% | 1.78% |

This reproduces the qqps pattern: high positive/all-IP event correlation,
lower negative-IP event correlation, small normalized cumulative-shape
movement, and a mild weakening of the MC positive/all-IP tag on rerun.

## Modern-Pythia qualification

The locally generated modern-Pythia detector sample is valid input to DELSIM,
the sDST converter, and recalculated AABTAG. Its stored bank is **not** an
apple-to-apple reference: DELANA writes it with AABTAG V7.12, Processing 94C,
and `MC:P94CMC.606`, while conversion-time recalculation uses AABTAG V7.14,
Processing 94C2, and `MC:P94C2FMC.610`. A lower bank/rerun correlation there is
therefore a configuration comparison, not evidence of generator corruption or
filename-based calibration routing.

This sample likewise predates the explicit invocation/validity schema. Its
physics/configuration comparison is retained, but its earlier checker PASS is
not current-schema validation.

## Local content-addressed evidence

The historical four-way report was produced in the local FCCAnalyses checkout
whose origin was `https://github.com/DickyChant/FCCAnalyses.git`, branch
`hadron_tagging_dev_modern`, at base HEAD
`5b607b27b89f8ca3ceee0e701ead22caa9f6166a`. The relevant tooling was
untracked at that commit, so the commit alone does not contain or reproduce
it. The evidence is therefore deliberately described as local and
content-addressed. Its tool SHA-256 digests were:

| local tool | SHA-256 |
|---|---|
| `plot_btag_legacy_closure_streaming.py` | `12243ba513123be482cedf468d8b625f45ac5d370e1edb64d9eb68265e66a7af` |
| `plot_btag_legacy_closure.py` | `90ca5d21c1bfcc31cf6f45ded44c7f55440c6fdbeb2e3d19438e5ba2ce9c8d06` |
| `run_btag_legacy_closure_full.sh` | `1f18fcaa033e6bfff1666353f02c016269797f03fec08914c9893fedcc199e48` |
| `render_btag_legacy_closure_from_root.py` | `d7e746318bbc92a6a64be805f9cd9a4de297c4719a73112025d7cd8fdc74fd29` |
| `test_render_btag_legacy_closure_from_root.py` | `a7184443c9268c8d5c623c5015243e9ca77d5c14c4e07b50d8428853fb936aeb` |
| `run_btag_legacy_closure_postrender.sh` | `62b3cc4161f927dc16caf96d83ffce6ae56c172497e80e96257bd576e516f2ed` |

The exact payload command recorded in `provenance.txt` was:

```text
python3 /home/sqian/Codes/delphi_stuffs/FCCAnalyses/examples/FCCee/flavour/hadron_tagging/plot_btag_legacy_closure_streaming.py --data-pairs-manifest /home/sqian/Codes/delphi_stuffs/FCCAnalyses/outputs/btag_legacy_closure_full_429data_166mc/data_pairs.tsv --mc-pairs-manifest /home/sqian/Codes/delphi_stuffs/FCCAnalyses/outputs/btag_legacy_closure_full_429data_166mc/mc_pairs.tsv --selection hadronic --quantile-reservoir-size 100000 --output-dir /home/sqian/Codes/delphi_stuffs/FCCAnalyses/outputs/btag_legacy_closure_full_429data_166mc
```

The ignored local `summary.json` had SHA-256
`f855df54729b868c73077ffcc9cbf7530eb61373ff15bced5453e87d6619434e`,
and the paired ROOT histogram bundle had SHA-256
`25c8af9b32a5c93304b93d0a25b77362717521f39b0d45fdfb407e4cd12bc5db`.
The supporting `provenance.txt`, `run.log`, and `render_manifest.json` had
SHA-256
`3129113f1ecc967eea5f73e2d5ac93d986a096e6f96c2abba73403ce33f9f2ac`,
`cba1d9a4cbaf1513d8ee068a56c4cff09fc67a66654490acae5e0f481cf25886`,
and `bcb1ead307081978bea2710faea23fef39e4e6d8159f69c1e78e72e0d0b948c2`,
respectively.
The source-pair manifests had SHA-256
`4fc1dfdc4171083cd680197b76a47f9926929a964d4c2728eeb207a7bf331145`
(Data) and
`e78ce30181dd20db54c9287770deb070822c8c9c43a817f88be7c8e2170981ad`
(MC). These large campaign products are deliberately not committed.

The official-KK2f metric record had SHA-256
`166ba0d5a033cdec905cfaf0b120d7d727a12a0730b7549b1b917024320c214d`.
The official KK2f ROOT legs had SHA-256
`51f3c1258f24912d22a4dd1272ceca3f692a65800fe4e50c20a9702216670994`
(recalculated) and
`ac8e77a92c8ad6cd09ea539f7cd4e93413d92c7d3f9c65710fa2951d10f68a38`
(stored bank).
