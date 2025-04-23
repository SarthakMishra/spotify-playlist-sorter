"""Spotify authentication and API interaction module."""

from __future__ import annotations

import logging
import os
from typing import Any

import spotipy
import streamlit as st
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Constants
# These are not passwords but API endpoints
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
HTTP_STATUS_UNAUTHORIZED = 401
SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"

# Valid redirect URIs - one of these must be configured in your Spotify Developer Dashboard
LOCAL_REDIRECT_URIS = [
    "http://127.0.0.1:8501",
]

CLOUD_REDIRECT_URIS = [
    "https://spotify-playlist-sorter.streamlit.app",
]


def load_credentials() -> tuple[str | None, str | None]:
    """Load Spotify credentials from environment variables or Streamlit secrets."""
    # Check session state first for user-provided credentials
    if "custom_client_id" in st.session_state and "custom_client_secret" in st.session_state:
        custom_client_id = st.session_state.custom_client_id
        custom_client_secret = st.session_state.custom_client_secret
        if custom_client_id and custom_client_secret:
            logger.info("Using user-provided Spotify API credentials")
            return custom_client_id, custom_client_secret

    # Try to load from .env file next
    load_dotenv()

    # Get credentials from environment variables
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    # Try to get from Streamlit secrets if not found in environment
    if not client_id or not client_secret:
        try:
            client_id = st.secrets.get("SPOTIFY_CLIENT_ID", client_id)
            client_secret = st.secrets.get("SPOTIFY_CLIENT_SECRET", client_secret)
        except (KeyError, AttributeError) as e:
            logger.warning("Could not load from Streamlit secrets: %s", e)

    return client_id, client_secret


def get_redirect_uri() -> str:
    """Get the appropriate redirect URI based on the environment and user settings."""
    # Check if the user has specified a custom redirect URI
    if "custom_redirect_uri" in st.session_state and st.session_state.custom_redirect_uri:
        logger.info("Using custom redirect URI: %s", st.session_state.custom_redirect_uri)
        return st.session_state.custom_redirect_uri

    # Use the environment value from session state (set by checkbox in app.py)
    is_local = st.session_state.get("is_local_environment", True)

    if is_local:
        # Use the first local redirect URI by default
        redirect_uri = LOCAL_REDIRECT_URIS[0]
        logger.info("Using local environment redirect URI: %s", redirect_uri)
    else:
        # Use the first cloud redirect URI by default
        redirect_uri = CLOUD_REDIRECT_URIS[0]
        logger.info("Using cloud environment redirect URI: %s", redirect_uri)

    return redirect_uri


def get_auth_manager(redirect_uri: str | None = None) -> SpotifyOAuth | None:
    """Create a SpotifyOAuth manager for handling the OAuth flow."""
    client_id, client_secret = load_credentials()

    if not client_id or not client_secret:
        logger.error("Spotify credentials not found")
        return None

    # Use provided redirect URI or get the appropriate one for the environment
    if redirect_uri is None:
        redirect_uri = get_redirect_uri()

    logger.info("Creating SpotifyOAuth with redirect URI: %s", redirect_uri)

    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SPOTIFY_SCOPE,
        cache_path=None,  # Don't cache to disk
        show_dialog=True,
    )


def get_spotify_client() -> spotipy.Spotify | None:
    """Get an authenticated Spotify client using OAuth flow."""
    # Get auth manager
    auth_manager = get_auth_manager()
    if not auth_manager:
        logger.error("Failed to create auth manager - missing credentials")
        return None

    # Check if we already have a token in session state
    if "token_info" in st.session_state and st.session_state.token_info:
        logger.info("Found existing token in session state")
        # Validate and refresh token if needed
        try:
            if auth_manager.is_token_expired(st.session_state.token_info):
                logger.info("Token expired, refreshing...")
                st.session_state.token_info = auth_manager.refresh_access_token(
                    st.session_state.token_info["refresh_token"]
                )
                logger.info("Token successfully refreshed")

            # Create client with the refreshed token
            logger.info("Creating Spotify client with existing token")
            return spotipy.Spotify(auth=st.session_state.token_info["access_token"])
        except Exception:
            logger.exception("Error refreshing token")
            # Clear invalid token
            logger.info("Clearing invalid token from session state")
            st.session_state.token_info = None

    # Check if we have a code in query parameters
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        logger.info("Found authorization code in query parameters")
        try:
            # Exchange code for token
            logger.info("Exchanging code for access token...")
            # Log important parameters for debugging
            logger.info(
                "Auth exchange parameters - Redirect URI: %s, Client ID length: %d",
                auth_manager.redirect_uri,
                len(auth_manager.client_id),
            )

            # Create a more specific error message in case of failure
            try:
                token_info = auth_manager.get_access_token(code, as_dict=True)
            except Exception as token_error:
                logger.exception("Token exchange error details")
                st.error(
                    f"Token exchange failed: {token_error}. Make sure your Spotify app's redirect URI matches exactly."
                )
                return None

            if token_info and "access_token" in token_info:
                logger.info("Successfully obtained access token")
                # Store in session state
                st.session_state.token_info = token_info

                # Clear query parameters to avoid reusing the code
                st.query_params.clear()
                logger.info("Cleared query parameters after successful token exchange")

                # Display token info (safely) for debugging
                safe_token_info = {
                    k: "***" if k in ("access_token", "refresh_token") else v for k, v in token_info.items()
                }
                logger.info("Token info (masked): %s", safe_token_info)

                # Create and return Spotify client
                return spotipy.Spotify(auth=token_info["access_token"])

            logger.error("Failed to get access token from code - token_info is empty or missing access_token")
            # Add more specific error info for debugging
            if token_info:
                logger.error("Token info keys: %s", list(token_info.keys()))
                st.error("Received incomplete token information from Spotify. Please check your app configuration.")
            else:
                logger.error("token_info is None or empty")
                st.error("No token information received from Spotify. Please verify your redirect URI is exact.")
            return None
        except Exception as e:
            logger.exception("Error exchanging code for token")
            # Show error in UI
            st.error(f"Authentication error: {e!s}")

    # If we get here, we need a new authentication
    logger.info("No valid authentication found, new authentication needed")
    return None


def get_auth_url(redirect_uri: str | None = None) -> str | None:
    """Get the authorization URL for Spotify OAuth."""
    auth_manager = get_auth_manager(redirect_uri)
    if not auth_manager:
        return None

    auth_url = auth_manager.get_authorize_url()
    logger.info("Generated auth URL: %s", auth_url)
    return auth_url


def get_all_redirect_uris() -> list[str]:
    """Get all available redirect URIs for display to the user."""
    return LOCAL_REDIRECT_URIS + CLOUD_REDIRECT_URIS


def get_all_playlists(sp: spotipy.Spotify) -> list[dict[str, Any]]:
    """Get all playlists for the authenticated user."""
    playlists = []
    logger.info("Fetching playlists for authenticated user")

    try:
        results = sp.current_user_playlists()

        while results:
            playlists.extend(results["items"])
            if results["next"]:
                results = sp.next(results)
            else:
                break

        logger.info("Successfully fetched %s playlists", len(playlists))
    except Exception as e:
        logger.exception("Error fetching playlists")
        # Show error in UI
        st.error(f"Error fetching playlists: {e!s}")

    return playlists
