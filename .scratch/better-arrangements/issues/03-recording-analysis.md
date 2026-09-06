# Match recordings conservatively and measure their actual boundaries

Status: resolved
Type: task
Blocked by: none

Implement the [recording and analysis contract](../spec.md#recording-and-analysis-contract). Offline metadata/generated-audio work is unblocked. Live source use depends on the evidence from ticket 01.

## Work

- Separate candidate eligibility/ranking from download I/O. Preserve artist and version evidence; apply the spec's duration, score and ambiguity thresholds even to a single result. Remove karaoke/view-count preferences. Return structured uncertainty/failure reasons.
- Add and lock a compatible librosa version; replace the custom loader/resampler, tempo and chroma calculations. Keep existing yt-dlp/cookie handling where applicable.
- Extract bounded trajectories and intro/body/outro summaries with per-measurement evidence. Retain silence/fades at the playback boundary. Unknown tempo/key stays unknown; it must not become a default estimate or discard otherwise useful measurements.
- Persist matching provenance and versioned feature records. Invalidate old cache entries; share recording work across duplicates. Use atomic checkpoints and two concurrent full-recording tasks initially. Clean temporary audio and retain read-only cookie behavior.
- Record extraction time and peak memory on generated short, typical and 20-minute inputs, plus warm-cache behavior. Do not promise a cold-playlist latency based on these synthetic timings alone.

## Acceptance

Add compact `unittest` cases with generated audio and metadata fixtures. Reproduce and prevent the 440 Hz pitch-bin and duration-dependent resampling-amplitude errors. Cover distinct endings, silent/short audio, half/double tempo ambiguity, rejected variants, a lone poor candidate, ambiguous top candidates, missing duration/artist evidence, invalid cache versions and duplicate-work reuse.

Repeated analysis of an unchanged recording uses the cache; changed source/version metadata invalidates it. No copyrighted recordings or credentials enter fixtures. Run `task check` and `git diff --check`, including existing cookie tests.

## Comments

2026-09-06: Librosa is a justified new dependency because it replaces existing faulty DSP routines and supplies the segment features this plan needs. No ML dependency is planned.

2026-09-06: Claimed at the owner's request. Implement and benchmark with generated audio and mocked source metadata/downloads. Integrated live source use remains unverified under ticket 01's outcome.

## Answer

2026-09-06: Implemented with librosa 1.0.0, locked for the current Python 3.13/NumPy environment. [Audio measurements](../../../api/audio_analysis.py) are independent of service I/O; [playlist_sorter.py](../../../api/playlist_sorter.py) owns matching, downloads, cache checkpoints and ordering. Librosa includes its declared transitive dependencies; no learned model is used.

The resolver retains title, credited-artist and version evidence, rejects duration/variant mismatches, and applies the 0.85 score and 0.10 margin even to a single result. Karaoke and view-count preferences are removed. After an accepted source fails, only that candidate is removed and the remaining ranking must independently clear both checks before retrying. Initial ambiguity never triggers downloads. Uncertain, failed and overlong recordings return distinct status/reason values and remain visible in fixed positions.

The extractor streams native audio through librosa into one 22,050 Hz mono buffer, then discards bounded thirty-second spectrograms after keeping compact frame measurements. It stores five-second trajectories plus the real first/final fifteen seconds, body and whole-recording summary. Leading/trailing silence is retained. A missing body stays absent. The twenty-minute cap is checked before analysis and against the decoded file.

Per-measurement evidence accompanies level, onset activity, tempo candidates, texture, chroma and optional Camelot labels. The generated A-tone and resampling-level regressions now pass. Silence, tiny inputs and aperiodic noise do not receive default tempos; a single pitch does not receive a major/minor key. Missing key/BPM does not hide otherwise analyzed entries. The current score blends uncertain key/tempo terms toward a neutral value. The full directed objective remains ticket 04 work.

The cache now carries schema, resolver and extractor versions, settings, exact input metadata, source evidence and a source-record fingerprint. It ignores unversioned/incompatible entries and shares work across duplicate occurrences. Ten successful results trigger an atomic checkpoint, and completed results are saved on interrupted progress as well. Playlist-relative intensity is derived from raw level/activity without mutating cached measurements; missing activity stays neutral. API counts distinguish cached occurrences from unique recordings. Two recording tasks run concurrently.

Validation: `task check` passed with 14 offline tests, lint/types and the frontend production build. The SDK probe and `git diff --check` passed. Generated audio/metadata tests cover real boundaries, short/silent/noisy audio, tempo alternatives, wrong/ambiguous recording candidates, fallback download rules, old metadata/source/version cache rejection, duplicate-work reuse, interrupted checkpoints and atomic replacement failure. Existing cookie, session, preview and interrupted-save regressions remain passing. Browser checks passed at 1280px light and 390px dark with keyboard navigation, reduced motion and zero axe WCAG A/AA violations.

Measured generated-file results, excluding downloads and initial library warm-up:

| Duration | Decode plus extraction | Warm cache | Peak process memory |
| --- | --- | --- | --- |
| 2 seconds | 0.0108 s | 0.00018 s | 272.6 MiB |
| 3 minutes | 0.5568 s | 0.00059 s | 342.1 MiB |
| 20 minutes | 3.3601 s | 0.00257 s | 535.8 MiB |

The first eager-loading implementation peaked at 1,085.7 MiB for the twenty-minute file; streaming removed that peak. [Method, environment and caveats](../../../docs/librosa-analysis-research.md#implemented-extraction-and-measured-limits), [raw measurements](../audio-benchmark.jsonl), [benchmark script](../benchmark_audio.py), [updated details screenshot](../light-1280-details.png).

Metadata still cannot prove acoustic identity, and cached sources are not polled for upstream changes. No real recording corpus, live media download or Spotify mutation was used for this ticket. Ticket 01's external permission/access questions remain open. Next frontier: ticket 04.
