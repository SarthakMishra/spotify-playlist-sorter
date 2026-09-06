# Arrangement validation and benchmarks

Checked 2026-09-06 for [ticket 04](../.scratch/better-arrangements/issues/04-arrangement-objective.md).

The arranger compares real outro/intro measurements and includes artist repetition and five-entry monotony. Smooth uses weights 0.80/0.15/0.05; More variety uses 0.60/0.25/0.15. The progression term is disabled. Each term is bounded and normalized as specified in the [objective contract](../.scratch/better-arrangements/spec.md#arrangement-contract).

Normalization uses trusted intro, outro, body and summary measurements from each unique eligible recording. All candidates share those bounds. Fixed entries contribute neutral audio edges; artist metadata can still establish repetition involving them. Assessed-edge counts mean that at least one component has nonzero evidence at both endpoints. They are not a listener-confidence score.

The implementation starts with the original order adjusted to satisfy endpoint pins while preserving the relative order of other movable entries. It evaluates up to four deterministic greedy starts, picks the best seed, then improves it using swaps and relocations in both directions. Moves fill only free slots, preserving fixed entries and endpoint choices. The two-pass improvement loop shares a 5,000-candidate budget with the initial seeds. Equal costs keep the feasible original. Exhausting a budget is not proof of global optimality.

Pair matrices are reused across profiles for the current analysis/scoring version. Each profile retains only its latest result and choices. A playlist exceeding 1,000 entries receives its complete feasible baseline with an explicit limited-search state and uncomputed objective/coverage values. No entries are truncated.

## Measurements

The [reproduction script](../.scratch/better-arrangements/benchmark_arrangement.py) uses deterministic generated section features, credited artists and fixed entries. It makes no service calls and performs no audio extraction. Both first/last pins and every fixed slot are asserted, along with occurrence preservation, objective no worse than baseline, and the evaluation cap.

Each playlist size ran in a separate process on Python 3.13.15, x86_64 Linux, with 32 logical CPUs. The first Smooth run includes normalization, matrix construction and search. More variety reuses matrices but runs its own search. Repeated Smooth reuses its result. Times exclude imports and fixture generation. These are individual observed runs, not latency guarantees or a public-load test.

| Entries | Smooth, including preparation | More variety, reusing matrices | Repeated Smooth | Peak process memory |
| --- | --- | --- | --- | --- |
| 100 | 0.12868 s | 0.11678 s | 0.00003 s | 96.8 MiB |
| 500 | 0.28756 s | 0.20141 s | 0.00012 s | 180.3 MiB |

Both sizes met the proposed two-/five-second targets. Both profiles used 5,000 evaluations on these fixtures and stayed below their respective feasible-baseline cost. The 100-entry sequence had 91 assessed edges out of 99; the 500-entry sequence had 457 out of 499. Fixed entries remained in every candidate and final result. [Raw measurements](../.scratch/better-arrangements/arrangement-benchmark.jsonl).

Run from the repository root:

```bash
PYTHONPATH=. uv run python .scratch/better-arrangements/benchmark_arrangement.py 100
PYTHONPATH=. uv run python .scratch/better-arrangements/benchmark_arrangement.py 500
```

## Correctness and product limits

Offline tests verify directed boundaries, half/double tempo, confidence blending, neutral missing measurements, constant-feature monotony, a hand-calculated AAABBB objective, featured-artist overlap, duplicate spacing, fixed endpoints, invalid pins, deterministic ties and large-playlist fallback. HTTP tests verify optional choices, profile validation, revision binding, unchanged-order save rejection and that switching styles does not repeat audio analysis.

Browser checks cover both styles, clearing optional choices, conflicting pins, fixed endpoints, selection of a specific duplicate, keyboard tabs/save, identical-profile results and unchanged results. They run at 1280px light and 390px dark with reduced motion and axe checks, using simulated asynchronous API responses throughout.

Lower objective cost establishes the search's behavior, not listener preference. Source access, recording identity, objective calibration and the listening pilot retain their separate requirements. Ticket 05 will improve the review narrative and elapsed-time comparisons using the returned component costs and evidence.
