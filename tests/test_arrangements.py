"""Offline arrangement checks with explicit synthetic section measurements."""

# ruff: noqa: INP001, SLF001

from __future__ import annotations

import copy
import unittest
from collections import Counter
from typing import Any
from unittest.mock import Mock, patch

import numpy as np

from api import playlist_sorter


def segment(tempo: float = 120.0, level: float = -20.0) -> dict[str, Any]:
    """Make one fully measured section for predictable cost comparisons."""
    return {
        "tempo": tempo,
        "rms_db": level,
        "onset": 2.0,
        "centroid": 1000.0,
        "contrast": [10.0] * 7,
        "chroma": [1.0] + [0.0] * 11,
        "evidence": dict.fromkeys(("tempo", "rms_db", "onset", "centroid", "contrast", "chroma"), 1.0),
    }


def fixture(count: int = 6) -> playlist_sorter.SpotifyPlaylistSorter:
    """Create distinct occurrences, with two repeated recordings and no external I/O."""
    sorter = playlist_sorter.SpotifyPlaylistSorter("test-playlist", Mock())
    sorter.original_items = [
        {
            "occurrence": f"snapshot:{i}",
            "id": "a" if i < count // 2 else "b",
            "Track": f"Song {i}",
            "original_position": i,
            "fixed_reason": None,
            "artist_ids": ["artist-a" if i < count // 2 else "artist-b"],
        }
        for i in range(count)
    ]
    sorter.current_order = [entry["occurrence"] for entry in sorter.original_items]
    sorter.audio_features = {
        key: {"analysis": {part: segment() for part in ("intro", "outro", "body", "summary")}} for key in ("a", "b")
    }
    return sorter


class ArrangementTest(unittest.TestCase):
    """Verify objective meaning, bounded search and preservation contracts."""

    def test_review_notes_use_supported_actual_boundaries(self) -> None:
        """Limit notes to three real measured neighbors and expose both coverage counts."""
        sorter = fixture(8)
        for record in sorter.audio_features.values():
            record["analysis"]["intro"]["rms_db"] = -40.0
            record["analysis"]["outro"]["rms_db"] = 0.0
        sorter.original_items[3]["fixed_reason"] = "Unavailable"
        order = sorter.sort_playlist()
        transitions = sorter.get_transition_analysis(order)
        review = sorter.review_summary(order, transitions)
        assert review["total_edges"] == 7
        assert review["original_assessed"] == 5
        assert review["suggested_assessed"] == 5
        assert len(review["highlights"]) == 3
        for note in review["highlights"]:
            boundary = transitions[note["index"] - 1]
            assert boundary["score"] is not None
            assert note["track1_occurrence"] == boundary["track1_occurrence"]
            assert note["track2_occurrence"] == boundary["track2_occurrence"]
            assert "Intensity drops" in note["text"]
        neutral: dict[str, Any] = {
            "energy_diff": None,
            "components": dict.fromkeys(playlist_sorter._COMPONENTS, 0.25),
            "evidence": dict.fromkeys(playlist_sorter._COMPONENTS, 0.5),
        }
        assert playlist_sorter._audio_note(neutral) is None
        neutral["energy_diff"] = 0.8
        neutral["evidence"]["intensity"] = 0.1
        assert playlist_sorter._audio_note(neutral) is None
        sorter.arrangement_data = None
        limited = sorter.review_summary(order, transitions)
        assert limited["original_assessed"] is None
        assert limited["suggested_assessed"] is None
        assert limited["highlights"] == []

    def test_direction_tempo_ambiguity_and_unknown_evidence(self) -> None:
        """Ending-to-beginning direction matters; missing data never looks like a perfect fit."""
        sorter = fixture(2)
        sorter.audio_features["a"]["analysis"]["outro"] = segment(80, -50)
        sorter.audio_features["b"]["analysis"]["intro"] = segment(160, -50)
        sorter.audio_features["b"]["analysis"]["outro"] = segment(120, 0)
        data = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert data["components"]["tempo"][0, 1] < 1e-12
        assert data["transition"][0, 1] < data["transition"][1, 0]
        assert data["components"]["texture"][0, 1] == 0
        sorter.audio_features["b"]["analysis"]["intro"] = {}
        missing = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert missing["transition"][0, 1] == 0.5
        assert not missing["assessed"][0, 1]
        sorter.audio_features["b"]["analysis"]["intro"] = segment(160, -50)
        sorter.audio_features["b"]["analysis"]["intro"]["evidence"]["tempo"] = 0.2
        weak = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert abs(weak["components"]["tempo"][0, 1] - 0.4) < 1e-12
        sorter.original_items[0]["artist_ids"].append("featured-artist")
        sorter.original_items[1]["artist_ids"].append("featured-artist")
        credited = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert credited["artists"][0, 1]

    def test_presets_preserve_occurrences_and_improve_their_baseline(self) -> None:
        """Soft artist spacing can separate duplicates while endpoint requirements remain hard."""
        sorter = fixture()
        original = sorter.current_order.copy()
        for preset in ("steady", "mixed"):
            with self.subTest(preset=preset):
                order = sorter.sort_playlist({"preset": preset}, original[2], original[-1])
                assert Counter(order) == Counter(original)
                assert (order[0], order[-1]) == (original[2], original[-1])
                assert sorter.valid_order(order)
                result = sorter.arrangement_result
                assert result["cost"] <= result["baseline_cost"]
                assert result["terms"]["repetition"] < 0.5
                assert result["assessed_edges"] == len(order) - 1
                assert result["evaluations"] <= 5000
                assert all(0 <= term <= 1 for term in result["terms"].values())
                matrices = sorter.arrangement_data
                assert sorter.sort_playlist({"preset": preset}, original[2], original[-1]) == order
                assert sorter.arrangement_data is matrices
        assert len(sorter.arrangement_results) == 2

    def test_objective_terms_have_the_specified_scale(self) -> None:
        """Check the formula against a hand-calculated AAABBB sequence."""
        sorter = fixture()
        data = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        order = np.arange(6)
        terms = playlist_sorter._order_terms(order, data)
        assert terms["transition"] == 0
        assert terms["repetition"] == 4 / 6
        assert terms["monotony"] == 1
        assert terms["pace"] == 0
        assert terms["energy"] == 0
        steady = playlist_sorter._option_weights({"preset": "steady", "variety": 0.5, "pace": 0.5, "energy": 0.5})
        assert abs(playlist_sorter._order_cost(order, data, steady) - (0.35 * 1.075 * 4 / 6 + 0.10)) < 1e-12
        mixed = playlist_sorter._option_weights({"preset": "mixed", "variety": 0.5, "pace": 0.5, "energy": 0.5})
        assert abs(playlist_sorter._order_cost(order, data, mixed) - (0.37625 * 4 / 6 + 0.15)) < 1e-12
        for record in sorter.audio_features.values():
            record["analysis"]["body"] = None
        missing = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert playlist_sorter._order_terms(order, missing)["monotony"] == 0

    def test_tilt_terms_rank_measured_features_by_position(self) -> None:
        """Pace and energy tilts grow toward unbalanced orders and vanish without measurements."""
        sorter = fixture(2)
        sorter.audio_features["a"]["analysis"]["summary"]["rms_db"] = -40.0
        sorter.audio_features["b"]["analysis"]["summary"]["rms_db"] = 0.0
        sorter.audio_features["a"]["analysis"]["summary"]["tempo"] = 90.0
        sorter.audio_features["b"]["analysis"]["summary"]["tempo"] = 150.0
        data = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        calm_first = playlist_sorter._order_terms(np.array([0, 1]), data)
        assert calm_first["energy"] > 0
        assert calm_first["pace"] > 0
        fast_first = playlist_sorter._order_terms(np.array([1, 0]), data)
        assert fast_first["energy"] < 0
        assert fast_first["pace"] < 0
        weights = playlist_sorter._option_weights({"preset": "steady", "energy": 0.5, "pace": 0.5, "variety": 0.5})
        assert playlist_sorter._order_cost(np.array([0, 1]), data, weights) == playlist_sorter._order_cost(
            np.array([1, 0]), data, weights
        )
        ascending = playlist_sorter._option_weights({"preset": "steady", "energy": 1.0, "pace": 1.0, "variety": 0.5})
        assert playlist_sorter._order_cost(np.array([1, 0]), data, ascending) < playlist_sorter._order_cost(
            np.array([0, 1]), data, ascending
        )
        for record in sorter.audio_features.values():
            record["analysis"]["summary"]["evidence"]["rms_db"] = 0.0
            record["analysis"]["summary"]["evidence"]["onset"] = 0.0
            record["analysis"]["summary"]["evidence"]["tempo"] = 0.0
        unmeasured = playlist_sorter._prepare_arrangement(sorter.original_items, sorter.audio_features)
        assert unmeasured["energy_values"].sum() == 0
        assert unmeasured["pace_values"].sum() == 0

    def test_fixed_slots_invalid_pins_and_save_validation(self) -> None:
        """Fixed openers/closers cannot be displaced, including by a forged saved permutation."""
        sorter = fixture()
        original = sorter.current_order.copy()
        sorter.original_items[0]["fixed_reason"] = "Unavailable"
        sorter.original_items[-1]["fixed_reason"] = "Local file"
        assert sorter.sort_playlist(first_occurrence=original[1]) == []
        assert sorter.sort_playlist(last_occurrence=original[1]) == []
        assert sorter.sort_playlist(first_occurrence="foreign:snapshot:0") == []
        assert sorter.sort_playlist(first_occurrence=original[1], last_occurrence=original[1]) == []
        order = sorter.sort_playlist()
        assert (order[0], order[-1]) == (original[0], original[-1])
        assert sorter.valid_order(order)
        assert sorter.sort_playlist(first_occurrence=original[0], last_occurrence=original[-1]) == order
        transitions = sorter.get_transition_analysis(order)
        assert transitions[0]["score"] is None
        assert transitions[-1]["score"] is None
        assert all(value == 0 for value in transitions[0]["evidence"].values())
        other = fixture()
        order = other.sort_playlist(first_occurrence=other.current_order[2], last_occurrence=other.current_order[-1])
        other.snapshot_id = "snapshot"
        order[0], order[1] = order[1], order[0]
        assert other.valid_order(order)
        assert not other.update_spotify_playlist(order)[0]
        assert isinstance(other.sp, Mock)
        other.sp.playlist.assert_not_called()

    def test_placement_choices_move_fixed_entries(self) -> None:
        """Unanalyzable entries occupy the chosen slot and reject conflicting choices."""
        sorter = fixture()
        original = sorter.current_order.copy()
        sorter.original_items[0]["fixed_reason"] = "Unavailable"
        sorter.original_items[2]["fixed_reason"] = "Local file"
        order = sorter.sort_playlist(placements={original[0]: 4, original[2]: 0})
        assert (order[0], order[4]) == (original[2], original[0])
        assert sorter.valid_order(order)
        assert sorter.arrangement_result["placements"] == {original[0]: 4, original[2]: 0}
        assert not sorter.valid_order([*order[1:], order[0]])
        assert not sorter.update_spotify_playlist([*order[1:], order[0]])[0]
        for invalid in (
            {original[1]: 0},
            {original[0]: 99},
            {original[0]: 4, original[2]: 4},
        ):
            with self.subTest(invalid=invalid):
                assert sorter.sort_playlist(placements=invalid) == []
        assert sorter.sort_playlist(first_occurrence=original[0], placements={original[0]: 2}) == []
        assert sorter.sort_playlist(last_occurrence=original[1], placements={original[0]: 5}) == []
        combined = sorter.sort_playlist(last_occurrence=original[1], placements={original[0]: 4})
        assert (combined[4], combined[-1]) == (original[0], original[1])
        assert sorter.valid_order(combined)
        reset = sorter.sort_playlist(first_occurrence=original[0])
        assert reset[0] == original[0]
        assert sorter.valid_order(reset)
        again = sorter.sort_playlist(placements={original[0]: 4, original[2]: 0})
        assert again == order
        assert sorter.valid_order(again)

    def test_ties_all_one_artist_and_large_playlist_fallback(self) -> None:
        """Keep feasible originals on ties and every entry when the pair-matrix guard applies."""
        sorter = fixture()
        for entry in sorter.original_items:
            entry["artist_ids"] = ["same-artist"]
        original = sorter.current_order.copy()
        assert sorter.sort_playlist() == original
        assert sorter.arrangement_result["unchanged"]
        assert sorter.sort_playlist({"preset": "mixed"}) == original
        assert sorter.arrangement_result["terms"]["monotony"] == 1
        small = fixture(4)
        small.sort_playlist()
        assert small.arrangement_result["terms"]["monotony"] == 0
        guarded = fixture()
        guarded.original_items[2]["fixed_reason"] = "Unavailable"
        with patch.object(playlist_sorter, "_MAX_MATRIX_ENTRIES", 3):
            result = guarded.sort_playlist(
                first_occurrence=guarded.current_order[4], last_occurrence=guarded.current_order[0]
            )
        assert len(result) == 6
        assert guarded.valid_order(result)
        assert result[2] == guarded.current_order[2]
        assert guarded.arrangement_result["limited"]
        assert guarded.arrangement_result["cost"] is None
        assert guarded.arrangement_data is None

    def test_option_weights_trade_flow_for_variety(self) -> None:
        """Different priorities may produce different orders without changing normalization."""
        sorter = fixture()
        for section in sorter.audio_features["b"]["analysis"].values():
            section["rms_db"] = 0.0
        before = copy.deepcopy(sorter.audio_features)
        steady = sorter.sort_playlist()
        data = sorter.arrangement_data
        assert data is not None
        mixed = sorter.sort_playlist({"preset": "mixed", "variety": 0.8})
        assert steady != mixed
        assert sorter.arrangement_data is data
        assert sorter.audio_features == before
        for options, result in sorter.arrangement_results.items():
            indices = np.array([int(occurrence.split(":")[-1]) for occurrence in result["order"]])
            weights = playlist_sorter._option_weights(
                {
                    "preset": options[0],
                    "pace": float(options[1]),
                    "energy": float(options[2]),
                    "variety": float(options[3]),
                }
            )
            assert abs(playlist_sorter._order_cost(indices, data, weights) - result["cost"]) < 1e-12
