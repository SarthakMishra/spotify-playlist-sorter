"""Bounded audio measurements from local recordings, without network access."""

from __future__ import annotations

from contextlib import closing
from importlib.metadata import version
from typing import Any

import librosa
import numpy as np
import soundfile as sf

SAMPLE_RATE = 22050
MAX_SECONDS = 20 * 60
FFT_SIZE = 2048
HOP = 512
BOUNDARY_SECONDS = 15
MIN_TEMPO_SECONDS = 2
MIN_ONSETS = 3
MIN_BPM, MAX_BPM = 40, 240
MIN_PERIODICITY = 0.25
TEMPO_SEPARATION = 0.15
MIN_KEY_PITCHES = 3
MIN_CHROMA_WEIGHT, MIN_CHROMA_SPREAD = 0.1, 0.01
MIN_KEY_CORRELATION, MIN_KEY_MARGIN = 0.6, 0.1
SILENCE_RMS = 1e-5
SETTINGS = {
    "sample_rate": SAMPLE_RATE,
    "mono": True,
    "fft_size": FFT_SIZE,
    "hop": HOP,
    "trajectory_seconds": 5,
    "boundary_seconds": 15,
    "max_seconds": MAX_SECONDS,
    "decode_block_seconds": 5,
}
ANALYSIS_VERSION = f"librosa-{version('librosa')}-segments-3"

# Mapping from (pitch_class, mode) -> Camelot key
# pitch_class: 0=C, 1=C#, 2=D, ... 11=B  |  mode: 0=minor, 1=major
_CAMELOT_MAP: dict[tuple[int, int], str] = {
    (0, 1): "8B",
    (1, 1): "3B",
    (2, 1): "10B",
    (3, 1): "5B",
    (4, 1): "12B",
    (5, 1): "7B",
    (6, 1): "2B",
    (7, 1): "9B",
    (8, 1): "4B",
    (9, 1): "11B",
    (10, 1): "6B",
    (11, 1): "1B",
    (0, 0): "5A",
    (1, 0): "12A",
    (2, 0): "7A",
    (3, 0): "2A",
    (4, 0): "9A",
    (5, 0): "4A",
    (6, 0): "11A",
    (7, 0): "6A",
    (8, 0): "1A",
    (9, 0): "8A",
    (10, 0): "3A",
    (11, 0): "10A",
}

# Krumhansl-Kessler key profiles (C, C#, D, … B) for key detection
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def load_audio(filepath: str, duration: float | None = None) -> tuple[np.ndarray, int]:
    """Load a bounded mono recording without changing its level or trimming silence."""
    info = sf.info(filepath)
    if info.duration <= 0 or info.duration > MAX_SECONDS:
        message = "Recording duration is outside the supported range"
        raise ValueError(message)
    frames = min(info.frames, int(duration * info.samplerate)) if duration is not None else info.frames
    audio = np.empty(int(np.ceil(frames * SAMPLE_RATE / info.samplerate)), dtype=np.float32)
    position = 0
    # Integer-second blocks satisfy librosa's native/target rate alignment for any integer sample rate.
    with closing(
        librosa.stream(
            filepath,
            block_length=5 * SAMPLE_RATE,
            frame_length=1,
            hop_length=1,
            sr=SAMPLE_RATE,
            mono=True,
            duration=duration,
            dtype=np.float32,
        )
    ) as blocks:
        for block in blocks:
            audio[position : position + len(block)] = block
            position += len(block)
    audio = audio[:position]
    if not np.isfinite(audio).all():
        message = "Recording contains invalid samples"
        raise ValueError(message)
    return audio, SAMPLE_RATE


