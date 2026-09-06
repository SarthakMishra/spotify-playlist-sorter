"""Measure generated audio only. Run with PYTHONPATH=. uv run python ... SECONDS."""

import json
import os
import platform
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf

from app import audio_analysis, playlist_sorter

seconds = int(sys.argv[1])
sr = 44100
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "generated.wav"
    with sf.SoundFile(path, mode="w", samplerate=sr, channels=2, subtype="PCM_16") as output:
        for start in range(0, seconds, 30):
            t = np.arange(min(30, seconds - start) * sr, dtype=np.float32) / sr + start
            signal = (0.15 * np.sin(2 * np.pi * 220 * t) + 0.08 * np.sin(2 * np.pi * 330 * t)) * (0.6 + 0.4 * np.cos(4 * np.pi * t))
            output.write(np.column_stack((signal, signal)))
    audio_analysis.analyze_audio(np.zeros(audio_analysis.SAMPLE_RATE, dtype=np.float32))
    begin = time.perf_counter()
    wave, sample_rate = audio_analysis.load_audio(str(path))
    decoded = time.perf_counter()
    features = audio_analysis.analyze_audio(wave, sample_rate)
    analyzed = time.perf_counter()
    assert len(features["trajectory"]) == int(np.ceil(seconds / 5))
    json.dumps(features, allow_nan=False)
    track = {"id": "benchmark", "Track": "Generated", "Artist": "Test", "duration_ms": seconds * 1000}
    source = {"id": "abcdefghijk", "title": "Generated", "duration": seconds}
    record = {"status": "ready", "metadata": playlist_sorter._metadata(track), "source": source,
              "source_fingerprint": playlist_sorter._source_fingerprint(source), "analysis": features}
    timings = []
    with patch.object(playlist_sorter, "_CACHE_FILE", Path(directory) / "cache.json"):
        playlist_sorter._save_cache({track["id"]: record})
        sorter = playlist_sorter.SpotifyPlaylistSorter("benchmark", Mock())
        with patch.object(sorter, "_analyze_track", side_effect=AssertionError("Cache missed")):
            for _ in range(3):
                before = time.perf_counter()
                sorter._fetch_audio_features_local([track, track])
                timings.append(time.perf_counter() - before)
        assert sorter.cached_count == 2 and sorter.recording_count == 1
        cache_bytes = playlist_sorter._CACHE_FILE.stat().st_size
    print(json.dumps({"seconds": seconds, "decode_seconds": round(decoded-begin, 4),
                      "analysis_seconds": round(analyzed-decoded, 4), "warm_cache_median_seconds": round(statistics.median(timings), 5),
                      "peak_process_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                      "cache_bytes": cache_bytes, "python": platform.python_version(), "machine": platform.machine(),
                      "logical_cpus": os.cpu_count(), "analysis_version": audio_analysis.ANALYSIS_VERSION}))
