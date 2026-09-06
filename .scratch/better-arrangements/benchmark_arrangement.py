"""Benchmark deterministic generated section data, without audio or service I/O."""

import json
import os
import platform
import resource
import sys
import time
from unittest.mock import Mock

import numpy as np

from app.playlist_sorter import SpotifyPlaylistSorter

count = int(sys.argv[1])
rng = np.random.default_rng(42)
sorter = SpotifyPlaylistSorter("benchmark", Mock())
for i in range(count):
    key = str(i)
    sorter.original_items.append({"id": key, "occurrence": f"snapshot:{i}", "original_position": i,
                                  "Track": f"Generated {i}", "fixed_reason": "Fixed" if i % 23 == 17 else None,
                                  "artist_ids": [f"artist-{i // 3}", f"featured-{i % 17}"]})
    analysis = {}
    for part in ("intro", "outro", "body", "summary"):
        chroma = rng.random(12)
        analysis[part] = {"tempo": float(rng.uniform(70, 180)), "rms_db": float(rng.uniform(-40, -7)),
                          "onset": float(rng.uniform(0, 10)), "centroid": float(rng.uniform(500, 4000)),
                          "contrast": rng.uniform(5, 30, 7).tolist(), "chroma": (chroma/chroma.sum()).tolist(),
                          "evidence": {key: float(rng.uniform(.4, 1)) for key in ("tempo", "rms_db", "onset", "centroid", "contrast", "chroma")}}
    sorter.audio_features[key] = {"analysis": analysis}
sorter.current_order = [entry["occurrence"] for entry in sorter.original_items]
first, last = sorter.current_order[3], sorter.current_order[-4]
records = []
for profile in ("smooth", "variety", "smooth"):
    start = time.perf_counter()
    order = sorter.sort_playlist(first, last, profile)
    elapsed = time.perf_counter() - start
    assert sorter.valid_order(order)
    assert order[0] == first and order[-1] == last
    result = sorter.arrangement_result
    assert result["cost"] <= result["baseline_cost"]
    assert result["evaluations"] <= 5000
    records.append({"profile": profile, "seconds": round(elapsed, 5), "cost": result["cost"],
                    "baseline_cost": result["baseline_cost"], "evaluations": result["evaluations"],
                    "assessed_edges": result["assessed_edges"]})
print(json.dumps({"entries": count, "runs": records, "python": platform.python_version(),
                  "machine": platform.machine(), "logical_cpus": os.cpu_count(),
                  "peak_process_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)}))
