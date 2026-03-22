"""Streamlit web application for Spotify playlist sorting."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from playlist_sorter import SpotifyPlaylistSorter
from spotify_auth import (
    get_all_playlists,
    get_auth_url,
    get_redirect_uri,
    get_spotify_client,
)
from spotify_auth import (
    load_credentials as load_spotify_credentials,
)

if TYPE_CHECKING:
    import spotipy

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Path for saving credentials (relative to this file's directory)
CREDENTIALS_FILE = Path(__file__).parent.parent / ".spotify_credentials"

# Number of expected lines in credentials file (client_id and client_secret)
EXPECTED_CREDENTIALS_LINES = 2

# Minimum number of tracks needed for a meaningful chart
MIN_TRACKS_FOR_CHART = 2


# --- Credential helpers ---


def save_credentials(client_id: str, client_secret: str) -> bool:
    """Save credentials to a local file."""
    try:
        with CREDENTIALS_FILE.open("w") as f:
            f.write(f"{client_id}\n{client_secret}")
        logger.info("Credentials saved successfully")
        return True
    except Exception:
        logger.exception("Failed to save credentials")
        return False


def load_credentials() -> tuple[str | None, str | None]:
    """Load credentials from a local file."""
    try:
        if not CREDENTIALS_FILE.exists():
            return None, None

        with CREDENTIALS_FILE.open() as f:
            lines = f.readlines()

        if len(lines) >= EXPECTED_CREDENTIALS_LINES:
            client_id = lines[0].strip()
            client_secret = lines[1].strip()
            logger.info("Credentials loaded successfully")
            return client_id, client_secret
        return None, None
    except Exception:
        logger.exception("Failed to load credentials")
        return None, None


# --- Session state helpers ---


def _init_session_state() -> None:
    """Initialize all session state variables with defaults."""
    defaults: dict[str, Any] = {
        "authenticated": False,
        "playlists": None,
        "playlist_id": None,
        "tracks_data": None,
        "sorter": None,
        "sorted_ids": None,
        "anchor_track_id": None,
        "original_df": None,
        "sorted_df": None,
        "transitions": None,
        "auth_flow_started": False,
        "auth_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if "custom_client_id" not in st.session_state:
        client_id, client_secret = load_spotify_credentials()
        st.session_state.custom_client_id = client_id or ""
        st.session_state.custom_client_secret = client_secret or ""

    if "credentials_locked" not in st.session_state:
        st.session_state.credentials_locked = bool(
            st.session_state.custom_client_id and st.session_state.custom_client_secret
        )


def _clear_auth_state() -> None:
    """Reset authentication-related session state."""
    st.session_state.authenticated = False
    st.session_state.token_info = None
    st.session_state.playlists = None
    st.session_state.auth_flow_started = False
    st.session_state.auth_error = None


def _clear_playlist_state() -> None:
    """Reset playlist-related session state when switching playlists."""
    st.session_state.tracks_data = None
    st.session_state.sorter = None
    st.session_state.sorted_ids = None
    st.session_state.anchor_track_id = None
    st.session_state.original_df = None
    st.session_state.sorted_df = None
    st.session_state.transitions = None


# --- Sidebar rendering ---


def _render_credential_inputs() -> None:
    """Render the credential input section in the sidebar."""
    # Environment selection
    if "is_local_environment" not in st.session_state:
        st.session_state.is_local_environment = False

    is_local = st.checkbox("Running locally", value=st.session_state.is_local_environment)
    if is_local != st.session_state.is_local_environment:
        st.session_state.is_local_environment = is_local
        if "token_info" in st.session_state:
            _clear_auth_state()
            st.rerun()

    if st.session_state.credentials_locked:
        st.text_input("Client ID", value="*" * 10, disabled=True)
        st.text_input("Client Secret", value="*" * 10, disabled=True)

        if st.button("Reset Credentials", width="stretch"):
            st.session_state.custom_client_id = ""
            st.session_state.custom_client_secret = ""
            st.session_state.credentials_locked = False
            _clear_auth_state()
            if CREDENTIALS_FILE.exists():
                try:
                    CREDENTIALS_FILE.unlink()
                except Exception:
                    logger.exception("Failed to delete credentials file")
            st.rerun()
    else:
        st.caption("Need credentials? [Create a Spotify app](https://developer.spotify.com/dashboard)")
        custom_client_id = st.text_input("Client ID", value=st.session_state.custom_client_id, type="password")
        custom_client_secret = st.text_input(
            "Client Secret", value=st.session_state.custom_client_secret, type="password"
        )

        if st.button("Save Credentials", type="primary", width="stretch"):
            if custom_client_id and custom_client_secret:
                st.session_state.custom_client_id = custom_client_id
                st.session_state.custom_client_secret = custom_client_secret
                if save_credentials(custom_client_id, custom_client_secret):
                    st.session_state.credentials_locked = True
                    _clear_auth_state()
                    st.rerun()
                else:
                    st.error("Failed to save credentials.")
            else:
                st.error("Both Client ID and Client Secret are required.")


def _render_auth_flow() -> None:
    """Render the Spotify OAuth authentication flow UI."""
    auth_url = get_auth_url()

    if not auth_url:
        st.error("Enter valid Spotify API credentials to continue.")
        return

    st.link_button("Connect Spotify Account", auth_url, width="stretch")

    if st.session_state.auth_error:
        st.error(st.session_state.auth_error)

    if "code" in st.query_params:
        st.info("Authorization code received. Processing...")
        with st.expander("Troubleshooting"):
            st.write(f"Redirect URI: `{get_redirect_uri()}`")
            st.write("Make sure your Spotify app's redirect URI matches exactly.")
            if st.button("Retry Authentication"):
                _clear_auth_state()
                st.rerun()


def _render_playlist_selector(sp: spotipy.Spotify) -> None:
    """Render playlist loading and selection UI."""
    if st.button("Refresh Playlists"):
        with st.spinner("Loading playlists..."):
            st.session_state.playlists = get_all_playlists(sp)

    if st.session_state.playlists is None:
        with st.spinner("Loading playlists..."):
            st.session_state.playlists = get_all_playlists(sp)

    if not st.session_state.playlists:
        st.info("No playlists found.")
        return

    playlist_options = {f"{p['name']} ({p['tracks']['total']} tracks)": p["id"] for p in st.session_state.playlists}
    selected_playlist = st.selectbox("Playlist", options=list(playlist_options.keys()), label_visibility="collapsed")

    if not selected_playlist:
        return

    playlist_id = playlist_options[selected_playlist]

    if st.session_state.playlist_id != playlist_id:
        st.session_state.playlist_id = playlist_id
        _clear_playlist_state()

    if st.button("Load Playlist", width="stretch"):
        progress_bar = st.progress(0, text="Fetching tracks...")
        status_text = st.empty()

        def on_progress(done: int, total: int) -> None:
            pct = done / total if total else 1.0
            progress_bar.progress(pct, text=f"Analyzing audio... {done}/{total}")
            status_text.caption(f"{done}/{total} tracks analyzed")

        sorter = SpotifyPlaylistSorter(playlist_id, sp)
        tracks_data = sorter.load_playlist(progress_callback=on_progress)
        progress_bar.empty()
        status_text.empty()

        if tracks_data is not None and not tracks_data.empty:
            st.session_state.tracks_data = tracks_data
            st.session_state.sorter = sorter
            st.success(f"Loaded {len(tracks_data)} tracks")
        else:
            st.error("Failed to load playlist data.")


def _render_sidebar() -> None:
    """Render the full sidebar with auth and playlist selection."""
    with st.sidebar:
        st.header("Spotify Playlist Sorter")
        _render_credential_inputs()

        if not (st.session_state.custom_client_id and st.session_state.custom_client_secret):
            return

        # Set credentials for the OAuth flow
        os.environ["SPOTIFY_CLIENT_ID"] = st.session_state.custom_client_id
        os.environ["SPOTIFY_CLIENT_SECRET"] = st.session_state.custom_client_secret

        st.divider()

        if not st.session_state.authenticated:
            sp = get_spotify_client()
            if sp:
                st.session_state.authenticated = True
                st.session_state.auth_error = None
                st.rerun()
        else:
            sp = get_spotify_client()
            if not sp:
                st.session_state.authenticated = False
                st.session_state.auth_error = "Token expired or invalid"
                st.rerun()

        if st.session_state.authenticated and sp:
            st.success("Connected to Spotify", icon="✅")
            _render_playlist_selector(sp)
            if st.button("Sign Out"):
                _clear_auth_state()
                st.rerun()
        else:
            _render_auth_flow()

        with st.expander("Debug"):
            st.caption(f"Auth: {'Yes' if st.session_state.authenticated else 'No'}")
            st.caption(f"Token: {'Yes' if st.session_state.get('token_info') else 'No'}")
            if st.button("Clear Session"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()


# --- Main content rendering ---


def _render_sorting_controls() -> None:
    """Render anchor track selection and sort button."""
    playlist_name = st.session_state.sorter.playlist_name
    st.subheader(f"{playlist_name}")
    st.caption(f"{len(st.session_state.tracks_data)} tracks with audio data")

    track_options = {
        f"{row['Track']} - {row['Artist']}": row["id"] for _, row in st.session_state.tracks_data.iterrows()
    }
    selected_anchor = st.selectbox("Anchor track (playlist will start here)", options=list(track_options.keys()))

    if not selected_anchor:
        return

    anchor_track_id = track_options[selected_anchor]
    st.session_state.anchor_track_id = anchor_track_id

    button_label = "Re-sort" if st.session_state.get("sorted_ids") else "Sort Playlist"
    if st.button(button_label, type="primary"):
        with st.spinner("Sorting..."):
            sorted_ids = st.session_state.sorter.sort_playlist(anchor_track_id)
            if sorted_ids:
                st.session_state.sorted_ids = sorted_ids
                original_df, sorted_df = st.session_state.sorter.compare_playlists(sorted_ids)
                st.session_state.original_df = original_df
                st.session_state.sorted_df = sorted_df
                st.session_state.transitions = st.session_state.sorter.get_transition_analysis(sorted_ids)
            else:
                st.error("Sorting failed.")


def _render_sorted_results() -> None:
    """Render the sorted playlist comparison and transition analysis."""
    if not (
        st.session_state.sorted_ids
        and st.session_state.original_df is not None
        and st.session_state.sorted_df is not None
    ):
        return

    display_columns = ["Track", "Artist", "Camelot", "BPM", "Energy"]

    tab_sorted, tab_original = st.tabs(["Sorted Order", "Original Order"])

    with tab_sorted:
        st.dataframe(st.session_state.sorted_df[display_columns], hide_index=True, width="stretch")

    with tab_original:
        st.dataframe(st.session_state.original_df[display_columns], hide_index=True, width="stretch")

    if st.session_state.transitions:
        _render_transition_analysis(st.session_state.transitions)

    st.divider()

    if st.button("Apply to Spotify", type="primary"):
        with st.spinner("Updating playlist on Spotify..."):
            success, message = st.session_state.sorter.update_spotify_playlist(st.session_state.sorted_ids)
            if success:
                st.success(message)
            else:
                st.error(message)


def _render_transition_analysis(all_transitions: list[dict[str, Any]]) -> None:
    """Render the transition analysis table and chart."""
    transitions = [t for t in all_transitions if not t.get("summary", False)]

    # Build compact transition rows
    transition_data = []
    for transition in transitions:
        if "score" not in transition:
            continue
        transition_data.append(_build_transition_row(transition))

    if not transition_data:
        return

    with st.expander("Transition Details", expanded=False):
        st.dataframe(pd.DataFrame(transition_data), hide_index=True, width="stretch")

    with st.expander("Visual Analysis", expanded=False):
        try:
            fig = create_transition_chart(transitions)
            st.plotly_chart(fig, use_container_width=True)
        except (ValueError, TypeError, KeyError):
            st.caption("Not enough data to render chart.")


def _build_transition_row(transition: dict[str, Any]) -> dict[str, Any]:
    """Build a compact transition row for the analysis table."""
    bpm_diff = transition.get("bpm_diff")
    energy_diff = transition.get("energy_diff")

    row: dict[str, Any] = {
        "#": transition["index"],
        "From": transition["track1_name"],
        "To": transition["track2_name"],
        "Key": f"{transition['key1']} → {transition['key2']}",
        "BPM Diff": f"{bpm_diff:.0f}" if bpm_diff is not None else "-",
        "Energy Diff": f"{energy_diff:+.2f}" if energy_diff is not None else "-",
        "Score": f"{transition['score']:.2f}",
    }

    return row


def _render_landing_page() -> None:
    """Render the unauthenticated landing page."""
    st.markdown(
        "Sort your Spotify playlists for smooth transitions using "
        "**harmonic mixing** (Camelot wheel), **BPM matching**, and **energy flow**."
    )

    redirect_uri = get_redirect_uri()

    st.info(
        f"**Setup:** Create a [Spotify app](https://developer.spotify.com/dashboard), "
        f"set redirect URI to `{redirect_uri}`, then enter your credentials in the sidebar.",
        icon="👈",
    )


# --- Chart creation ---


def create_transition_chart(transitions: list[dict[str, Any]]) -> go.Figure:
    """Create a scatter plot of track transitions (BPM vs Key, colored by Energy)."""
    chart_data = []

    for i, transition in enumerate(transitions):
        if "score" not in transition:
            continue

        try:
            bpm1 = float(transition["bpm1"]) if transition["bpm1"] is not None else 0
            bpm2 = float(transition["bpm2"]) if transition["bpm2"] is not None else 0
            energy1 = float(transition["energy1"]) if transition["energy1"] is not None else 0
            energy2 = float(transition["energy2"]) if transition["energy2"] is not None else 0

            track1 = {
                "Track": f"{transition['track1_name']} - {transition['track1_artist']}",
                "Key": transition["key1"],
                "BPM": bpm1,
                "Energy": energy1,
                "Position": i,
                "TrackNum": i + 1,
            }
            track2 = {
                "Track": f"{transition['track2_name']} - {transition['track2_artist']}",
                "Key": transition["key2"],
                "BPM": bpm2,
                "Energy": energy2,
                "Position": i + 1,
                "TrackNum": i + 2,
            }

            if i == 0 or chart_data[-1]["Track"] != track1["Track"]:
                chart_data.append(track1)
            chart_data.append(track2)
        except (ValueError, TypeError, KeyError):
            continue

    if len(chart_data) < MIN_TRACKS_FOR_CHART:
        msg = "Not enough valid transition data to create chart"
        raise ValueError(msg)

    chart_df = pd.DataFrame(chart_data)

    fig = px.scatter(
        chart_df,
        x="BPM",
        y="Key",
        color="Energy",
        size="Energy",
        color_continuous_scale="Viridis",
        hover_name="Track",
        text="TrackNum",
        range_color=[0, 1],
    )

    fig.update_layout(
        height=500,
        xaxis_title="BPM",
        yaxis_title="Key (Camelot)",
        margin={"l": 40, "r": 20, "t": 20, "b": 40},
    )

    fig.update_traces(
        textposition="top center",
        textfont={"size": 9, "color": "gray"},
        marker={"line": {"width": 1, "color": "darkgray"}},
        selector={"mode": "markers+text"},
    )

    return fig


# --- Page setup & entry point ---


st.set_page_config(
    page_title="Spotify Playlist Sorter",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    """Main application entry point."""
    _init_session_state()
    _render_sidebar()

    if st.session_state.authenticated:
        if st.session_state.tracks_data is not None and st.session_state.sorter is not None:
            _render_sorting_controls()
            _render_sorted_results()
        else:
            st.caption("Select a playlist from the sidebar to get started.")
    else:
        _render_landing_page()

    st.caption(
        "[@MishraMishry](https://x.com/MishraMishry) · "
        "[Source](https://github.com/SarthakMishra/spotify-playlist-sorter)"
    )


if __name__ == "__main__":
    main()
