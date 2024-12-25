import streamlit as st
import spotipy as sp
from spotipy.oauth2 import SpotifyOAuth
import os
import requests
import certifi
from datetime import datetime, timedelta
import pandas as pd
from pandas import json_normalize
import time
import pyodbc
import pytz

import credentials

# Use certifi's certificate bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

#Setup session State
if 'access_token' not in st.session_state:
    st.session_state['access_token'] = ''
if 'access_token_endTime' not in st.session_state:
    st.session_state['access_token_endTime'] = ''
if 'refresh_token' not in st.session_state:
    st.session_state['refresh_token'] = ''
if 'UserName' not in st.session_state:
    st.session_state['UserName'] = ''
if 'UserId' not in st.session_state:
    st.session_state['UserId'] = ''
if 'UserUri' not in st.session_state:
    st.session_state['UserUri'] = ''
if 'SelectedPlaylist' not in st.session_state:
    st.session_state['SelectedPlaylist'] = ''
if 'historicalDataDisplay' not in st.session_state:
    st.session_state['historicalDataDisplay'] = pd.DataFrame()
if 'is_playing' not in st.session_state:
    st.session_state['is_playing'] = False
if 'UserDbId' not in st.session_state:
    st.session_state['UserDbId'] = ''
    

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
                     f'UID={credentials.dbUsername};'
                     f'PWD={credentials.dbPassword}')

cursor = conn.cursor()

def errorLog(errorMessage):
    f = open("error.txt", "a")
    f.write(f"{datetime.now()} - {errorMessage} \n")
    f.close()

#General Query funciton, returns a dataframe. Use this instead of pd.read_sql
def getQuery(query, params=None):
    if params is None:
        params = []
    cursor.execute(query, params)
    Data = pd.DataFrame.from_records(cursor.fetchall(), columns=[col[0] for col in cursor.description])
    return Data
    
def getUserId():
    # Ensure the correct table name and schema
    userIdQuery = "SELECT * FROM dbo.USERS WHERE userUri = ?"
    userUri = st.session_state['UserUri'].strip()

    # Use parameterized query to prevent SQL injection
    userId = getQuery(userIdQuery, [userUri])
    
    if len(userId) > 0:
        userId = userId.iloc[0].to_dict()
        if (st.session_state["UserName"]) != userId["userName"]: 
            errorLog("Username in DB and username from Spotify do not match")
        st.toast(f"Thanks for returning {userId['userName']}!")
        st.session_state["UserDbId"] = userId["userId"]
        return userId["userId"]
    else:
        newUserQuery = "SELECT MAX(userId) FROM dbo.USERS"
        newUserId = getQuery(newUserQuery).values[0][0]
        if newUserId is None:
            newUserId = 1
        else: 
            newUserId = int(newUserId) + 1

        # Convert current time to Unix timestamp
        utc_now = datetime.now(pytz.utc)
        unix_timestamp = int(utc_now.timestamp())

        insertNewUserQuery = "INSERT INTO dbo.USERS (dbId, userUri, userId, userName, lastLogin) VALUES (?, ?, ?, ?, ?)"
        userName = st.session_state["UserName"]
        cursor.execute(insertNewUserQuery, (newUserId, userUri, newUserId, userName, unix_timestamp))
        conn.commit()
        st.session_state["UserDbId"] = newUserId
        return newUserId

def login():
    query_params = st.query_params
    code = query_params.get("code")

    if code:
        try:
            # Exchange the authorization code for an access token
            sp_oauth.get_access_token(code)  # This will cache the token internally
            token_info = sp_oauth.get_cached_token()  # Retrieve the token info as a dictionary
            
            access_token = token_info['access_token']
            expires_at_utc = datetime.fromtimestamp(token_info['expires_at'], pytz.utc)

            # Store access token in session state
            st.session_state['access_token'] = access_token
            st.session_state["access_token_endTime"] = expires_at_utc - timedelta(minutes=3)
            st.toast(f"You are now authenticated!, expires at {st.session_state['access_token_endTime']}")
        
        except Exception as e:
            st.warning(f"Error fetching the token: {e}")
    else:
        st.warning("Authorization code not found in URL. Please try again.")

def getUserInfo():
    try:
        requestsAsJsonUser = submitRequest("https://api.spotify.com/v1/me", "Get Users PlaybackState", {})
        
        if requestsAsJsonUser is None:
            st.warning("Failed to retrieve user information. Please check your connection and try again.")
            return

        userUri = requestsAsJsonUser["uri"]
        st.session_state["UserName"] = str(requestsAsJsonUser["display_name"])
        st.session_state["UserUri"] = userUri
        st.session_state["UserId"] = str(requestsAsJsonUser["id"])

        return st.session_state["UserName"], st.session_state["UserUri"], st.session_state["UserId"]
    
    except requests.exceptions.RequestException as e:
        errorLog(f"API request error in getUserInfo: {e}")
        st.warning("An error occurred while connecting to the Spotify API. Please try again later.")

