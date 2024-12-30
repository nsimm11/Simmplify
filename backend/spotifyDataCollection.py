# Import necessary libraries
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import time
import pyodbc
from datetime import datetime, timedelta
import requests
import pandas as pd
from pandas import json_normalize
import pytz

import credentials as credentials

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

#connection string 
conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};'
                     f'Server={credentials.dbConnectionLocation};'
                     f'Database={credentials.dbID};'
                     'TrustServerCertificate=yes;'
                     f'UID={credentials.dbUsername};PWD={credentials.dbPassword}')

cursor = conn.cursor()

# Example of storing previous playback data
previous_playback_data = {}

# Function to refresh access tokens
def refresh_access_tokens():
    # Query to get all users with refresh tokens and their access token expiration times
    query = "SELECT dbID, refreshToken, accessTokenEndTime, userUri FROM UserTokens WHERE refreshToken IS NOT NULL"
    cursor.execute(query)
    users = cursor.fetchall()

    active_users = []

    for user in users:
        db_id, refresh_token, access_token_end_time, user_uri = user
        try:
            # Ensure access_token_end_time is timezone-aware
            if access_token_end_time.tzinfo is None:
                access_token_end_time = pytz.utc.localize(access_token_end_time)

            # Check if the access token is about to expire (e.g., within the next 5 minutes)
            current_time_utc = datetime.now(pytz.utc)
            if access_token_end_time - current_time_utc < timedelta(minutes=5):
                print(f"Refreshing token for user {db_id}")
                # Refresh the access token using the existing sp_oauth object
                token_info = sp_oauth.refresh_access_token(refresh_token)
                new_access_token = token_info['access_token']
                
                # Update existing token entry
                update_access_token_query = """
                UPDATE UserTokens 
                SET accessToken = ?, accessTokenEndTime = ?, lastUpdated = ? 
                WHERE dbID = ?
                """
                expires_at_utc = datetime.fromtimestamp(token_info['expires_at'], pytz.utc)
                cursor.execute(update_access_token_query, (new_access_token, expires_at_utc, datetime.now(pytz.utc), db_id))
                
                conn.commit()
                print(f"Successfully refreshed token for user {db_id}")
                
            # Add user to the active list if their token is still valid
            if access_token_end_time > current_time_utc:
                active_users.append((db_id, user_uri))
        except Exception as e:
            print(f"Error refreshing token for user {db_id}: {e}")

    return active_users

# Function to get data from the Spotify API about the currently playing track
def get_current_playback_data():
    try:
        # Get the access token from the SpotifyOAuth object
        token_info = sp_oauth.get_cached_token()
        access_token = token_info['access_token']
        
        # Define the endpoint and headers
        url = "https://api.spotify.com/v1/me/player"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        # Make the request to the Spotify API
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            playback_data = response.json()
            return playback_data
        else:
            print(f"Failed to retrieve playback data: {response.status_code} {response.reason}")
            return None
    except Exception as e:
        print(f"Error retrieving current playback data: {e}")
        return None