def _frame_features(audio: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    """Discard each thirty-second spectrogram after retaining compact feature rows."""
    count = max(1, int(np.ceil(max(0, len(audio) - FFT_SIZE) / HOP)) + 1)
    chunk_frames = 30 * sr // HOP
    parts: dict[str, list[np.ndarray]] = {key: [] for key in ("rms", "onset", "centroid", "contrast", "chroma")}
    previous = None
    for first in range(0, count, chunk_frames):
        frames = min(chunk_frames, count - first)
        size = (frames - 1) * HOP + FFT_SIZE
        block = audio[first * HOP : first * HOP + size]
        block = np.pad(block, (0, max(0, size - len(block))))
        magnitude = np.abs(librosa.stft(block, n_fft=FFT_SIZE, hop_length=HOP, center=False))
        power = magnitude**2
        mel = librosa.feature.melspectrogram(S=power, sr=sr, n_fft=FFT_SIZE, n_mels=40)
        log_power = librosa.power_to_db(mel, ref=1.0, top_db=None)
        onset_input = log_power if previous is None else np.concatenate((previous, log_power), axis=1)
        onsets = librosa.onset.onset_strength(S=onset_input, sr=sr, hop_length=HOP, center=False)
        parts["onset"].append(onsets[-frames:][None, :])
        previous = log_power[:, -1:].copy()
        parts["rms"].append(librosa.feature.rms(y=block, frame_length=FFT_SIZE, hop_length=HOP, center=False))
        parts["centroid"].append(librosa.feature.spectral_centroid(S=magnitude, sr=sr))
        parts["contrast"].append(librosa.feature.spectral_contrast(S=magnitude, sr=sr))
        parts["chroma"].append(librosa.feature.chroma_stft(S=power, sr=sr, tuning=0, norm=2))
    return {key: np.concatenate(values, axis=1) for key, values in parts.items()}


def _tempo(onsets: np.ndarray, sr: int) -> tuple[float | None, list[dict[str, float]], float]:
    """Retain competing periodicities and withhold estimates with weak rhythmic evidence."""
    duration = len(onsets) * HOP / sr
    peaks = librosa.util.localmax(onsets)
    if (
        duration < MIN_TEMPO_SECONDS
        or np.count_nonzero(peaks & (onsets > max(0.05, float(onsets.max()) * 0.2))) < MIN_ONSETS
    ):
        return None, [], 0.0
    window = min(384, len(onsets))
    profiles = []
    for start in range(0, len(onsets), 30 * sr // HOP):
        block = onsets[start : start + 30 * sr // HOP]
        if len(block) < window:
            continue
        # Remove the activity baseline so aperiodic noise does not look strongly rhythmic.
        block = block - block.mean()
        tg = librosa.feature.tempogram(onset_envelope=block, sr=sr, hop_length=HOP, win_length=window, center=False)
        profiles.append(tg.mean(axis=1))
    if not profiles:
        return None, [], 0.0
    profile = np.maximum(np.mean(profiles, axis=0), 0)
    bpms = librosa.tempo_frequencies(len(profile), sr=sr, hop_length=HOP)
    indices = np.flatnonzero(librosa.util.localmax(profile) & (bpms >= MIN_BPM) & (bpms <= MAX_BPM))
    indices = sorted(indices, key=lambda index: float(profile[index]), reverse=True)[:5]
    candidates = [{"bpm": float(bpms[i]), "strength": float(np.clip(profile[i], 0, 1))} for i in indices]
    if not candidates or candidates[0]["strength"] < MIN_PERIODICITY:
        return None, candidates, 0.0
    estimate = float(librosa.feature.tempo(tg=profile[:, None], sr=sr, hop_length=HOP)[0])
    chosen = min(candidates, key=lambda candidate: abs(np.log2(candidate["bpm"] / estimate)))
    if chosen["strength"] < MIN_PERIODICITY:
        return None, candidates, 0.0
    strength = chosen["strength"] * min(1.0, duration / BOUNDARY_SECONDS)
    competing = [c for c in candidates if abs(np.log2(c["bpm"] / chosen["bpm"])) > TEMPO_SEPARATION]
    if any(c["strength"] >= chosen["strength"] * 0.8 for c in competing):
        strength *= 0.5
    return chosen["bpm"], candidates, min(0.8, strength)


def _key(chroma: np.ndarray) -> tuple[str | None, float]:
    """Require several pitches and a clear profile preference before naming a key."""
    if np.count_nonzero(chroma > MIN_CHROMA_WEIGHT) < MIN_KEY_PITCHES or np.std(chroma) < MIN_CHROMA_SPREAD:
        return None, 0.0
    scores = sorted(
        (float(np.corrcoef(chroma, np.roll(profile, pitch))[0, 1]), pitch, mode)
        for pitch in range(12)
        for mode, profile in enumerate((_KK_MINOR, _KK_MAJOR))
    )
    best, pitch, mode = scores[-1]
    margin = best - scores[-2][0]
    if best < MIN_KEY_CORRELATION or margin < MIN_KEY_MARGIN:
        return None, 0.0
    return _CAMELOT_MAP[pitch, mode], min(1.0, margin / 0.3)


def _segment(audio: np.ndarray, frames: dict[str, np.ndarray], sr: int, bounds: tuple[float, float]) -> dict[str, Any]:
    """Summarize actual samples, preserving silent boundaries and missing evidence."""
    start, end = bounds
    samples = audio[round(start * sr) : round(end * sr)]
    support = min(1.0, len(samples) / sr / 5)
    rms = float(librosa.feature.rms(y=samples, frame_length=len(samples), hop_length=len(samples), center=False)[0, 0])
    times = (np.arange(frames["rms"].shape[1]) * HOP + FFT_SIZE / 2) / sr
    selected = (times >= start) & (times < end)
    audible = selected & (frames["rms"][0] > SILENCE_RMS)
    evidence = dict.fromkeys(("rms_db", "onset", "tempo", "centroid", "contrast", "chroma", "key"), 0.0)
    evidence["rms_db"] = support
    result: dict[str, Any] = {
        "start": start,
        "end": end,
        "rms_db": float(20 * np.log10(max(rms, 1e-6))),
        "onset": None,
        "tempo": None,
        "tempo_candidates": [],
        "centroid": None,
        "contrast": None,
        "chroma": None,
        "camelot": None,
        "evidence": evidence,
    }
    if selected.any():
        onsets = frames["onset"][0, selected]
        result["onset"] = float(onsets.mean())
        evidence["onset"] = support
        result["tempo"], result["tempo_candidates"], evidence["tempo"] = _tempo(onsets, sr)
    if audible.any():
        result["centroid"] = float(frames["centroid"][0, audible].mean())
        result["contrast"] = frames["contrast"][:, audible].mean(axis=1).tolist()
        chroma = np.average(frames["chroma"][:, audible], axis=1, weights=frames["rms"][0, audible])
        chroma /= max(float(chroma.sum()), 1e-9)
        result["chroma"] = chroma.tolist()
        result["camelot"], key_strength = _key(chroma)
        evidence["centroid"] = evidence["contrast"] = support
        evidence["chroma"] = support * float(np.ptp(chroma) / max(chroma.max(), 1e-9))
        evidence["key"] = support * key_strength
    return result


def analyze_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> dict[str, Any]:
    """Measure complete local audio using bounded transforms and five-second summaries."""
    if sr != SAMPLE_RATE or audio.ndim != 1 or not len(audio) or not np.isfinite(audio).all():
        message = "Expected finite mono audio at the analysis sample rate"
        raise ValueError(message)
    duration = len(audio) / sr
    if duration > MAX_SECONDS:
        message = "Recording exceeds twenty minutes"
        raise ValueError(message)
    frames = _frame_features(audio, sr)
    boundary = min(float(BOUNDARY_SECONDS), duration)
    return {
        "duration": duration,
        "summary": _segment(audio, frames, sr, (0.0, duration)),
        "intro": _segment(audio, frames, sr, (0.0, boundary)),
        "body": _segment(audio, frames, sr, (15.0, duration - 15.0)) if duration > 2 * BOUNDARY_SECONDS else None,
        "outro": _segment(audio, frames, sr, (duration - boundary, duration)),
        "trajectory": [
            _segment(audio, frames, sr, (float(start), min(start + 5.0, duration)))
            for start in range(0, int(np.ceil(duration)), 5)
        ],
    }
