# Librosa recording analysis reference

Checked 2026-09-06 for [ticket 03](../.scratch/better-arrangements/issues/03-recording-analysis.md). This note verifies library behavior and proposes extraction details. It does not establish source permission or listening quality.

## Version and compatibility

The current stable release is librosa 1.0.0, published 2026-08-11. It requires Python 3.12 or newer and explicitly lists Python 3.13 and 3.14. [PyPI release](https://pypi.org/project/librosa/1.0.0/).

Its declared requirements include NumPy >=2.1, Numba >=0.61, SciPy >=1.15, SoundFile >=0.12.1 and soxr >=1.0. The project lock resolves librosa 1.0.0, NumPy 2.5.2, Numba 0.67.0, SciPy 1.18.1, SoundFile 0.14.0 and soxr 1.1.0. Installed Numba metadata constrains NumPy to >=1.22 and <2.6, which includes this resolution. Exact resolved versions remain in `uv.lock`. [Upstream dependency declarations](https://github.com/librosa/librosa/blob/1.0.0/setup.cfg).

Local generated-audio probes ran on Python 3.13.15. A 440 Hz sine at amplitude 0.25, resampled from 44,100 to 22,050 Hz, gave RMS 0.17677668 for 0.2 seconds and 0.17677669 for 2 seconds. Both chromagrams peaked at index 9, A. These probes check the installed DSP path; they are not cross-platform certification.

Version 1.0 removes the deprecated audioread backend. Keep the downloader's existing ffmpeg conversion to a SoundFile-readable recording. The 1.0 API reference moved under `api/generated/`; older URLs can expose stale 0.11 behavior. [Release notes](https://librosa.org/doc/1.0.0/changelog.html).

## APIs and units

| Measurement | Supported call and consequence |
| --- | --- |
| Loading | `librosa.load(path, sr=22050, mono=True, dtype=np.float32, res_type="soxr_hq")` returns waveform and sampling rate. `offset` and `duration` use seconds. It does not require trimming silence. [Load](https://librosa.org/doc/1.0.0/api/generated/librosa.load.html) |
| Resampling | `librosa.resample(y, orig_sr=..., target_sr=..., scale=False)` uses soxr HQ by default. `scale=True` preserves total discrete energy by changing amplitude, so leave it false when comparing signal levels. `fix=True` returns `ceil(target_sr * len(y) / orig_sr)` samples. [Resample](https://librosa.org/doc/1.0.0/api/generated/librosa.resample.html) |
| Chroma | `librosa.feature.chroma_stft(S=magnitude**2, sr=sr, tuning=0, norm=2)` accepts a power spectrogram. Default `base_c=True` orders bins C, C#, D, D#, E, F, F#, G, G#, A, A#, B. Fixed tuning is a reproducible initial assumption; `tuning=None` estimates it. Chroma is tonal content, not a key label. [Chroma](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.chroma_stft.html) |
| Onset activity | `librosa.onset.onset_strength(S=log_power, sr=sr, hop_length=hop, center=False)` accepts a log-power spectrogram. With waveform input it builds a log-power Mel spectrogram. Reuse the existing STFT through a Mel projection to avoid recomputing it. [Onset strength](https://librosa.org/doc/1.0.0/api/generated/librosa.onset.onset_strength.html) |
| RMS | `librosa.feature.rms(y=block, frame_length=n_fft, hop_length=hop, center=False)` gives frame RMS. `S=` instead expects magnitude and reflects its analysis window. Use waveform RMS for amplitude tests. Convert to log units with an explicit fixed reference and silence floor; never normalize each recording to its own maximum. [RMS](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.rms.html) |
| Texture | `librosa.feature.spectral_centroid(S=magnitude, sr=sr)` returns Hz. `librosa.feature.spectral_contrast(S=magnitude, sr=sr)` returns seven bands by default; `linear=False` compares peaks and valleys logarithmically. Both require magnitude, not power. [Centroid](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.spectral_centroid.html), [contrast](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.spectral_contrast.html) |
| Tempo evidence | `librosa.feature.tempogram(onset_envelope=onsets, sr=sr, hop_length=hop, win_length=384)` returns local autocorrelation with 384 lag rows. The default window spans about 8.9 seconds at 22,050 Hz and hop 512. [Tempogram](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.tempogram.html) |
| Tempo estimate | `librosa.feature.tempo(tg=tg, sr=sr, hop_length=hop)` reuses that tempogram. `aggregate=None` returns per-frame estimates. Its default prior favors 120 BPM; a numerical result alone is not evidence of a beat. Retain competing autocorrelation peaks and reduce support for half/double ambiguity, short observations and weak periodicity. [Tempo](https://librosa.org/doc/1.0.0/api/generated/librosa.feature.tempo.html) |

The evidence rules above are engineering recommendations. Librosa does not return calibrated confidence for these measurements. Silence should retain valid level evidence while giving absent tonal/tempo evidence. A strong single pitch still does not establish a major or minor key.

## Bounded extraction proposal

Decode once, capped at the specified 20 minutes, as float32 mono. Process hop-aligned chunks of at most 30 seconds using one STFT per chunk. Discard magnitude and power matrices after extracting the small feature arrays. Keep the frame arrays only until first/final 15-second summaries, the actual remaining body and 5-second trajectory summaries have been computed.

Preserve overlap between neighboring chunks so frames spanning a boundary see the original samples. Use `center=False` for chunk transforms and retain the previous log-power frame for onset differences. Track sample positions explicitly. Padding internal chunk edges with silence creates false transitions; padding the final partial frame must not inflate the recorded duration. [Librosa streaming guidance](https://librosa.org/doc/1.0.0/api/generated/librosa.stream.html).

For tempo, process bounded sections of the compact onset envelope and aggregate lag evidence rather than constructing one full-recording tempogram. An initial 5-second trajectory block has less rhythm support than the 15-second intro/outro; report that difference. Avoid averaging unit chroma from almost-silent frames into a confident tonal summary. The short-recording body can be absent, and intro/outro windows may overlap when both refer to real samples.

Calculated storage examples for 20 minutes at 22,050 Hz, FFT 2048 and hop 512:

| Array | Approximate storage |
| --- | --- |
| Mono float32 waveform | 100.9 MiB |
| Full complex64 STFT | 404.1 MiB before magnitude/power copies |
| Thirty-second complex64 STFT | 10.1 MiB |
| Twenty-two float32 feature rows for the whole recording | 4.3 MiB |

These are array-size calculations, not measured process peaks. Native-rate decoding, resampling buffers, imports and two concurrent workers add memory. Benchmark actual extraction before choosing a tighter guard.

If waveform loading exceeds the pilot's measured budget, librosa 1.0 can resample within `stream`. It requires `(block_length * hop_length * native_sr) / sr` to be an integer. Set `sr` explicitly, and close the generator when stopping early. This avoids writing a custom streaming resampler. [Stream API](https://librosa.org/doc/1.0.0/api/generated/librosa.stream.html).

## Matching clarification for implementation

The initial [spec](../.scratch/better-arrangements/spec.md#match-the-recording-before-trusting-measurements) required a top score >=0.85 and runner-up margin >=0.10, then permits up to two fallback downloads that independently pass those rules. Only the current best candidate can have that margin. After a download fails, remove that candidate and reapply both thresholds to the remaining ranking before any retry. Do not remove candidates simply to escape initial ambiguity. With scores bounded to 0..1, the thresholds can make fewer than three attempts eligible. This is an interpretation to record alongside implementation, not a change to the acceptance thresholds.

## Implemented extraction and measured limits

Ticket 03 implements [audio_analysis.py](../api/audio_analysis.py) with librosa 1.0.0. The loader streams five-second native blocks through librosa's stateful resampler into one mono float32 buffer. Using one-sample frames/hops for decoding makes an integer-second block align with any integer native sample rate. Spectral analysis then uses overlapping frames in bounded thirty-second blocks and carries the previous log-power frame across blocks for onset differences. No learned model is used.

Evidence strengths are heuristics, not probabilities. Single pitches do not receive major/minor key labels; silence and generated aperiodic noise do not receive tempo estimates. The rhythm measurement removes the onset activity baseline before checking autocorrelation peaks, then retains competing tempo candidates and reduces ambiguous evidence. Short excerpts have less support. Raw level/activity measurements stay in the cache; intensity normalization happens per playlist.

The following observed results used generated 44,100 Hz stereo PCM files, Python 3.13.15, x86_64 Linux and 32 logical CPUs. Decode/extraction timing excludes file generation and initial library warm-up. Each duration ran in its own process; peak resident memory includes imports, generation buffers, decoding and analysis. Warm-cache time is the median of three loads of one cached recording used twice in the playlist. These measurements establish neither download latency nor performance across other machines or music collections.

| Generated duration | Decode | Extract | Warm cache | Peak process memory | Cached record size |
| --- | --- | --- | --- | --- | --- |
| 2 seconds | 0.0035 s | 0.0073 s | 0.00018 s | 272.6 MiB | 3,595 bytes |
| 3 minutes | 0.1518 s | 0.4050 s | 0.00059 s | 342.1 MiB | 37,302 bytes |
| 20 minutes | 0.9852 s | 2.3749 s | 0.00257 s | 535.8 MiB | 223,003 bytes |

The first implementation used eager stereo loading and reached 1,085.7 MiB on the twenty-minute fixture. Streaming decoding removed that peak. The final extractor version is `librosa-1.0.0-segments-3`. [Raw measurements](../.scratch/better-arrangements/audio-benchmark.jsonl), [reproduction script](../.scratch/better-arrangements/benchmark_audio.py).

Run a measurement from the repository root with `PYTHONPATH=. uv run python .scratch/better-arrangements/benchmark_audio.py 1200`. The script uses temporary generated files, a temporary feature cache and a mocked source analyzer. It makes no live service requests. Two-worker peak memory was not benchmarked as a separate load test.


The owner-reported uncertainty and speed investigation on 2026-09-06 revised that universal margin rule. Exact structured track, all artist credits and album agreement may pass without an upload-only runner-up margin, after the same minimum score, duration and version checks. Weaker metadata retains the 0.10 margin. [Reproduction, primary sources and validation](ytdlp-reliability-research.md) document this product correction. Audio measurement settings remain unchanged.