def storeTokensInDatabase():
    db_id = st.session_state['UserDbId']
    access_token = st.session_state['access_token']
    expires_at_utc = st.session_state["access_token_endTime"] + timedelta(minutes=3)
    refresh_token = sp_oauth.get_cached_token()['refresh_token']
    userUri = st.session_state.get('UserUri', '').strip()

    if not userUri:
        errorLog("UserUri is empty. Cannot proceed with token operations.")
        st.warning("UserUri is not set. Please try logging in again.")
        return

    # Check if a token entry already exists for this user
    check_token_query = "SELECT id FROM USERTOKENS WHERE dbID = ?"
    cursor.execute(check_token_query, (db_id,))
    result = cursor.fetchone()

    if result:
        # Update existing token entry
        update_token_query = """
        UPDATE USERTOKENS 
        SET accessToken = ?, accessTokenEndTime = ?, refreshToken = ?, lastUpdated = ?, userUri = ? 
        WHERE dbID = ?
        """
        cursor.execute(update_token_query, (access_token, expires_at_utc, refresh_token, datetime.now(pytz.utc), userUri, db_id))
    else:
        # Insert new token entry
        insert_token_query = """
        INSERT INTO USERTOKENS (dbID, accessToken, accessTokenEndTime, refreshToken, lastUpdated, userUri) 
        VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor.execute(insert_token_query, (db_id, access_token, expires_at_utc, refresh_token, datetime.now(pytz.utc), userUri))
    
    conn.commit()

#General Request call for Spotify
def submitRequest(endpoint, functionName, params):

    # Define the endpoint for currently playing track
    headers = {
    "Authorization": f"Bearer {st.session_state["access_token"]}"}   

    response = requests.get(endpoint, headers=headers, params=params)

    # Check if the response is successful
    if response.status_code == 200:
        current_response = response.json()
    else:
        errorLog(f"error, {functionName}, {response.status_code}")
        print(f"error: {functionName}, {response.status_code}")
        current_response = None
    
    if current_response is not None:
        return current_response
    
    return None

# Get Information for the Live Player
def spotifyUserCurrentSongPlaying():

    requestsAsJsonPlayer = submitRequest("https://api.spotify.com/v1/me/player", "Get Users PlaybackState", {})

    if requestsAsJsonPlayer is not None:
        requestsAsJsonSong = requestsAsJsonPlayer["item"]
        playerCurrent = json_normalize(requestsAsJsonSong)
        playerCurrent["SongCurrentPosition"] = requestsAsJsonPlayer['progress_ms']
        playerCurrent["CurrentPlaylistUri"] = requestsAsJsonPlayer['context']["uri"].split(":")[2]
        
        # Add is_playing status to session state
        st.session_state['is_playing'] = requestsAsJsonPlayer['is_playing']

        if requestsAsJsonSong is not None:
            playerCurrent = playerCurrent[["id", "name", "album.name", "duration_ms", "is_local", "artists", "album.images", "SongCurrentPosition", "CurrentPlaylistUri"]]
            playerCurrent['artists'] = playerCurrent['artists'].apply(extract_item)
            playerCurrent['album.images'] = json_normalize(playerCurrent['album.images'][0])["url"]
            
        return playerCurrent

    else:
        requestsAsJsonSong = None

# Function to extract 'name' from each JSON object in the array
def extract_item(json_array, key='name'):
    return [item[key] for item in json_array if key in item]

def spotifyUsersPlaylists(username):
    params = {"limit": 50}
    requestsAsJsonPlaylists = submitRequest("https://api.spotify.com/v1/me/playlists", "Get Users History", params)

    if len(requestsAsJsonPlaylists["items"]) == 0:
        print("Request Empty - No Playlists")
        errorLog("Request Empty - No Playlists")
        return None
    
    elif requestsAsJsonPlaylists["total"] > 50:
        st.warning("More than 50 playlists")
        return None
    
    else:
        userPlaylists = (json_normalize(requestsAsJsonPlaylists["items"]))[["uri", "name", "owner.display_name", "owner.id"]]
        userPlaylists = userPlaylists[(userPlaylists["owner.id"] == username) | (userPlaylists["owner.display_name"] == username)]

    return userPlaylists

def getHistoricalData(userUri):
    # Join with SONGINFO table to get song details
    historicalDataQuery = """
    SELECT 
        ld.userUri, 
        ld.playlistUri,
        si.songName,
        si.artistName,
        si.albumName,
        ld.percentageListened,
        ld.percentageSkipped,
        CAST(ld.listeningStartTime AS datetime) AS listeningStartTime
    FROM LISTENERDATA ld
    JOIN SONGINFO si ON ld.songUri = si.songUri
    WHERE ld.userUri = ?
    """
    historicalData = getQuery(historicalDataQuery, [userUri])
    
    # Convert listeningStartTime to user's local timezone and round to nearest second
    user_timezone = pytz.timezone('America/New_York')  # Replace with the user's actual timezone
    historicalData['listeningStartTime'] = historicalData['listeningStartTime'].apply(
        lambda x: x.replace(tzinfo=pytz.utc).astimezone(user_timezone).replace(microsecond=0)
    )
    
    return historicalData

def format_historical_data(df, playlist_name):
    # Add playlist name to the DataFrame
    if playlist_name != "ALL":
        df['Playlist Name'] = playlist_name
    else:
        # Fetch playlist names for each URI
        playlist_names = userPlaylists.set_index('uri')['name'].to_dict()
        df['Playlist Name'] = df['playlistUri'].map(playlist_names)

    # Rename columns for better readability
    df = df.rename(columns={
        'songName': 'Song Name',
        'artistName': 'Artist Name',
        'albumName': 'Album Name',
        'percentageListened': 'Percentage Listened',
        'percentageSkipped': 'Percentage Skipped',
        'listeningStartTime': 'Listening Start Time'
    })

    # Drop the playlistUri and songUri columns
    df = df.drop(columns=['playlistUri', 'songUri'], errors='ignore')
    df = df.sort_values(by='Listening Start Time', ascending=False)

    # Reorder columns to move Playlist Name to the first position
    columns_order = ['Playlist Name', 'Song Name', 'Artist Name', 'Album Name', 'Percentage Listened', 'Percentage Skipped', 'Listening Start Time']
    df = df[columns_order]

    # Apply gradient formatting
    styled_df = df.style.background_gradient(
        cmap='RdYlGn',  # Red to Yellow to Green gradient
        subset=['Percentage Listened'],
        vmin=0, vmax=100  # Set the range for the gradient
    ).background_gradient(
        cmap='RdYlGn_r',  # Reverse the gradient for Percentage Skipped
        subset=['Percentage Skipped'],
        vmin=0, vmax=100
    )

    return styled_df

def getSummarizedData(historicalData, selectedPlaylistUri,userPlaylists):
    if selectedPlaylistUri is not None:
        historicalData = historicalData[historicalData['playlistUri'] == selectedPlaylistUri]
    
    playlist_names = userPlaylists.set_index('uri')['name'].to_dict()
    historicalData["Playlist Name"] = historicalData['playlistUri'].map(playlist_names)

    # Group by 'songName', 'artistName', 'albumName' and aggregate sums
    summarizedData = historicalData.groupby(['Playlist Name', 'songName', 'artistName', 'albumName']).agg({
        'percentageListened': 'sum',
        'percentageSkipped': 'sum'
    }).reset_index()

    # Rename columns for better readability
    summarizedData = summarizedData.rename(columns={
        'songName': 'Song Name',
        'artistName': 'Artist Name',
        'albumName': 'Album Name',
        'percentageListened': 'Listened Total',
        'percentageSkipped': 'Skipped Total'
    })

    # Add a new column for Preference Score
    summarizedData['Preference Score'] = summarizedData['Listened Total'] - summarizedData['Skipped Total']

    # Sort by Preference Score in descending order
    summarizedData = summarizedData.sort_values(by='Preference Score', ascending=True)

    # Apply conditional formatting based on Preference Score
    def highlight_row(row):
        score = row['Preference Score']
        if score > 0:
            return ['background-color: green'] * len(row)
        elif score > -300:
            return ['background-color: yellow'] * len(row)
        else:
            return ['background-color: red'] * len(row)

    styled_summarizedData = summarizedData.style.apply(highlight_row, axis=1)

    return styled_summarizedData

def getSpotifyHistoricalData(userUri, historicalData):
    # Find the most recent listeningStartTime in the historicalData DataFrame
    if not historicalData.empty:
        most_recent_listening = historicalData['listeningStartTime'].max()
        most_recent_listening_timestamp = int(most_recent_listening.timestamp() * 1000)
    else:
        print("No Historical Data Found")
        return pd.DataFrame(columns=['playlistUri', 'songUri', 'listenedPercentage', 'skippedPercentage', 'listeningStartTime'])

    all_songs = []
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
                'playlistUri': item['context']['uri'] if item['context'] else None,
                'songUri': item['track']['uri'],
                'listenedPercentage': 100,
                'skippedPercentage': 0,
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
                INSERT INTO SONGINFO (songUri, songName, artistName, albumName)
                VALUES (?, ?, ?, ?)
                """
                song_name = item['track']['name']
                artist_name = ', '.join([artist['name'] for artist in item['track']['artists']])
                album_name = item['track']['album']['name']
                
                cursor.execute(insert_song_query, (song_data['songUri'], song_name, artist_name, album_name))
                conn.commit()

            all_songs.append(song_data)

        # Check if we have reached the end of the available data
        if len(spotifyHistoricalData['items']) < 50:
            break

        # Update the timestamp to the last song's played time
        most_recent_listening_timestamp = int(pd.to_datetime(spotifyHistoricalData['items'][-1]['played_at']).timestamp() * 1000)

    # Convert the list of song data to a DataFrame
    return pd.DataFrame(all_songs)

