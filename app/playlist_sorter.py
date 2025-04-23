import requests
import pandas as pd
import numpy as np
import time
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

class SpotifyPlaylistSorter:
    def __init__(self, playlist_id: str, sp):
        self.playlist_id = playlist_id
        self.sp = sp  # Authenticated spotipy client
        self.tracks_data = None
        self.camelot_map = self._build_camelot_map()
        self.playlist_name = None
        self.original_track_order = None

    def _build_camelot_map(self) -> Dict[str, List[str]]:
        """Build a map of compatible Camelot keys."""
        camelot_map = {}
        numbers = range(1, 13)
        letters = ['A', 'B']

        for num in numbers:
            for letter in letters:
                key = f"{num}{letter}"
                neighbors = []

                # Same number, different letter (switching between minor/major)
                other_letter = 'B' if letter == 'A' else 'A'
                neighbors.append(f"{num}{other_letter}")

                # Same letter, adjacent numbers
                prev_num = 12 if num == 1 else num - 1
                next_num = 1 if num == 12 else num + 1
                neighbors.extend([f"{prev_num}{letter}", f"{next_num}{letter}"])

                camelot_map[key] = neighbors

        return camelot_map

    def _scrape_songdata_io(self) -> Optional[pd.DataFrame]:
        """Scrape track data from songdata.io for the playlist."""
        url = f"https://songdata.io/playlist/{self.playlist_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        logging.info(f"Attempting to scrape data from: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch data from songdata.io: {e}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the table - adjust selector if songdata.io changes structure
        table = soup.find('table', id='table_chart')
        if not table:
            logging.error("Could not find the track table (id='table_chart') on the page.")
            logging.error("The website structure might have changed.")
            # Try finding by class as a fallback
            table = soup.find('table', class_='table')
            if not table:
                 logging.error("Could not find the track table by class either.")
                 return None
            else:
                 logging.warning("Found table using class='table' as fallback.")

        table_body = table.find('tbody', id='table_body')
        if not table_body:
            # Fallback if tbody doesn't have the specific ID
            table_body = table.find('tbody')
            if not table_body:
                logging.error("Could not find the table body (tbody) within the table.")
                return None
            else:
                logging.warning("Found tbody without specific ID.")

        tracks = []
        rows = table_body.find_all('tr', class_='table_object')

        if not rows:
             logging.error("Found table body, but no rows with class='table_object'.")
             return None

        logging.info(f"Found {len(rows)} potential track rows in the table.")

        for row in rows:
            try:
                # Extract data based on common class names (inspect songdata.io for accuracy)
                track_name_tag = row.find('td', class_='table_name')
                track_name = track_name_tag.find('a').text.strip() if track_name_tag and track_name_tag.find('a') else None

                artist_tag = row.find('td', class_='table_artist')
                artist = artist_tag.text.strip() if artist_tag else None

                key_tag = row.find('td', class_='table_key')
                key = key_tag.text.strip() if key_tag else None

                camelot_tag = row.find('td', class_='table_camelot')
                camelot = camelot_tag.text.strip() if camelot_tag else None

                bpm_tag = row.find('td', class_='table_bpm')
                bpm = bpm_tag.text.strip() if bpm_tag else None

                energy_tag = row.find('td', class_='table_energy')
                energy = energy_tag.text.strip() if energy_tag else None

                # Popularity is often in 'table_data' but might need specific identification
                all_data_tags = row.find_all('td', class_='table_data')
                popularity = None
                if len(all_data_tags) > 5:
                    release_date_tag = row.find('td', class_='table_data', string=lambda t: t and ('-' in t or '/' in t))
                    if release_date_tag:
                        prev_sibling = release_date_tag.find_previous_sibling('td', class_='table_data')
                        if prev_sibling:
                            popularity = prev_sibling.text.strip()

                # Spotify ID is usually in a data-src attribute
                spotify_link_cell = row.find('td', id='spotify_obj')
                spotify_id = spotify_link_cell['data-src'].strip() if spotify_link_cell and 'data-src' in spotify_link_cell.attrs else None

                if not all([track_name, artist, camelot, bpm, energy, spotify_id]):
                     logging.warning(f"Skipping row due to missing essential data (Name, Artist, Camelot, BPM, Energy, ID): {track_name}, {artist}")
                     continue

                tracks.append({
                    'id': spotify_id,
                    'Track': track_name,
                    'Artist': artist,
                    'Key': key,
                    'Camelot': camelot,
                    'BPM': bpm,
                    'Energy': energy,
                    'Popularity': popularity
                })
            except Exception as e:
                logging.warning(f"Error parsing a row: {e}. Row content: {row.text[:100]}...")
                continue

        if not tracks:
            logging.error("No tracks successfully parsed from the table.")
            return None

        df = pd.DataFrame(tracks)

        # --- Data Cleaning and Type Conversion ---
        try:
            # Convert relevant columns to numeric, coercing errors to NaN
            df['BPM'] = pd.to_numeric(df['BPM'], errors='coerce')
            # Energy from songdata.io might be 1-10 scale or 0-1. Let's assume 0-1 for now.
            raw_energy = pd.to_numeric(df['Energy'], errors='coerce')
            if raw_energy.max() > 1.0:
                 logging.warning("Detected Energy values > 1. Assuming 1-10 scale and normalizing to 0-1.")
                 df['Energy'] = raw_energy / 10.0
            else:
                 df['Energy'] = raw_energy

            df['Popularity'] = pd.to_numeric(df['Popularity'], errors='coerce')

            # Validate Camelot format (e.g., '1A', '12B')
            df['Camelot'] = df['Camelot'].str.upper()
            valid_camelot_mask = df['Camelot'].str.match(r'^[1-9]A$|^1[0-2]A$|^[1-9]B$|^1[0-2]B$', na=False)
            invalid_camelot = df[~valid_camelot_mask]['Camelot'].unique()
            if len(invalid_camelot) > 0:
                logging.warning(f"Found potentially invalid Camelot keys: {invalid_camelot}. Replacing with NaN.")
                df.loc[~valid_camelot_mask, 'Camelot'] = np.nan

        except Exception as e:
            logging.error(f"Error during data type conversion: {e}")

        logging.info(f"Successfully scraped and parsed {len(df)} tracks.")
        return df

    def load_playlist(self):
        """Load playlist name from Spotify and track data by scraping songdata.io."""
        logging.info(f"Loading playlist metadata for: {self.playlist_id}")
        try:
            # Get playlist name from Spotify (more reliable than scraping)
            playlist_info = self.sp.playlist(self.playlist_id, fields="name")
            self.playlist_name = playlist_info['name']
            logging.info(f"Playlist Name (from Spotify): '{self.playlist_name}'")
        except Exception as e:
            logging.warning(f"Failed to get playlist name from Spotify: {e}. Will proceed without it.")
            self.playlist_name = f"Playlist {self.playlist_id}"

        # Scrape track data from songdata.io
        scraped_data = self._scrape_songdata_io()

        if scraped_data is None or scraped_data.empty:
            logging.error("Failed to scrape data from songdata.io. Cannot proceed.")
            self.tracks_data = pd.DataFrame()
            self.original_track_order = []
            return None
        else:
            self.tracks_data = scraped_data
            # Store original order based on scraped table
            self.original_track_order = self.tracks_data['id'].tolist()
            logging.info(f"Using original track order based on songdata.io table ({len(self.original_track_order)} tracks).")

            # Ensure required columns exist even if scraping missed some
            for col in ['id', 'Track', 'Artist', 'Camelot', 'BPM', 'Energy', 'Popularity']:
                 if col not in self.tracks_data.columns:
                     self.tracks_data[col] = np.nan

            # Drop rows where essential sorting keys are missing AFTER scraping
            initial_count = len(self.tracks_data)
            self.tracks_data.dropna(subset=['id', 'Camelot', 'BPM', 'Energy'], inplace=True)
            dropped_count = initial_count - len(self.tracks_data)
            if dropped_count > 0:
                logging.warning(f"Dropped {dropped_count} tracks due to missing essential data (ID, Camelot, BPM, or Energy) after scraping.")

            if self.tracks_data.empty:
                 logging.error("No tracks remaining after dropping those with missing essential data.")
                 return None

        return self.tracks_data

    def calculate_transition_score(self, track1: pd.Series, track2: pd.Series) -> float:
        """Calculate transition score between two tracks using scraped data."""
        # --- Key Compatibility ---
        key1 = track1.get('Camelot')
        key2 = track2.get('Camelot')

        if pd.isna(key1) or pd.isna(key2) or key1 not in self.camelot_map:
            key_compatible = False
            key_multiplier = 0.5
            if key1 not in self.camelot_map and not pd.isna(key1):
                 logging.debug(f"Key {key1} not in camelot map for score calc.")
        else:
            key_compatible = key2 in self.camelot_map[key1]
            key_multiplier = 1.5 if key_compatible else 0.5

        # --- BPM Difference Score ---
        bpm1 = track1.get('BPM')
        bpm2 = track2.get('BPM')
        if pd.isna(bpm1) or pd.isna(bpm2):
            bpm_score = 0.0
            bpm_diff = float('inf')
        else:
            bpm_diff = abs(bpm1 - bpm2)
            bpm_score = max(0, 1 - (bpm_diff / 20.0))

        # --- Energy Transition Score ---
        energy1 = track1.get('Energy')
        energy2 = track2.get('Energy')
        if pd.isna(energy1) or pd.isna(energy2):
             energy_score = 0.5
        else:
            energy_diff = energy2 - energy1
            if energy_diff >= -0.1:
                energy_score = max(0, 1 - abs(energy_diff) * 0.5)
            else:
                energy_score = max(0, 1 - abs(energy_diff) * 1.5)

        # --- Combine Scores ---
        base_score = (bpm_score * 0.6) + (energy_score * 0.4)
        final_score = base_score * key_multiplier

        # --- Optional Bonuses ---
        if key_compatible and key1 == key2:
             final_score *= 1.1

        if bpm_diff <= 3:
             final_score *= 1.1

        return final_score

    def sort_playlist(self, start_track_id: str) -> List[str]:
        """Sort the playlist using transition scores, starting from anchor."""
        if self.tracks_data is None or self.tracks_data.empty:
            logging.error("Track data is not loaded or is empty. Cannot sort.")
            return []

        sortable_tracks = self.tracks_data.copy()

        if start_track_id not in sortable_tracks['id'].values:
             logging.error(f"Start track ID '{start_track_id}' not found in the loaded & filtered tracks.")
             if self.original_track_order and start_track_id in self.original_track_order:
                  logging.warning("Anchor track was present initially but filtered out due to missing data. Cannot use as anchor.")
             return []

        logging.info(f"Starting sort with anchor track ID: {start_track_id}")
        current_id = start_track_id
        sorted_ids = [current_id]
        remaining_tracks = sortable_tracks.set_index('id', drop=False)
        remaining_tracks = remaining_tracks.drop(current_id)

        while not remaining_tracks.empty:
            current_track_data = sortable_tracks[sortable_tracks['id'] == current_id]
            if current_track_data.empty:
                 logging.error(f"Could not find data for current track ID: {current_id}. Stopping sort.")
                 break
            current_track = current_track_data.iloc[0]

            scores = remaining_tracks.apply(
                lambda x: self.calculate_transition_score(current_track, x),
                axis=1
            )

            if scores.empty or scores.isna().all():
                logging.warning(f"Could not calculate valid scores from {current_track.get('Track', current_id)}. Stopping sort.")
                break

            next_track_idx = scores.idxmax()
            next_track = remaining_tracks.loc[next_track_idx]

            sorted_ids.append(next_track['id'])
            remaining_tracks = remaining_tracks.drop(next_track_idx)

            current_id = next_track['id']
            logging.debug(f"Added: {next_track.get('Track', current_id)} (Score: {scores.loc[next_track_idx]:.2f})")

        original_ids_set = set(self.original_track_order) if self.original_track_order else set()
        sorted_ids_set = set(sorted_ids)
        initial_sortable_ids = set(sortable_tracks['id'])
        missing_from_sort = list(initial_sortable_ids - sorted_ids_set)

        if missing_from_sort:
             logging.warning(f"Sort finished, but {len(missing_from_sort)} tracks that had data were not placed.")
             missing_tracks_ordered = [tid for tid in self.original_track_order if tid in missing_from_sort]
             logging.info(f"Appending {len(missing_tracks_ordered)} tracks that were not placed during sorting.")
             sorted_ids.extend(missing_tracks_ordered)
        elif len(sorted_ids) < len(initial_sortable_ids):
             logging.warning(f"Sorting ended with {len(sorted_ids)} tracks, but started with {len(initial_sortable_ids)} sortable tracks.")

        logging.info(f"Playlist sorting complete. Final track count: {len(sorted_ids)}")
        return sorted_ids

    def compare_playlists(self, sorted_ids: List[str]):
        """Compare original (scraped order) and sorted playlist."""
        if self.tracks_data is None or self.tracks_data.empty or not self.original_track_order:
            logging.error("Cannot compare playlists: Data not loaded or original order missing.")
            return pd.DataFrame(), pd.DataFrame()

        compare_df = self.tracks_data.copy()
        valid_original_ids = [tid for tid in self.original_track_order if tid in compare_df['id'].values]
        valid_sorted_ids = [tid for tid in sorted_ids if tid in compare_df['id'].values]

        if not valid_original_ids or not valid_sorted_ids:
             logging.error("No valid track data found for comparison after filtering.")
             return pd.DataFrame(), pd.DataFrame()

        original_df = compare_df.set_index('id').loc[valid_original_ids].reset_index()
        sorted_df = compare_df.set_index('id').loc[valid_sorted_ids].reset_index()

        original_df['Position'] = range(1, len(original_df) + 1)
        sorted_df['Position'] = range(1, len(sorted_df) + 1)

        position_map = {id_val: pos for pos, id_val in enumerate(valid_original_ids, 1)}
        sorted_df['Original Position'] = sorted_df['id'].map(position_map)
        sorted_df['Original Position'] = sorted_df['Original Position'].fillna('N/A')

        sorted_df['Position'] = pd.to_numeric(sorted_df['Position'], errors='coerce')
        sorted_df['Original Position'] = pd.to_numeric(sorted_df['Original Position'], errors='coerce')

        sorted_df['Position Change'] = sorted_df.apply(
            lambda row: row['Original Position'] - row['Position'] if pd.notna(row['Original Position']) and pd.notna(row['Position']) else np.nan,
            axis=1
        )

        return original_df, sorted_df

    def get_transition_analysis(self, sorted_ids: List[str]):
        """Generate analysis of the transitions in the sorted playlist."""
        if self.tracks_data is None or self.tracks_data.empty:
             logging.warning("No track data to analyze transitions.")
             return []

        if len(sorted_ids) < 2:
             return [{"message": "Not enough tracks for transition analysis."}]

        track_map = self.tracks_data.set_index('id').to_dict('index')
        transitions = []
        total_score = 0
        valid_transitions = 0

        for i in range(len(sorted_ids) - 1):
            track1_id = sorted_ids[i]
            track2_id = sorted_ids[i+1]

            track1_data = track_map.get(track1_id)
            track2_data = track_map.get(track2_id)

            if not track1_data or not track2_data:
                 transitions.append({
                     "index": i+1,
                     "message": f"Skipping transition {i+1}: Track data missing for {track1_id or 'N/A'} or {track2_id or 'N/A'}"
                 })
                 continue

            track1 = pd.Series(track1_data, name=track1_id)
            track2 = pd.Series(track2_data, name=track2_id)

            has_essential_data = not pd.isna(track1.get('Camelot')) and not pd.isna(track1.get('BPM')) and not pd.isna(track1.get('Energy')) and \
                                 not pd.isna(track2.get('Camelot')) and not pd.isna(track2.get('BPM')) and not pd.isna(track2.get('Energy'))

            transition = {
                "index": i+1,
                "track1_name": track1.get('Track', track1_id),
                "track2_name": track2.get('Track', track2_id),
                "track1_artist": track1.get('Artist', 'Unknown'),
                "track2_artist": track2.get('Artist', 'Unknown'),
            }

            if has_essential_data:
                score = self.calculate_transition_score(track1, track2)
                key_compatible = False
                key1_camelot = track1.get('Camelot')
                key2_camelot = track2.get('Camelot')
                if key1_camelot and key1_camelot in self.camelot_map:
                     key_compatible = key2_camelot in self.camelot_map[key1_camelot]

                bpm1 = track1.get('BPM', np.nan)
                bpm2 = track2.get('BPM', np.nan)
                energy1 = track1.get('Energy', np.nan)
                energy2 = track2.get('Energy', np.nan)

                transition.update({
                    "key1": key1_camelot,
                    "key2": key2_camelot,
                    "key_compatible": key_compatible,
                    "perfect_key_match": key1_camelot == key2_camelot,
                    "bpm1": int(bpm1) if pd.notna(bpm1) else None,
                    "bpm2": int(bpm2) if pd.notna(bpm2) else None,
                    "bpm_diff": abs(int(bpm1) - int(bpm2)) if pd.notna(bpm1) and pd.notna(bpm2) else None,
                    "energy1": float(energy1) if pd.notna(energy1) else None,
                    "energy2": float(energy2) if pd.notna(energy2) else None,
                    "energy_diff": float(energy2 - energy1) if pd.notna(energy1) and pd.notna(energy2) else None,
                    "score": float(score)
                })
                
                total_score += score
                valid_transitions += 1
            else:
                transition.update({
                    "key1": track1.get('Camelot', 'N/A'),
                    "key2": track2.get('Camelot', 'N/A'),
                    "bpm1": track1.get('BPM', 'N/A'),
                    "bpm2": track2.get('BPM', 'N/A'),
                    "energy1": track1.get('Energy', 'N/A'),
                    "energy2": track2.get('Energy', 'N/A'),
                    "message": "Missing essential data for one or both tracks"
                })

            transitions.append(transition)

        # Add summary
        if valid_transitions > 0:
            average_score = total_score / valid_transitions
            transitions.append({
                "summary": True,
                "average_score": float(average_score),
                "valid_transitions": valid_transitions,
                "total_transitions": len(sorted_ids) - 1
            })
        else:
            transitions.append({
                "summary": True,
                "message": "No valid transitions could be scored (check scraped data).",
                "valid_transitions": 0,
                "total_transitions": len(sorted_ids) - 1
            })

        return transitions

    def _get_track_uris(self, track_ids: List[str]) -> Dict[str, str]:
        """Fetch Spotify URIs for a list of track IDs."""
        uri_map = {}
        if not track_ids:
            return uri_map

        for i in range(0, len(track_ids), 50):
            batch_ids = track_ids[i:i+50]
            try:
                results = self.sp.tracks(tracks=batch_ids)
                for track in results['tracks']:
                    if track and track['id'] and track['uri']:
                        uri_map[track['id']] = track['uri']
                    elif track and track['id']:
                         logging.warning(f"Could not find URI for track ID: {track['id']}")
            except Exception as e:
                logging.error(f"Failed to fetch track details batch (starting index {i}): {e}")
            time.sleep(0.5)

        return uri_map

    def update_spotify_playlist(self, sorted_ids: List[str]):
        """Update the Spotify playlist with the new track order."""
        if not sorted_ids:
             logging.error("No sorted track IDs provided to update playlist.")
             return False, "No sorted track IDs provided"
        if self.tracks_data is None or self.tracks_data.empty:
             logging.error("No track data available to map IDs to URIs.")
             return False, "No track data available"

        logging.info(f"Fetching URIs for {len(sorted_ids)} sorted tracks...")
        uri_map = self._get_track_uris(sorted_ids)

        track_uris = [uri_map[track_id] for track_id in sorted_ids if track_id in uri_map]

        if not track_uris:
            logging.error("No valid track URIs could be fetched for the sorted IDs. Cannot update playlist.")
            return False, "No valid track URIs could be fetched"

        if len(track_uris) != len(sorted_ids):
             logging.warning(f"Could only find URIs for {len(track_uris)} out of {len(sorted_ids)} tracks. Playlist will be updated with available tracks.")

        logging.info(f"Updating Spotify playlist '{self.playlist_name}' with {len(track_uris)} tracks.")

        try:
            self.sp.playlist_replace_items(self.playlist_id, track_uris[:100])
            logging.info(f"Replaced/set first {min(len(track_uris), 100)} tracks.")

            for i in range(100, len(track_uris), 100):
                batch = track_uris[i:i+100]
                self.sp.playlist_add_items(self.playlist_id, batch)
                logging.info(f"Added batch of {len(batch)} tracks (starting index {i}).")
                time.sleep(1)

            logging.info(f"Successfully updated playlist '{self.playlist_name}' order on Spotify!")
            return True, f"Successfully updated playlist '{self.playlist_name}' with {len(track_uris)} tracks"

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Failed to update Spotify playlist: {error_msg}")
            logging.error("Check API permissions (scope), rate limits, and playlist ownership.")
            return False, f"Failed to update playlist: {error_msg}"