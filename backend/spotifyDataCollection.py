# Import necessary libraries
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import time

import credentials


def read_refresh_tokens(file_path='refreshTokens.csv'):
    # Read refresh tokens from CSV
    tokens = []
    with open(file_path, mode='r') as file:
        reader = csv.reader(file)
        for row in reader:
            tokens.append(row[0])  # Assuming the token is in the first column
    return tokens

def connect_to_spotify(refresh_token):
    # Set up Spotify authentication using a refresh token
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=credentials.CLIENT_ID,
                                                   client_secret=credentials.CLIENT_SECRET,
                                                   redirect_uri=credentials.REDIRECT_URI,
                                                   refresh_token=refresh_token,
                                                   scope='user-read-playback-state user-read-recently-played'))
    return sp

def fetch_historical_data(sp):
    # Fetch historical data using Spotify's recently played endpoint
    limit = 50
    cycles = 10
    after_timestamp = None
    all_tracks = []

    for _ in range(cycles):
        # Fetch recently played tracks
        results = sp.current_user_recently_played(limit=limit, after=after_timestamp)
        items = results['items']

        if not items:
            break

        # Process and store track data
        for item in items:
            track = item['track']
            played_at = item['played_at']
            all_tracks.append([
                track['id'],        # Track ID
                track['name'],      # Track Name
                played_at           # Played At timestamp
            ])

        # Update the timestamp for the next request
        after_timestamp = items[-1]['played_at']

        # Sleep to avoid hitting the API rate limit
        time.sleep(1)

    return all_tracks

def save_to_csv(data, file_path='processData.csv'):
    # Save data to processData.csv
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(data)

def monitor_current_playback(sp):

    previous_track_id = None
    previous_position = 0
    last_check_time = time.time()

    while True:
        # Get current playback state
        playback = sp.current_playback()

        if playback and playback['is_playing']:
            current_track = playback['item']
            current_track_id = current_track['id']
            current_position = playback['progress_ms']
            track_length = current_track['duration_ms']
            playlist = playback['context']['uri'] if playback['context'] else 'No Playlist'

            # Check if the track has changed
            if current_track_id != previous_track_id:
                if previous_track_id is not None:
                    # Calculate listened and skipped fractions for the previous track
                    listened_fraction = previous_position / track_length
                    skipped_fraction = 1 - listened_fraction

                    # Record the previous track's data
                    save_to_csv([
                        previous_track_id,  # Track ID
                        playlist,           # Playlist URI
                        previous_position,  # Last position in ms
                        track_length,       # Track length in ms
                        listened_fraction,  # Listened fraction
                        skipped_fraction    # Skipped fraction
                    ])

                # Update previous track info
                previous_track_id = current_track_id
                previous_position = current_position

            # Update the current position
            previous_position = current_position

        # Check if 10 seconds have passed since the last check
        current_time = time.time()
        if current_time - last_check_time >= 10:
            last_check_time = current_time

def main():
    refresh_tokens = read_refresh_tokens()
    
    for token in refresh_tokens:
        sp = connect_to_spotify(token)
        historical_data = fetch_historical_data(sp)
        save_to_csv(historical_data)
        monitor_current_playback(sp)

if __name__ == "__main__":
    main()