st.set_page_config(layout="wide")
st.title("Simmplify")

st.divider()

player = st.empty()

st.divider()

#Pull user information from database or spotify
login()
userName, userUri, userId = getUserInfo()
useDbId = getUserId()
storeTokensInDatabase()

# Display historical data for all playlists
historicalData = getHistoricalData(userUri)

#Find most recent historical data in database, pull historical data from spotify from then till present
spotifyHistoricalData = getSpotifyHistoricalData(userUri, historicalData)

#

#Get users playlists, allow user to select a playlist
userPlaylists = spotifyUsersPlaylists(userName)

# Add "ALL" option to the list of playlist names
playlist_options = ["ALL"] + list(userPlaylists["name"].unique())
selectedPlaylistName = st.selectbox("Filter by Playlist", placeholder="-", options=playlist_options)

# Determine the selected playlist URI
if selectedPlaylistName == "ALL":
    selectedPlaylistUri = None  # No filtering by playlist
else:
    selectedPlaylistUri = userPlaylists[userPlaylists["name"] == selectedPlaylistName]["uri"].values[0]

st.session_state['SelectedPlaylist'] = selectedPlaylistUri

summarizedListeningData = getSummarizedData(historicalData, selectedPlaylistUri, userPlaylists)
st.dataframe(summarizedListeningData, hide_index=True, use_container_width=True)

