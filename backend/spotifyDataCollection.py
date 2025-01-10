# Import necessary libraries
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from datetime import datetime, timedelta
import requests
import pandas as pd
from pandas import json_normalize
import pytz
import psycopg2
from sshtunnel import SSHTunnelForwarder
import tempfile
import numpy as np

import credentials as credentials

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

#connection string 
def connect_to_db_postgres():
    # Load SSH and PostgreSQL secrets
    ssh_username =  credentials.username_ssh
    ssh_private_key = credentials.private_key_ssh
    ssh_private_key_passphrase = credentials.private_key_passphrase

    postgres_hostname = credentials.hostname
    postgres_host_port = credentials.port
    postgres_username = credentials.username_post
    postgres_password = credentials.password_post
    postgres_database = credentials.database_post

    # Write the private key to a temporary file
    with tempfile.NamedTemporaryFile("w", delete=False) as temp_key_file:
        temp_key_file.write(ssh_private_key)
        temp_key_path = temp_key_file.name

    # Set up SSH tunnel
    server = SSHTunnelForwarder(
        ssh_address_or_host="ssh.pythonanywhere.com",
        ssh_username="nsimm22",
        ssh_private_key=temp_key_path,
        remote_bind_address=("nsimm22-4282.postgres.pythonanywhere-services.com", 14282),
        local_bind_address=("localhost", 5432),
    )
    server.start()

    # Connect to the PostgreSQL database via the SSH tunnel
    conn = psycopg2.connect(
        dbname="simmplify",
        user="simmplify",
        password="2*PlayaOnPelada",
        host="localhost",
        port=server.local_bind_port,
        sslmode="disable",
    )
        
    return conn, server

conn, server = connect_to_db_postgres()
cursor = conn.cursor()

# Example of storing previous playback data
previous_playback_data = {}

# Function to refresh access tokens
def refresh_access_tokens():
    # Query to get all users with refresh tokens and their access token expiration times
    query = "SELECT dbid, refreshtoken, accesstokenendtime, useruri, accesstoken FROM usertokens WHERE refreshtoken IS NOT NULL"
    cursor.execute(query)
    users = cursor.fetchall()

    active_users = []

    for user in users:
        db_id, refresh_token, access_token_end_time, user_uri, access_token = user
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
                access_token = token_info['access_token']
                
                # Update existing token entry
                update_access_token_query = """
                UPDATE usertokens 
                SET accesstoken = %s, accesstokenendtime = %s, lastupdated = %s 
                WHERE dbid = %s;
                """
                expires_at_utc = datetime.fromtimestamp(token_info['expires_at'], pytz.utc)
                cursor.execute(update_access_token_query, (access_token, expires_at_utc, datetime.now(pytz.utc), db_id))
                
                conn.commit()
                print(f"Successfully refreshed token for user {db_id}")
                
            # Add user to the active list if their token is still valid
            if access_token_end_time > current_time_utc:
                active_users.append((db_id, user_uri, access_token))
        except Exception as e:
            print(f"Error refreshing token for user {db_id}: {e}")

    return active_users

# Function to get data from the Spotify API about the currently playing track
def get_current_playback_data(access_token):
    try:
        
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
            
            # Check if song info is already in SONGDATA table
            check_song_query = "SELECT songuri FROM SONGDATA WHERE songuri = %s;"
            cursor.execute(check_song_query, (previous_track_id,))
            song_exists = cursor.fetchone()
            
            if not song_exists:
                print(f"Song {previous_track_id} not found in SONGDATA. Inserting new record.")
                # Insert song info into SONGDATA table
                song_name = previous_playback['item']['name']
                artist_name = ', '.join([artist['name'] for artist in previous_playback['item']['artists']])
                album_name = previous_playback['item']['album']['name']
                song_length_ms = previous_playback['item']['duration_ms']
                
                insert_song_info_query = """
                INSERT INTO SONGDATA (songuri, songname, artistname, albumname, songlengthms) 
                VALUES (%s, %s, %s, %s, %s);
                """
                cursor.execute(insert_song_info_query, (previous_track_id, song_name, artist_name, album_name, song_length_ms))
                conn.commit()
                print(f"Inserted song info for {previous_track_id}: {song_name} by {artist_name}")
            else:
                print(f"Song {previous_track_id} already exists in SONGDATA.")
            
            # Insert into LISTENERDATA table using previous_playlist_uri
            insert_listener_data_query = """
            INSERT INTO LISTENERDATA (useruri, playlisturi, songuri, percentlistened, percentskipped, listeningstarttime) 
            VALUES (%s, %s, %s, %s, %s, %s);
            """
            cursor.execute(insert_listener_data_query, (user_uri, previous_playlist_uri, previous_track_id, percentage_listened, percentage_skipped, listening_start_time))
            conn.commit()
            print(f"Processed data for track {previous_track_id}: {percentage_listened:.2f}% listened, {percentage_skipped:.2f}% skipped, started at {listening_start_time}")