# Function to process playback data and calculate percentage listened
def process_playback_data(previous_playback, current_playback, user_uri):
    if previous_playback and current_playback:
        previous_track_id = previous_playback['item']['id']
        current_track_id = current_playback['item']['id']
        
        if previous_track_id != current_track_id:
            print(f"New track detected: {current_track_id}")
            
            # Calculate percentage listened
            previous_position_ms = previous_playback['progress_ms']
            previous_track_length_ms = previous_playback['item']['duration_ms']
            
            # Check if within 10 seconds of the end
            if previous_track_length_ms - previous_position_ms <= 12000:
                percentage_listened = 100.0
            else:
                percentage_listened = (previous_position_ms / previous_track_length_ms) * 100
            
            percentage_skipped = 100 - int(percentage_listened)
            print(f"Calculated listening percentages: {percentage_listened:.2f}% listened, {percentage_skipped:.2f}% skipped")
            
            # Extract previous playlist URI if available
            previous_playlist_uri = previous_playback.get('context', {}).get('uri', None)
            print(f"Previous Playlist URI: {previous_playlist_uri}")
            
            # Record the current time as the listening start time
            listening_start_time = datetime.now(pytz.utc)
            print(f"Listening start time recorded: {listening_start_time}")
            
            # Check if song info is already in SONGINFO table
            check_song_query = "SELECT songUri FROM SONGINFO WHERE songUri = ?"
            cursor.execute(check_song_query, (previous_track_id,))
            song_exists = cursor.fetchone()
            
            if not song_exists:
                print(f"Song {previous_track_id} not found in SONGINFO. Inserting new record.")
                # Insert song info into SONGINFO table
                song_name = previous_playback['item']['name']
                artist_name = ', '.join([artist['name'] for artist in previous_playback['item']['artists']])
                album_name = previous_playback['item']['album']['name']
                song_length_ms = previous_playback['item']['duration_ms']
                
                insert_song_info_query = """
                INSERT INTO SONGINFO (songUri, songName, artistName, albumName, songLengthMs) 
                VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(insert_song_info_query, (previous_track_id, song_name, artist_name, album_name, song_length_ms))
                conn.commit()
                print(f"Inserted song info for {previous_track_id}: {song_name} by {artist_name}")
            else:
                print(f"Song {previous_track_id} already exists in SONGINFO.")
            
            # Insert into LISTENERDATA table using previous_playlist_uri
            insert_listener_data_query = """
            INSERT INTO LISTENERDATA (userUri, playlistUri, songUri, percentageListened, percentageSkipped, listeningStartTime) 
            VALUES (?, ?, ?, ?, ?, ?)
            """
            cursor.execute(insert_listener_data_query, (user_uri, previous_playlist_uri, previous_track_id, percentage_listened, percentage_skipped, listening_start_time))
            conn.commit()
            print(f"Processed data for track {previous_track_id}: {percentage_listened:.2f}% listened, {percentage_skipped:.2f}% skipped, started at {listening_start_time}")

def getSpotifyHistoricalData(userUri, historicalData):
    # Find the most recent listeningStartTime in the historicalData DataFrame
    if not historicalData.empty:
        most_recent_listening = historicalData['listeningStartTime'].max()
        # Add 60 seconds to the most recent listening timestamp
        most_recent_listening_timestamp = int((most_recent_listening + timedelta(seconds=60)).timestamp() * 1000)
    else:
        print("No Historical Data Found")
        return pd.DataFrame(columns=['playlistUri', 'songUri', 'listenedPercentage', 'skippedPercentage', 'listeningStartTime'])

    all_songs = []
    liked_songs_uri = f'spotify:user:{userUri}:collection'  # Define the Liked Songs URI

    while True:
        # Fetch historical data from Spotify since the most recent listeningStartTime
        spotifyHistoricalData = submitRequest(
            "https://api.spotify.com/v1/me/player/recently-played", 
            "Get Users Recently Played", 
            {"after": most_recent_listening_timestamp, "limit": 50}
        )

        if not spotifyHistoricalData or 'items' not in spotifyHistoricalData:
            print("No more data to fetch")
            break

        # Process each song and append to the all_songs list
        for item in spotifyHistoricalData['items']:
            song_data = {
                'playlistUri': liked_songs_uri if item['context'] is None else item['context']['uri'],
                'songUri': item['track']['uri'],
                'percentageListened': 100,
                'percentageSkipped': 0,
                'listeningStartTime': item['played_at']
            }

            # Check if the songUri is already in the SONGINFO table
            check_song_query = """
            SELECT songUri, songName, artistName, albumName, songLengthMs 
            FROM SONGINFO 
            WHERE songUri = ?
            """
            cursor.execute(check_song_query, (song_data['songUri'],))
            result = cursor.fetchone()
            
            if not result:
                # If the songUri is not found, insert the new song information
                insert_song_query = """
                INSERT INTO SONGINFO (songUri, songName, artistName, albumName, songLengthMs)
                VALUES (?, ?, ?, ?, ?)
                """
                song_name = item['track']['name']
                artist_name = ', '.join([artist['name'] for artist in item['track']['artists']])
                album_name = item['track']['album']['name']
                song_length_ms = item['track']['duration_ms']  # Get the song length in milliseconds
                
                cursor.execute(insert_song_query, (song_data['songUri'], song_name, artist_name, album_name, song_length_ms))
                conn.commit()

            # Check for unique listeningStartTime before adding to all_songs
            if song_data['listeningStartTime'] not in [s['listeningStartTime'] for s in all_songs]:
                all_songs.append(song_data)

        # Check if we have reached the end of the available data
        if len(spotifyHistoricalData['items']) < 50:
            break

        # Update the timestamp to the 'after' timestamp from the cursor in the API response
        if 'cursors' in spotifyHistoricalData and 'after' in spotifyHistoricalData['cursors']:
            most_recent_listening_timestamp = int(spotifyHistoricalData['cursors']['after'])

    # Convert the list of song data to a DataFrame
    spotifyHistoricalData = pd.DataFrame(all_songs)
    spotifyHistoricalData["userUri"] = userUri
    return spotifyHistoricalData

def insertSpotifyHistoricalData(spotifyHistoricalData):
    # Ensure spotifyHistoricalData is not empty
    if spotifyHistoricalData.empty:
        print("No data to insert")
        return

    # Ensure the DataFrame has all required columns
    required_columns = ['userUri', 'playlistUri', 'songUri', 'percentageListened', 'percentageSkipped', 'listeningStartTime']
    spotifyHistoricalData = spotifyHistoricalData[required_columns]

    # Convert DataFrame to a list of tuples
    data_to_insert = list(spotifyHistoricalData.itertuples(index=False, name=None))

    # Insert into LISTENERDATA table
    insert_listener_data_query = """
    INSERT INTO LISTENERDATA (userUri, playlistUri, songUri, percentageListened, percentageSkipped, listeningStartTime)
    VALUES (?, ?, ?, ?, ?, ?)
    """

    for record in data_to_insert:
        # Check if the record already exists
        check_existing_query = """
        SELECT COUNT(*) FROM LISTENERDATA 
        WHERE userUri = ? AND playlistUri = ? AND songUri = ? AND listeningStartTime = ?
        """
        cursor.execute(check_existing_query, (record[0], record[1], record[2], record[5]))
        exists = cursor.fetchone()[0]

        if not exists:
            cursor.execute(insert_listener_data_query, record)

    conn.commit()
    if len(data_to_insert) > 0:
        print(f"Found {len(data_to_insert)} songs to insert while you were away")


# Schedule this function to run periodically
def run_periodically(default_interval=10, inactive_interval=120):  # Default check every 10 seconds, inactive every 2 minutes
    next_check_time = {}
    max_inactive_interval = 1200  # 20 minutes in seconds
    inactive_users = set()  # Track inactive users

    while True:
        users = refresh_access_tokens()

        for db_id, user_uri in users:
            current_time = time.time()

            # Check if it's time to process this user's playback data
            if user_uri in next_check_time and current_time < next_check_time[user_uri]:
                continue

            print(f"Processing playback data for user {user_uri}")
            
            # Get current playback data for the user
            current_playback = get_current_playback_data()
            
            # Retrieve previous playback data if available
            previous_playback = previous_playback_data.get(user_uri)
            
            # Process playback data for the user
            process_playback_data(previous_playback=previous_playback, current_playback=current_playback, user_uri=user_uri)
            
            # Update the previous playback data
            previous_playback_data[user_uri] = current_playback

            # Check if user is inactive
            if current_playback is None or bool(current_playback['is_playing']) == False:
                print(f"User {user_uri} is inactive. Setting next check time to {inactive_interval} seconds.")
                next_check_time[user_uri] = current_time + inactive_interval
                inactive_users.add(user_uri)  # Mark user as inactive
                
                # Increase inactive interval by 2 minutes, up to a maximum of 20 minutes
                inactive_interval = min(inactive_interval + 120, max_inactive_interval)
            else:
                # User is active, reset inactive interval
                next_check_time[user_uri] = current_time + default_interval

                # Check if the user was previously inactive
                if user_uri in inactive_users:
                    print(f"User {user_uri} has returned from inactivity. Fetching historical data.")
                    # Call the function to get historical data
                    historical_data = getSpotifyHistoricalData(user_uri, pd.DataFrame())
                    # Insert the historical data into the database
                    insertSpotifyHistoricalData(historical_data)

                    print(f"Historical Data: {historical_data}")

                    inactive_users.remove(user_uri)  # Remove user from inactive set

        # Sleep for a short time to prevent a tight loop
        time.sleep(5)

if __name__ == "__main__":
    run_periodically()

