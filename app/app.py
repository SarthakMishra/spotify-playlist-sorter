import streamlit as st
import pandas as pd
import logging
import time
from spotify_auth import load_credentials, get_auth_url, extract_code_from_redirect, get_token, get_spotify_client, get_all_playlists
from playlist_sorter import SpotifyPlaylistSorter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Set page config
st.set_page_config(
    page_title="Spotify Playlist Sorter",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1DB954;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        margin-top: 2rem;
        margin-bottom: 1rem;
        color: #1DB954;
    }
    .info-text {
        font-size: 1rem;
        color: #777777;
    }
    .success-box {
        padding: 1rem;
        background-color: rgba(29, 185, 84, 0.1);
        border-left: 5px solid #1DB954;
        margin-bottom: 1rem;
    }
    .warning-box {
        padding: 1rem;
        background-color: rgba(255, 173, 51, 0.1);
        border-left: 5px solid #FFAD33;
        margin-bottom: 1rem;
    }
    .error-box {
        padding: 1rem;
        background-color: rgba(255, 82, 82, 0.1);
        border-left: 5px solid #FF5252;
        margin-bottom: 1rem;
    }
    .transition-card {
        padding: 1rem;
        background-color: #f9f9f9;
        border-radius: 5px;
        margin-bottom: 1rem;
        border: 1px solid #ddd;
    }
    .key-compatible {
        color: #1DB954;
        font-weight: bold;
    }
    .key-incompatible {
        color: #FF5252;
        font-weight: bold;
    }
    .perfect-match {
        color: #1DB954;
        font-weight: bold;
    }
    .bpm-good {
        color: #1DB954;
    }
    .bpm-medium {
        color: #FFAD33;
    }
    .bpm-bad {
        color: #FF5252;
    }
    .score-high {
        color: #1DB954;
        font-weight: bold;
    }
    .score-medium {
        color: #FFAD33;
        font-weight: bold;
    }
    .score-low {
        color: #FF5252;
        font-weight: bold;
    }
    .footer {
        margin-top: 3rem;
        text-align: center;
        color: #777777;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Header
    st.markdown("<h1 class='main-header'>Spotify Playlist Sorter</h1>", unsafe_allow_html=True)
    st.markdown(
        "Sort your Spotify playlists based on musical key compatibility (Camelot wheel), "
        "BPM (tempo), and energy levels to create smooth transitions between tracks."
    )
    
    # Initialize session state variables if they don't exist
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'playlists' not in st.session_state:
        st.session_state.playlists = None
    if 'playlist_id' not in st.session_state:
        st.session_state.playlist_id = None
    if 'tracks_data' not in st.session_state:
        st.session_state.tracks_data = None
    if 'sorter' not in st.session_state:
        st.session_state.sorter = None
    if 'sorted_ids' not in st.session_state:
        st.session_state.sorted_ids = None
    if 'anchor_track_id' not in st.session_state:
        st.session_state.anchor_track_id = None
    if 'original_df' not in st.session_state:
        st.session_state.original_df = None
    if 'sorted_df' not in st.session_state:
        st.session_state.sorted_df = None
    if 'transitions' not in st.session_state:
        st.session_state.transitions = None
    
    # Sidebar for authentication and playlist selection
    with st.sidebar:
        st.markdown("<h2 class='sub-header'>Authentication</h2>", unsafe_allow_html=True)
        
        # Check if we have a Spotify client
        sp = get_spotify_client()
        
        if sp:
            st.session_state.authenticated = True
            st.markdown("<div class='success-box'>✅ Authenticated with Spotify</div>", unsafe_allow_html=True)
            
            if st.button("Refresh Playlists"):
                with st.spinner("Loading your playlists..."):
                    st.session_state.playlists = get_all_playlists(sp)
                st.success(f"Loaded {len(st.session_state.playlists)} playlists")
            
            # Load playlists if not already loaded
            if st.session_state.playlists is None:
                with st.spinner("Loading your playlists..."):
                    st.session_state.playlists = get_all_playlists(sp)
            
            # Playlist selection
            st.markdown("<h2 class='sub-header'>Select Playlist</h2>", unsafe_allow_html=True)
            
            if st.session_state.playlists:
                playlist_options = {f"{p['name']} ({p['tracks']['total']} tracks)": p['id'] for p in st.session_state.playlists}
                selected_playlist = st.selectbox(
                    "Choose a playlist to sort:",
                    options=list(playlist_options.keys())
                )
                
                if selected_playlist:
                    playlist_id = playlist_options[selected_playlist]
                    
                    if st.session_state.playlist_id != playlist_id:
                        st.session_state.playlist_id = playlist_id
                        st.session_state.tracks_data = None
                        st.session_state.sorter = None
                        st.session_state.sorted_ids = None
                        st.session_state.anchor_track_id = None
                        st.session_state.original_df = None
                        st.session_state.sorted_df = None
                        st.session_state.transitions = None
                    
                    if st.button("Load Playlist Data"):
                        with st.spinner("Loading playlist data from Spotify and songdata.io..."):
                            sorter = SpotifyPlaylistSorter(playlist_id, sp)
                            tracks_data = sorter.load_playlist()
                            
                            if tracks_data is not None and not tracks_data.empty:
                                st.session_state.tracks_data = tracks_data
                                st.session_state.sorter = sorter
                                st.success(f"Loaded {len(tracks_data)} tracks with key, BPM, and energy data")
                            else:
                                st.error("Failed to load playlist data. Please check the logs for details.")
            else:
                st.info("No playlists found. Please refresh your playlists.")
        else:
            st.session_state.authenticated = False
            st.markdown("<div class='warning-box'>⚠️ Not authenticated with Spotify</div>", unsafe_allow_html=True)
            
            # Authentication flow
            client_id, client_secret = load_credentials()
            
            if not client_id or not client_secret:
                st.error(
                    "Spotify API credentials not found. Please set SPOTIFY_CLIENT_ID and "
                    "SPOTIFY_CLIENT_SECRET in your environment variables or Streamlit secrets."
                )
            else:
                # For Streamlit Cloud, we need to use a different redirect URI
                redirect_uri = "https://spotify-playlist-sorter.streamlit.app/callback"
                
                # For local development
                if st.checkbox("Running locally?"):
                    redirect_uri = "http://localhost:8501/callback"
                
                scope = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"
                auth_url = get_auth_url(client_id, redirect_uri, scope)
                
                st.markdown(f"[Authorize with Spotify]({auth_url})", unsafe_allow_html=True)
                
                redirect_url = st.text_input(
                    "After authorizing, paste the URL you were redirected to:",
                    placeholder="http://localhost:8501/callback?code=..."
                )
                
                if redirect_url:
                    code = extract_code_from_redirect(redirect_url)
                    
                    if code:
                        with st.spinner("Getting access token..."):
                            token_info = get_token(client_id, client_secret, redirect_uri, code)
                            
                            if token_info:
                                st.session_state.token_info = token_info
                                st.success("Authentication successful! Refreshing page...")
                                time.sleep(1)
                                st.experimental_rerun()
                            else:
                                st.error("Failed to get access token. Please try again.")
                    else:
                        st.error("Could not extract authorization code from the URL. Please check the URL and try again.")
        
        # Footer
        st.markdown("<div class='footer'>Spotify Playlist Sorter © 2025</div>", unsafe_allow_html=True)
    
    # Main content area
    if st.session_state.authenticated:
        if st.session_state.tracks_data is not None and st.session_state.sorter is not None:
            st.markdown("<h2 class='sub-header'>Playlist Data</h2>", unsafe_allow_html=True)
            
            # Display playlist info
            playlist_name = st.session_state.sorter.playlist_name
            st.markdown(f"**Playlist:** {playlist_name}")
            st.markdown(f"**Tracks with complete data:** {len(st.session_state.tracks_data)}")
            
            # Select anchor track
            st.markdown("<h2 class='sub-header'>Select Anchor Track</h2>", unsafe_allow_html=True)
            st.markdown(
                "Choose the first track for your sorted playlist. This track will be the starting point, "
                "and all other tracks will be arranged based on optimal transitions from this track."
            )
            
            # Create a dataframe for display with track name, artist, key, BPM, energy
            display_df = st.session_state.tracks_data[['Track', 'Artist', 'Camelot', 'BPM', 'Energy']].copy()
            display_df['BPM'] = display_df['BPM'].round().astype('Int64')
            display_df['Energy'] = (display_df['Energy'] * 10).round() / 10
            
            # Add a select button column
            track_options = {f"{row['Track']} - {row['Artist']}": row['id'] for _, row in st.session_state.tracks_data.iterrows()}
            selected_anchor = st.selectbox(
                "Choose your anchor track:",
                options=list(track_options.keys())
            )
            
            if selected_anchor:
                anchor_track_id = track_options[selected_anchor]
                st.session_state.anchor_track_id = anchor_track_id
                
                # Sort button
                if st.button("Sort Playlist"):
                    with st.spinner("Sorting playlist based on optimal transitions..."):
                        sorted_ids = st.session_state.sorter.sort_playlist(anchor_track_id)
                        
                        if sorted_ids:
                            st.session_state.sorted_ids = sorted_ids
                            
                            # Compare playlists
                            original_df, sorted_df = st.session_state.sorter.compare_playlists(sorted_ids)
                            st.session_state.original_df = original_df
                            st.session_state.sorted_df = sorted_df
                            
                            # Get transition analysis
                            transitions = st.session_state.sorter.get_transition_analysis(sorted_ids)
                            st.session_state.transitions = transitions
                            
                            st.success("Playlist sorted successfully!")
                        else:
                            st.error("Failed to sort playlist. Please check the logs for details.")
            
            # Display sorted results if available
            if st.session_state.sorted_ids and st.session_state.original_df is not None and st.session_state.sorted_df is not None:
                st.markdown("<h2 class='sub-header'>Sorted Playlist</h2>", unsafe_allow_html=True)
                
                # Display comparison
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Original Order**")
                    st.dataframe(
                        st.session_state.original_df[['Position', 'Track', 'Artist', 'Camelot', 'BPM', 'Energy']],
                        hide_index=True
                    )
                
                with col2:
                    st.markdown("**Sorted Order**")
                    st.dataframe(
                        st.session_state.sorted_df[['Position', 'Track', 'Artist', 'Camelot', 'BPM', 'Energy', 'Original Position', 'Position Change']],
                        hide_index=True
                    )
                
                # Transition analysis
                if st.session_state.transitions:
                    st.markdown("<h2 class='sub-header'>Transition Analysis</h2>", unsafe_allow_html=True)
                    
                    # Filter out summary
                    transitions = [t for t in st.session_state.transitions if not t.get('summary', False)]
                    summary = next((t for t in st.session_state.transitions if t.get('summary', False)), None)
                    
                    # Display summary if available
                    if summary:
                        if 'average_score' in summary:
                            score_class = 'score-high' if summary['average_score'] > 0.7 else 'score-medium' if summary['average_score'] > 0.4 else 'score-low'
                            st.markdown(
                                f"<div class='success-box'>"
                                f"Average Transition Score: <span class='{score_class}'>{summary['average_score']:.2f}</span> "
                                f"({summary['valid_transitions']} of {summary['total_transitions']} transitions scored)"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        elif 'message' in summary:
                            st.markdown(f"<div class='warning-box'>{summary['message']}</div>", unsafe_allow_html=True)
                    
                    # Display transitions
                    for transition in transitions:
                        if 'message' in transition and 'score' not in transition:
                            st.markdown(f"<div class='warning-box'>{transition['message']}</div>", unsafe_allow_html=True)
                            continue
                        
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.markdown(
                                f"<div class='transition-card'>"
                                f"<h3>{transition['index']}. {transition['track1_name']} → {transition['track2_name']}</h3>"
                                f"<p>{transition['track1_artist']} → {transition['track2_artist']}</p>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        
                        with col2:
                            if 'score' in transition:
                                key_class = 'key-compatible' if transition['key_compatible'] else 'key-incompatible'
                                perfect_match = " <span class='perfect-match'>(Perfect Match)</span>" if transition['perfect_key_match'] else ""
                                
                                bpm_diff = transition['bpm_diff'] if transition['bpm_diff'] is not None else 'N/A'
                                bpm_class = 'bpm-good' if bpm_diff != 'N/A' and bpm_diff <= 5 else 'bpm-medium' if bpm_diff != 'N/A' and bpm_diff <= 10 else 'bpm-bad'
                                
                                score_class = 'score-high' if transition['score'] > 0.7 else 'score-medium' if transition['score'] > 0.4 else 'score-low'
                                
                                st.markdown(
                                    f"<div class='transition-card'>"
                                    f"<p>Camelot: <span class='{key_class}'>{transition['key1']} → {transition['key2']}</span>{perfect_match}</p>"
                                    f"<p>BPM: <span class='{bpm_class}'>{transition['bpm1']} → {transition['bpm2']} (Δ{bpm_diff})</span></p>"
                                    f"<p>Energy: {transition['energy1']:.1f} → {transition['energy2']:.1f} (Δ{transition['energy_diff']:.1f})</p>"
                                    f"<p>Score: <span class='{score_class}'>{transition['score']:.2f}</span></p>"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f"<div class='transition-card'>"
                                    f"<p>Camelot: {transition['key1']} → {transition['key2']}</p>"
                                    f"<p>BPM: {transition['bpm1']} → {transition['bpm2']}</p>"
                                    f"<p>Energy: {transition['energy1']} → {transition['energy2']}</p>"
                                    f"<p>Missing data for scoring</p>"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )
                
                # Update playlist button
                st.markdown("<h2 class='sub-header'>Update Spotify Playlist</h2>", unsafe_allow_html=True)
                st.warning(
                    "⚠️ This will replace the current order of your playlist on Spotify. "
                    "Make sure you're happy with the sorted order before proceeding."
                )
                
                if st.button("Update Playlist on Spotify"):
                    with st.spinner("Updating playlist on Spotify..."):
                        success, message = st.session_state.sorter.update_spotify_playlist(st.session_state.sorted_ids)
                        
                        if success:
                            st.markdown(f"<div class='success-box'>✅ {message}</div>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<div class='error-box'>❌ {message}</div>", unsafe_allow_html=True)
        else:
            # Instructions when no playlist is loaded
            st.markdown("<h2 class='sub-header'>How It Works</h2>", unsafe_allow_html=True)
            st.markdown(
                """
                This app helps you sort your Spotify playlists for optimal transitions between tracks.
                
                **Features:**
                - Loads playlist data directly from Spotify
                - Analyzes tracks using songdata.io
                - Sorts tracks based on:
                  - Harmonic mixing (Camelot wheel)
                  - BPM (tempo) similarity
                  - Energy level transitions
                - Updates playlist order on Spotify
                - Provides detailed transition analysis
                
                **To get started:**
                1. Authenticate with Spotify using the sidebar
                2. Select a playlist to sort
                3. Choose an anchor track (the first track in your sorted playlist)
                4. Review the transition analysis
                5. Update your playlist with the optimized order
                """
            )
            
            st.markdown("<div class='warning-box'>⚠️ Please select a playlist from the sidebar and load its data to continue.</div>", unsafe_allow_html=True)
    else:
        # Not authenticated
        st.markdown("<h2 class='sub-header'>Welcome to Spotify Playlist Sorter</h2>", unsafe_allow_html=True)
        st.markdown(
            """
            This app helps you create the perfect playlist flow by sorting your tracks based on:
            
            - **Harmonic Compatibility** (Camelot wheel)
            - **BPM Matching** (tempo transitions)
            - **Energy Flow** (smooth energy level progression)
            
            To get started, please authenticate with Spotify using the sidebar.
            """
        )
        
        st.markdown("<div class='info-text'>Note: This app requires access to your Spotify playlists to function.</div>", unsafe_allow_html=True)
        
        # How it works
        st.markdown("<h2 class='sub-header'>How It Works</h2>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(
                """
                ### 1. Camelot Wheel
                
                Tracks are arranged based on musical key compatibility using the Camelot wheel system.
                
                Compatible keys create harmonic transitions between tracks.
                """
            )
        
        with col2:
            st.markdown(
                """
                ### 2. BPM Matching
                
                Tracks with similar tempos are placed together to create smooth transitions.
                
                Gradual BPM changes prevent jarring tempo shifts.
                """
            )
        
        with col3:
            st.markdown(
                """
                ### 3. Energy Flow
                
                The algorithm considers energy levels to create a natural flow.
                
                This prevents sudden drops or spikes in energy throughout your playlist.
                """
            )

if __name__ == "__main__":
    main()