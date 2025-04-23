import os
import base64
import json
import requests
from urllib.parse import urlencode, parse_qs, urlparse
import logging
from dotenv import load_dotenv
import spotipy
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def load_credentials():
    """Load Spotify credentials from environment variables or Streamlit secrets."""
    # Try to load from .env file first
    load_dotenv()
    
    # Get credentials from environment variables first
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    # Try to get from Streamlit secrets if not found in environment
    if not client_id or not client_secret:
        try:
            client_id = st.secrets.get("SPOTIFY_CLIENT_ID", client_id)
            client_secret = st.secrets.get("SPOTIFY_CLIENT_SECRET", client_secret)
        except Exception as e:
            logging.warning(f"Could not load from Streamlit secrets: {e}")
    
    return client_id, client_secret

def get_auth_url(client_id, redirect_uri, scope):
    """Create the authorization URL for Spotify OAuth."""
    auth_params = {
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': scope,
        'show_dialog': 'true'
    }
    
    return 'https://accounts.spotify.com/authorize?' + urlencode(auth_params)

def get_token(client_id, client_secret, redirect_uri, code):
    """Exchange authorization code for access token."""
    token_url = 'https://accounts.spotify.com/api/token'
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    token_data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        token_response = requests.post(token_url, data=token_data, headers=headers)
        token_response.raise_for_status()
        token_info = token_response.json()
        return token_info
    except requests.exceptions.RequestException as e:
        logging.error(f"Error getting token: {e}")
        if hasattr(e, 'response') and e.response:
            logging.error(f"Response: {e.response.text}")
        return None

def refresh_token(client_id, client_secret, refresh_token_str):
    """Refresh an expired access token."""
    token_url = 'https://accounts.spotify.com/api/token'
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    refresh_data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token_str
    }
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        refresh_response = requests.post(token_url, data=refresh_data, headers=headers)
        refresh_response.raise_for_status()
        new_token_info = refresh_response.json()
        
        # Preserve the refresh token if not returned by Spotify
        if 'refresh_token' not in new_token_info:
            new_token_info['refresh_token'] = refresh_token_str
            
        return new_token_info
    except requests.exceptions.RequestException as e:
        logging.error(f"Error refreshing token: {e}")
        if hasattr(e, 'response') and e.response:
            logging.error(f"Response: {e.response.text}")
        return None

def extract_code_from_redirect(redirect_url):
    """Extract the authorization code from the redirect URL."""
    try:
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)
        
        if 'code' in query_params:
            return query_params['code'][0]
        elif 'error' in query_params:
            logging.error(f"Authorization error: {query_params['error'][0]}")
            return None
        else:
            logging.error("No code or error found in redirect URL")
            return None
    except Exception as e:
        logging.error(f"Error extracting code from redirect URL: {e}")
        return None

def get_spotify_client():
    """Get an authenticated Spotify client using cached token or new authentication."""
    # Check if we have a cached token in session state
    if 'token_info' in st.session_state and st.session_state.token_info:
        token_info = st.session_state.token_info
        
        # Initialize Spotify client with cached token
        sp = spotipy.Spotify(auth=token_info['access_token'])
        
        # Test if token is still valid
        try:
            sp.current_user()
            logging.info("Using valid cached token")
            return sp
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 401:  # Token expired
                logging.warning("Cached token expired, attempting refresh...")
                
                # If refresh token exists, try to refresh
                if 'refresh_token' in token_info:
                    client_id, client_secret = load_credentials()
                    new_token_info = refresh_token(client_id, client_secret, token_info['refresh_token'])
                    
                    if new_token_info:
                        st.session_state.token_info = new_token_info
                        return spotipy.Spotify(auth=new_token_info['access_token'])
    
    # If we get here, we need a new authentication
    return None

def get_all_playlists(sp):
    """Get all playlists for the authenticated user."""
    playlists = []
    results = sp.current_user_playlists()
    
    while results:
        playlists.extend(results['items'])
        if results['next']:
            results = sp.next(results)
        else:
            break
            
    return playlists