#General Request call for Spotify
def submitRequest(endpoint, functionName, params, access_token):

    # Define the endpoint for currently playing track
    headers = {
    "Authorization": f"Bearer {access_token}"}   

    response = requests.get(endpoint, headers=headers, params=params)

    # Check if the response is successful
    if response.status_code == 200:
        current_response = response.json()
    else:
        print(f"error: {functionName}, {response.status_code}")
        current_response = None
    
    if current_response is not None:
        return current_response
    
    return None

def getSpotifyHistoricalData(userUri, historicalData, access_token):
    # Find the most recent listeningStartTime in the historicalData DataFrame
    if len(historicalData) > 0:
        most_recent_listening = historicalData['listeningstarttime'].max()
        most_recent_listening_timestamp = int((most_recent_listening + timedelta(seconds=60)).timestamp() * 1000)
        print("Most Recent Listening Timestamp: ", most_recent_listening_timestamp)
    else:
        print("No Historical Data Found")
        return pd.DataFrame(columns=['playlisturi', 'songuri', 'listenedpercentage', 'skippedpercentage', 'listeningstarttime'])

    all_songs = []
    liked_songs_uri = f'spotify:user:{userUri}:collection'  # Define the Liked Songs URI

    while True:
        # Fetch historical data from Spotify since the most recent listeningStartTime
        spotifyHistoricalData = submitRequest(
            "https://api.spotify.com/v1/me/player/recently-played", 
            "Get Users Recently Played", 
            {"after": most_recent_listening_timestamp, "limit": 50},
            access_token
        )

        if not spotifyHistoricalData or 'items' not in spotifyHistoricalData:
            print("No more data to fetch")
            break

        # Process each song and append to the all_songs list
        for item in spotifyHistoricalData['items']:
            song_data = {
                'playlisturi':  item["context"]["uri"] if item["context"] and item["context"]["uri"] is not None else liked_songs_uri,
                'songuri': item['track']['uri'],
                'percentlistened': 100,
                'percentskipped': 0,
                'listeningstarttime': item['played_at']
            }

            # Check if the songUri is already in the SONGDATA table
            check_song_query = """
            SELECT songuri, songName, artistname, albumname, songlengthms 
            FROM SONGDATA
            WHERE songuri = %s;
            """
            cursor.execute(check_song_query, (song_data['songuri'],))
            result = cursor.fetchone()
            
            if not result:
                # If the songUri is not found, insert the new song information
                insert_song_query = """
                INSERT INTO SONGDATA (songuri, songname, artistname, albumname, songlengthms)
                VALUES (%s, %s, %s, %s, %s)
                """
                song_name = item['track']['name']
                artist_name = ', '.join([artist['name'] for artist in item['track']['artists']])
                album_name = item['track']['album']['name']
                song_length_ms = item['track']['duration_ms']  # Get the song length in milliseconds
                
                cursor.execute(insert_song_query, (song_data['songuri'], song_name, artist_name, album_name, song_length_ms))
                conn.commit()

            # Check for unique listeningStartTime before adding to all_songs
            if song_data['listeningstarttime'] not in [s['listeningstarttime'] for s in all_songs]:
                all_songs.append(song_data)

        # Check if we have reached the end of the available data
        if len(spotifyHistoricalData['items']) < 50:
            break

        # Update the timestamp to the 'after' timestamp from the cursor in the API response
        if 'cursors' in spotifyHistoricalData and 'after' in spotifyHistoricalData['cursors']:
            most_recent_listening_timestamp = int(spotifyHistoricalData['cursors']['after'])

    # Convert the list of song data to a DataFrame
    spotifyHistoricalData = pd.DataFrame(all_songs)
    spotifyHistoricalData["useruri"] = userUri
    return spotifyHistoricalData