st.divider()

st.markdown("## Historical Listening Data")


# Use the function to format the historical data
historicalData = format_historical_data(historicalData, selectedPlaylistName)
st.dataframe(historicalData, hide_index=True, use_container_width=True)

# Streamlit app - callback page
def callback_page():

    startTime = datetime.now(pytz.utc)

    while True:
    
        if (datetime.now(pytz.utc) - startTime).total_seconds() % 10 < 1:
            login()
            player_data = spotifyUserCurrentSongPlaying()
            if player_data is not None and not player_data.empty:
                userCurrentSongPlayingDict = player_data.to_dict('records')[0]
            else:
                userCurrentSongPlayingDict = {
                    "name": "No song playing",
                    "artists": [],
                    "album.name": "",
                    "duration_ms": 0,
                    "SongCurrentPosition": 0,
                    "CurrentPlaylistUri": ""
                }

        else: userCurrentSongPlayingDict["SongCurrentPosition"] = min(float(userCurrentSongPlayingDict["duration_ms"]), float(userCurrentSongPlayingDict["SongCurrentPosition"]) + 1000)

        with player.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown("## Player:")
            if st.session_state["is_playing"] == True:
                c2.markdown(f'SONG: {userCurrentSongPlayingDict["name"]}')
                c2.markdown(f'Artists: {",".join(userCurrentSongPlayingDict["artists"])}')
                c2.markdown(f'Album: {userCurrentSongPlayingDict["album.name"]}')
                
                # Check if playlistName is not empty
                playlistName = userPlaylists[userPlaylists["uri"] == userCurrentSongPlayingDict["CurrentPlaylistUri"]]["name"]
                if not playlistName.empty:
                    c2.markdown(f'Playlist: {str(playlistName.values[0])}')
                else:
                    c2.markdown('Playlist: Unknown')

                if userCurrentSongPlayingDict["album.images"] != "":
                    c3.image(userCurrentSongPlayingDict["album.images"], width=150)
                c2.progress(float(userCurrentSongPlayingDict["SongCurrentPosition"]) / userCurrentSongPlayingDict["duration_ms"])
                c4.markdown(f"Welcome: {st.session_state['UserName']}")
            else:
                c2.markdown("## Paused")
        

        time.sleep(1)


if __name__ == "__main__":
    callback_page()