def insertSpotifyHistoricalData(spotifyHistoricalData):

    # Ensure spotifyHistoricalData is not empty
    if len(spotifyHistoricalData) == 0:
        print("No data to insert")
        return

    # Ensure the DataFrame has all required columns
    required_columns = ['useruri', 'playlisturi', 'songuri', 'percentlistened', 'percentskipped', 'listeningstarttime']
    spotifyHistoricalData = spotifyHistoricalData[required_columns]

    # Convert DataFrame to a list of tuples
    data_to_insert = list(spotifyHistoricalData.itertuples(index=False, name=None))

    # Insert into LISTENERDATA table
    insert_listener_data_query = """
    INSERT INTO LISTENERDATA (useruri, playlisturi, songuri, percentlistened, percentskipped, listeningstarttime)
    VALUES (%s, %s, %s, %s, %s, %s);
    """

    for record in data_to_insert:
        # Check if the record already exists
        check_existing_query = """
        SELECT COUNT(*) FROM LISTENERDATA 
        WHERE useruri = %s AND playlisturi = %s AND songuri = %s AND listeningstarttime = %s;
        """
        cursor.execute(check_existing_query, (record[0], record[1], record[2], record[5]))
        exists = cursor.fetchone()[0]

        if not exists:
            cursor.execute(insert_listener_data_query, record)

    conn.commit()
    if len(data_to_insert) > 0:
        print(f"Found {len(data_to_insert)} songs to insert while you were away")

def getLastHistoricalData(user_uri):
    # Modify the query to convert datetimeoffset to datetime

    query = """
    SELECT 
        useruri, playlisturi, songuri, percentlistened, percentskipped, 
        CAST(listeningstarttime AS TIMESTAMP) AS listeningstarttime 
    FROM LISTENERDATA 
    WHERE useruri = %s 
    ORDER BY listeningstarttime DESC 
    LIMIT 1;
    """
    cursor.execute(query, (user_uri,))
    result = cursor.fetchone()
    
    # Ensure the listeningStartTime is timezone-aware
    if result and result[5]:  # Assuming the 5th index is listeningStartTime
        listening_start_time = result[5]
        if listening_start_time.tzinfo is None:
            listening_start_time = pytz.utc.localize(listening_start_time)
        result = list(result)  # Convert to list to modify
        result[5] = listening_start_time  # Update the listeningStartTime
        
        # Create a DataFrame from the result
        return pd.DataFrame([result], columns=['useruri', 'playlisturi', 'songuri', 'percentlistened', 'percentskipped', 'listeningstarttime'])

    return pd.DataFrame()  # Return empty DataFrame if no result

def checkSpotifyHistory(user_uri, access_token):
    historical_data = getSpotifyHistoricalData(user_uri, getLastHistoricalData(user_uri), access_token)
    insertSpotifyHistoricalData(historical_data)


# Schedule this function to run periodically
def run_periodically(default_interval=10, inactive_interval=20):  # Default check every 10 seconds, inactive every 1 minutes
    next_check_time = {}
    max_inactive_interval = 600  # 10 minutes in seconds
    inactive_users = set()  # Track inactive users
    inactive_intervals = {}  # Track inactive intervals for each user

    first_run = True

    while True:
        users = refresh_access_tokens()

        for db_id, user_uri, access_token in users:
            current_time = time.time()

            # Check if it's time to process this user's playback data
            if user_uri in next_check_time and current_time < next_check_time[user_uri]:
                continue

            if first_run:
                checkSpotifyHistory(user_uri, access_token)


            print(f"Processing playback data for user {user_uri}")
            
            # Get current playback data for the user
            current_playback = get_current_playback_data(access_token)
            
            # Retrieve previous playback data if available
            previous_playback = previous_playback_data.get(user_uri)
            
            # Process playback data for the user
            process_playback_data(previous_playback=previous_playback, current_playback=current_playback, user_uri=user_uri)
            
            # Update the previous playback data
            previous_playback_data[user_uri] = current_playback

            # Check if user is inactive
            if current_playback is None or bool(current_playback['is_playing']) == False:

                #SET INTERVAL TO 60 SECONDS IF NOT SET, ELSE ADD 60 SECONDS TO THE INTERVAL
                if user_uri not in inactive_intervals:
                    inactive_intervals[user_uri] = inactive_interval
                else:
                    inactive_intervals[user_uri] = min(max_inactive_interval, 2*(inactive_intervals[user_uri]))

                next_check_time[user_uri] = current_time + inactive_intervals[user_uri]
                inactive_users.add(user_uri)  # Mark user as inactive
                # Increase inactive interval by 2 minutes, up to a maximum of 20 minutes
                print(f"User {user_uri} is inactive. Setting next check time to {inactive_intervals[user_uri]} seconds.")

            else:
                # User is active, reset inactive interval
                next_check_time[user_uri] = current_time + default_interval

                # Check if the user was previously inactive
                if user_uri in inactive_users:
                    print(f"User {user_uri} has returned from inactivity. Fetching historical data.")
                    checkSpotifyHistory(user_uri, access_token)

                    inactive_intervals.pop(user_uri)
                    inactive_users.remove(user_uri)  # Remove user from inactive set


        # Sleep for a short time to prevent a tight loop
        if first_run:
            first_run = False
        time.sleep(5)

if __name__ == "__main__":

    run_periodically()

