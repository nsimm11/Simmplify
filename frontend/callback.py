import streamlit as st
from spotipy.oauth2 import SpotifyOAuth
import os
import numpy as np
import requests
import certifi
from datetime import datetime, timedelta
import pandas as pd
from pandas import json_normalize
import time
import pyodbc
import pytz
from streamlit_extras.switch_page_button import switch_page

st.set_page_config(
    layout="wide", 
    page_title="SIMMPLIFY",
    page_icon=":musical_note:"
)

# Set the display format for floating-point numbers to show 2 decimal places
pd.options.display.float_format = '{:.2f}'.format

# Use certifi's certificate bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Setup session State
if 'auth_code' not in st.session_state:
    st.session_state['auth_code'] = None
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
if 'previous_song_name' not in st.session_state:
    st.session_state['previous_song_name'] = None

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing user-read-recently-played"

sp_oauth = SpotifyOAuth(client_id=st.secrets["CLIENT_ID"], 
                        client_secret=st.secrets["CLIENT_SECRET"],
                        redirect_uri=st.secrets["REDIRECT_URI"],
                        scope=SCOPE)

#connection string 
conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};'
                     f'Server={st.secrets["dbConnectionLocation"]};'
                     f'Database={st.secrets["dbID"]};'
                     'TrustServerCertificate=yes;'
                     f'UID={st.secrets["dbUsername"]};'
                     f'PWD={st.secrets["dbPassword"]}')

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

    if st.session_state['access_token'] != '' and st.session_state["access_token_endTime"] != '' and st.session_state["refresh_token"] != '':
        st.toast("You are already logged in!")
        return
    
    query_params = st.query_params  # Use st.query_params directly
    code = query_params.get("code")  # Get the code directly

    if code:
        # Store the code in session state
        st.session_state['auth_code'] = code  

        # Proceed with token exchange using the new function
        exchange_code_for_token(code)  # Call the new function to exchange the code for a token

    else:
        st.warning("Authorization code not found in URL. Please try again.")

def exchange_code_for_token(code):
    token_url = "https://accounts.spotify.com/api/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': st.secrets["REDIRECT_URI"],
        'client_id': st.secrets["CLIENT_ID"],
        'client_secret': st.secrets["CLIENT_SECRET"]
    }
    
    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        token_info = response.json()
        st.toast("Updating Session State")
        st.session_state['access_token'] = token_info['access_token']
        st.session_state["access_token_endTime"] = datetime.now(pytz.utc) + timedelta(seconds=token_info['expires_in'])
        st.session_state["refresh_token"] = token_info['refresh_token']
        st.toast(f"You are now authenticated!, expires at {st.session_state['access_token_endTime']}")
    else:
        st.warning(f"Error fetching the token: {response.status_code} - {response.text}")

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
    refresh_token = st.session_state['refresh_token']
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
    ORDER BY ld.listeningStartTime DESC
    """
    historicalData = getQuery(historicalDataQuery, [userUri])

    # Convert listeningStartTime to user's local timezone and round to nearest second
    user_timezone = pytz.timezone('America/New_York')  # Replace with the user's actual timezone
    historicalData['listeningStartTime'] = historicalData['listeningStartTime'].apply(
        lambda x: x.replace(tzinfo=pytz.utc).astimezone(user_timezone).replace(microsecond=0)
    )

    return historicalData

def format_historical_data(df, playlist_name):
    #Limit to the last 150 rows since the data will become too large to display
    df = df.sort_values(by='listeningStartTime', ascending=False)
    df = df.head(150)
    
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

def getSummarizedData(historicalData, selectedPlaylistUri, userPlaylists):
    
    if selectedPlaylistUri is not None:
        historicalData = historicalData[historicalData['playlistUri'] == selectedPlaylistUri]
    
    playlist_names = userPlaylists.set_index('uri')['name'].to_dict()

    if "playlistUri" in historicalData.columns:
        historicalData["Playlist Name"] = historicalData['playlistUri'].map(playlist_names)


    # Group by 'playlistUri', 'songName', 'artistName', 'albumName' and aggregate sums
    summarizedData = historicalData.groupby(['Playlist Name', 'playlistUri', 'songName', 'artistName', 'albumName']).agg({
        'percentageListened': 'sum',
        'percentageSkipped': 'sum',
        'listeningStartTime': 'count'  # Count the number of times the song has been listened to in this playlist
    }).reset_index()

    # Rename columns for better readability
    summarizedData = summarizedData.rename(columns={
        'songName': 'Song Name',
        'artistName': 'Artist Name',
        'albumName': 'Album Name',
        'percentageListened': 'Listened Total',
        'percentageSkipped': 'Skipped Total',
        'listeningStartTime': 'Play Count'  # Rename the count column
    })

    # Drop the 'playlistUri' column before returning
    summarizedData = summarizedData.drop(columns=['playlistUri'])

    # Add a new column for Preference Score
    summarizedData['Preference Score'] = summarizedData['Listened Total'] - summarizedData['Skipped Total']

    # Add a new column for Preference Rate
    summarizedData['Preference Rate'] = np.round(summarizedData['Preference Score'] / summarizedData['Play Count'].replace(0, 1), 2)  # Avoid division by zero

    # Sort by Preference Rate with negative values first, then 0 to 100, and finally 100
    summarizedData['Preference Rate'] = summarizedData['Preference Rate'].astype(int)  # Ensure it's float for proper sorting
    summarizedData = summarizedData.sort_values(by='Preference Rate', ascending=True)  # Sort in ascending order
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

def summarizedAdvancedStats(historicalData):

    # Filter out entries where percentage listened is 0 for top categories
    filtered_top_historicalData = historicalData[historicalData['percentageListened'] > 0]

    bottomArtists = historicalData[historicalData['percentageSkipped'] > 0].groupby('artistName').agg({'percentageSkipped': 'sum'}).reset_index().sort_values(by='percentageSkipped', ascending=False).head(5)
    
    bottomSongs = historicalData[historicalData['percentageSkipped'] > 0].groupby(['songName', 'artistName']).agg({'percentageSkipped': 'sum'}).reset_index().sort_values(by='percentageSkipped', ascending=False).head(5)

    bottomPlaylists = historicalData.groupby('playlistUri').agg({'percentageSkipped': 'sum'}).reset_index().sort_values(by='percentageSkipped', ascending=False).head(5)
    
    topSongs = filtered_top_historicalData.groupby(['songName', 'artistName']).agg({'percentageListened': 'sum'}).reset_index().sort_values(by='percentageListened', ascending=False).head(5)
    
    topArtists = filtered_top_historicalData.groupby('artistName').agg({'percentageListened': 'sum'}).reset_index().sort_values(by='percentageListened', ascending=False).head(5)

    topPlaylists = historicalData.groupby('playlistUri').agg({'percentageListened': 'sum'}).reset_index().sort_values(by='percentageListened', ascending=False).head(5)

    return topArtists, topSongs, bottomArtists, bottomSongs, bottomPlaylists, topPlaylists

@st.cache_data
def get_album_cover_url(song_name):
    # Define the endpoint for searching the song
    search_url = "https://api.spotify.com/v1/search"
    params = {
        "q": song_name,
        "type": "track",
        "limit": 1  # Limit to one result
    }

    # Use the submitRequest function to make the API call
    response = submitRequest(search_url, "Get Album Cover", params)

    if response and 'tracks' in response and response['tracks']['items']:
        # Get the first track's album cover image URL
        album_cover_url = response['tracks']['items'][0]['album']['images'][0]['url']
        return album_cover_url

    # Return a placeholder image URL if no cover is found or an error occurs
    return "https://via.placeholder.com/150/CCCCCC/FFFFFF?text=No+Cover"  # Placeholder grey box

def search_artist_image_bySongUri(artistName):

    #First look for songUris in SONGINFO by artistName, if there are multiple artist names, take the first one by delimiting by ","
    songUri = getQuery("SELECT songUri FROM SONGINFO WHERE artistName = ?", artistName.split(",")[0])

    #Check if query comes back empty
    if len(songUri) == 0:
        return None

    # Define the endpoint for searching the artist
    search_url = "https://api.spotify.com/v1/tracks/" + str(songUri["songUri"].iloc[0])
    response = submitRequest(search_url, "Get Artist Image", {})

    if response and 'album' in response and response['album']['images']:
        # Check if the first artist has images
        if response['album']['images']:
            # Get the first artist's image URL
            artist_image_url = response['album']['images'][0]['url']

            return artist_image_url

    return None

def search_artist_image_byName(artist_name):
    # Define the endpoint for searching the artist
    search_url = "https://api.spotify.com/v1/search"
    params = {
        "q": artist_name,
        "type": "artist",
        "limit": 1  # Limit to one result
    }

    # Use the submitRequest function to make the API call
    response = submitRequest(search_url, "Get Artist Image", params)

    if response and 'artists' in response and response['artists']['items']:
        # Check if the first artist has images
        if response['artists']['items'][0]['images']:
            # Get the first artist's image URL
            artist_image_url = response['artists']['items'][0]['images'][0]['url']
            return artist_image_url

    return None


@st.cache_data
def get_artist_image_url(artist_name):
    #First try to get the image by songUri
    artist_image_url = search_artist_image_bySongUri(artist_name)

    #If that fails, try to get the image by artist name
    if artist_image_url is None:
        artist_image_url = search_artist_image_byName(artist_name)
    else: return artist_image_url

    #If that fails, return a placeholder image URL
    if artist_image_url is None or "http" not in artist_image_url:
        return "https://via.placeholder.com/150/CCCCCC/FFFFFF?text=No+Image"  # Placeholder grey box
    else: return artist_image_url

@st.cache_data
def get_playlist_image_url(playlist_name):
    return "https://via.placeholder.com/150/CCCCCC/FFFFFF?text=No+Image"  # Placeholder grey box


# Function to display statistics for artists or songs
def display_stats(column, title, statType, display_percentage):
    st.markdown(f"<h4 style='color: #1DB954;'>{title}</h4>", unsafe_allow_html=True)

    count = 1
    if len(column) > 0:
        for item in column.itertuples():
            # Adjust column sizes: rank, name, image, and percentage
            cols = st.columns([0.5, 1.5, 1, 1])

            # Display rank
            with cols[0]:
                st.markdown(
                    f"<div class='center-text'><span style='font-size: 2em; font-weight: bold; color: rgba(255, 255, 255, 0.8);'>{count}</span></div>",
                    unsafe_allow_html=True,
                )

            # Display artist or song name
            with cols[1]:
                if statType == "Artist":
                    st.markdown(f"**{item.artistName}**")
                elif statType == "Song":
                    st.markdown(f"**{item.songName}** by **{item.artistName}**")
                elif statType == "Playlist":
                    st.markdown(f"**{userPlaylists[userPlaylists['uri'] == item.playlistUri]['name'].values[0]}**")

            # Display artist image or album cover
            with cols[2]:
                if statType == "Artist":
                    artist_image_url = get_artist_image_url(item.artistName)
                    st.image(artist_image_url, width=80)
                elif statType == "Song":
                    album_cover_url = get_album_cover_url(item.songName)
                    st.image(album_cover_url, width=80)
                elif statType == "Playlist":
                    playlist_image_url = get_playlist_image_url(item.playlistUri)
                    st.image(playlist_image_url, width=80)

            # Display percentage listened or skipped
            with cols[3]:
                percentage = (
                    f"{item.percentageListened}%" if display_percentage == 'listened' else f"{item.percentageSkipped}%"
                )
                label = "Listened" if display_percentage == 'listened' else "Skipped"
                st.markdown(
                    f"<div class='center-text'><p><strong>{label}:</strong> {percentage}</p></div>",
                    unsafe_allow_html=True,
                )

            count += 1

query_params = st.query_params  # Use st.query_params directly
code = query_params.get("code")  # Get the code directly

if code == None and st.session_state['auth_code'] == None:
    st.markdown(
        
            """
            <div style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
            <h1 style="font-size: 4rem; margin: 0; color: #1DB954;">SIMMPLIFY</h1>
            <p style="font-size: 1.5rem;">Track your habits and declutter your playlists to enjoy your favourite songs, more often!</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Step 1: Get the authentication URL
    auth_url = sp_oauth.get_authorize_url()

    st.markdown(f"""
            <div style="display: flex; justify-content: center;">
                <a href="{auth_url}">
                    <button class="button" style="background-color: #1DB954; text-align: center; color: #FFFFFF; border: none; padding: 15px 30px; font-size: 1rem; border-radius: 25px; cursor: pointer;">
                        Authenticate with Spotify
                    </button>
                </a>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown(
            """
            <div style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
            <hr style="border: 1px solid #1DB954; width: 100%; margin: 20px auto;" />

            <div style="margin-top: 20px;">
                <h2 style="color: #1DB954;">How It Works</h2>
                <p style="line-height: 1.6;">
                Tired of songs that don't hit the right vibe anymore? SIMMPLIFY tracks how often you skip songs on your playlists and helps you decide which tracks to keep or remove. Just log in with your Spotify account, let SIMMPLIFY do its magic, and enjoy a finely-tuned playlist that's perfect for you!
                </p>
            </div>
            <div style="margin-top: 20px;">
                <h2 style="color: #1DB954;">How To Use</h2>
                <p>Connect your Spotify account with the Button Above and listen like normal.</p>
                <p>Check back here in a week or two to see your suggested playlist updates!</p>
                <p>The Simmplify Data Section will calculate and sort your playlist songs by how often they are skipped.</p>
                <p>Use the buttons to automatically remove songs based on preference score.</p>
                <p>The Historical Data Section will show you a list of every song you have listened to and listening percentage.</p>
                <hr style="border: 1px solid #1DB954; width: 100%; margin: 20px auto;" />

            </div>
            """,
            unsafe_allow_html=True
        )


else:
    #After authentication, display the player and simmplify page
    
    st.markdown("""
        <div style="text-align: center; margin-top: 10px;">
            <h1 style="color: #1DB954; font-size: 4em; margin-bottom: 10px;">SIMMPLIFY</h1>
            <p style="font-size: 1.5em; color: #FFFFFF;">Track your habits and declutter your playlists to enjoy your favourite songs, more often!</p>
            <hr style="border: 1px solid #1DB954; width: 100%; margin: 20px auto;" />
        </div>
    """, unsafe_allow_html=True)

    st.markdown(
        """<div style="text-align: left">
            <h3 style="color: #1DB954; font-size: 2em;">Player:</h3>
        </div>""", unsafe_allow_html=True)
    
    player = st.empty()
    
    st.markdown("""
        <div style="text-align: left">
            <hr style="border: 1px solid #1DB954; width: 100%" />
            <h3 style="color: #1DB954; font-size: 2em;">Simmplify Data:</h3>
        </div>
    """, unsafe_allow_html=True)

    # Call the login function at the start of the script



    login()

    #Pull user information from database or spotify
    userName, userUri, userId = getUserInfo()
    useDbId = getUserId()
    storeTokensInDatabase()

    # Display historical data for all playlists
    historicalData = getHistoricalData(userUri)

    #Get users playlists, allow user to select a playlist
    userPlaylists = spotifyUsersPlaylists(userName)

    # Add the "Liked Songs" playlist to the DataFrame
    liked_songs = pd.DataFrame({'uri': [f'spotify:user:{userName}:collection'], 'name': ['Liked Songs'], 'owner.display_name': [userName], 'owner.id': [userId]})
    userPlaylists = pd.concat([userPlaylists, liked_songs], ignore_index=True)

    # Add "ALL" option to the list of playlist names
    playlist_options = ["ALL"] + list(userPlaylists["name"].unique())
    sde1, sde2, sde3 = st.columns(3)
    selectedPlaylistName = sde1.selectbox("Filter by Playlist", placeholder="-", options=playlist_options)

    simmplify = st.empty()

    st.markdown("""
        <div style="text-align: left">
            <hr style="border: 1px solid #1DB954; width: 100%" />
            <h3 style="color: #1DB954; font-size: 2em;">Biggest Hits</h3>
        </div>
    """, unsafe_allow_html=True)

    biggestHits = st.empty()

    st.markdown("""
        <div style="text-align: left">
            <hr style="border: 1px solid #1DB954; width: 100%" />
            <h3 style="color: #1DB954; font-size: 2em;">Biggest Misses</h3>
        </div>  
    """, unsafe_allow_html=True)

    biggestMisses = st.empty()


    if selectedPlaylistName == "ALL":
        selectedPlaylistUri = None  # No filtering by playlist
    else:
        selectedPlaylistUri = userPlaylists[userPlaylists["name"] == selectedPlaylistName]["uri"].values[0]

    st.session_state['SelectedPlaylist'] = selectedPlaylistUri

    summarizedListeningData = getSummarizedData(historicalData, selectedPlaylistUri, userPlaylists)
    topArtists, topSongs, bottomArtists, bottomSongs, bottomPlaylists, topPlaylists = summarizedAdvancedStats(historicalData)

    historicalData = format_historical_data(historicalData, selectedPlaylistName)

    st.markdown("""
        <div style="text-align: left">
            <hr style="border: 1px solid #1DB954; width: 100%" />
            <h3 style="color: #1DB954; font-size: 2em;">Historical Listening Data:</h3>
        </div>
    """, unsafe_allow_html=True)

    historical = st.empty()

    image_path = "C:/Users/NSimms/OneDrive - Geosyntec/Desktop/General Coding/Simmplify/frontend/images/background3.jpg"
    
    st.markdown(f"""
        <div style="text-align: center; padding: 10px; border: 2px solid #1DB954; border-radius: 10px; background-color: rgba(255, 255, 255, 0.0);">
            <h4 style="color: #1DB954; font-size: 1.5em; margin-bottom: 5px;">Creator Info:</h4>
            <img src="{image_path}">
            <p style="color: #1DB954; font-size: 1.0em; margin-bottom: 5px;">Noah Simms - Developer and Music Enthusiast</p>
            <a href="https://www.instagram.com/nsimm22/?hl=en" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">Instagram 🌟</a>
            <a href="https://github.com/nsimm11" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">GitHub 💻</a>
            <a href="https://ca.linkedin.com/in/noah-simms-360724162" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">LinkedIn 💼</a>
        </div>
    """, unsafe_allow_html=True)

    startTime = datetime.now(pytz.utc)

    while True:
    
        if (datetime.now(pytz.utc) - startTime).total_seconds() % 10 < 1:
            player_data = spotifyUserCurrentSongPlaying()
            if player_data is not None and not player_data.empty:
                userCurrentSongPlayingDict = player_data.to_dict('records')[0]
                if userCurrentSongPlayingDict["CurrentPlaylistUri"] == userName:
                    userCurrentSongPlayingDict["CurrentPlaylistUri"] = "spotify:user:" + userName + ":collection"
                else: userCurrentSongPlayingDict["CurrentPlaylistUri"] = "spotify:playlist:" + userCurrentSongPlayingDict["CurrentPlaylistUri"]
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

            if st.session_state["is_playing"] == True:
                if st.session_state["previous_song_name"] != userCurrentSongPlayingDict["name"]:
                    st.session_state["previous_song_name"] = userCurrentSongPlayingDict["name"]
                    historicalData = getHistoricalData(userUri)
                    summarizedListeningData = getSummarizedData(historicalData, selectedPlaylistUri, userPlaylists)
                    historicalData = format_historical_data(historicalData, selectedPlaylistName)

                c2.markdown(f'SONG: {userCurrentSongPlayingDict["name"]}')
                c2.markdown(f'Artists: {",".join(userCurrentSongPlayingDict["artists"])}')
                c2.markdown(f'Album: {userCurrentSongPlayingDict["album.name"]}')
                
                # Check if playlistName is not empty
                playlistName = userPlaylists[userPlaylists["uri"] == userCurrentSongPlayingDict["CurrentPlaylistUri"]]["name"]
                if not playlistName.empty:
                    c2.markdown(f'Playlist: {str(playlistName.values[0])}')
                elif userCurrentSongPlayingDict["CurrentPlaylistUri"] == userName:
                    c2.markdown('Playlist: Liked Songs')
                else:
                    c2.markdown('Playlist: Non-User Playlist')

                if "album.images" in userCurrentSongPlayingDict and userCurrentSongPlayingDict["album.images"] != "":
                    c3.image(userCurrentSongPlayingDict["album.images"], width=150)
                c2.progress(float(userCurrentSongPlayingDict["SongCurrentPosition"]) / userCurrentSongPlayingDict["duration_ms"])
                c1.markdown(f"User: {st.session_state['UserName']}")
            else:
                c2.markdown("## Paused")

        with simmplify.container():
            st.dataframe(summarizedListeningData, hide_index=True, use_container_width=True)

        with biggestHits.container():
            # Clear previous columns
            as1, as2, as3 = st.columns(3)

            # Display Most Listened to Artists
            with as1:
                display_stats(topArtists, "Most Listened to Artists", "Artist", display_percentage='listened')

            # Display Most Listened to Songs
            with as2:
                display_stats(topSongs, "Most Listened to Songs", "Song", display_percentage='listened')

            # Display Most Skipped Artists
            with as3:
                display_stats(topPlaylists, "Most Played Playlists", "Playlist", display_percentage='listened')


        with biggestMisses.container():
            # Clear previous columns
            bm1, bm2, bm3 = st.columns(3)

            # Display Most Skipped Artists
            with bm1:
                display_stats(bottomArtists, "Most Skipped Artists", "Artist", display_percentage='skipped')

            # Display Most Skipped Songs
            with bm2:
                display_stats(bottomSongs, "Most Skipped Songs", "Song", display_percentage='skipped')

            # Display Most Skipped Playlists
            with bm3:   
                display_stats(bottomPlaylists, "Most Skipped Playlists", "Playlist", display_percentage='skipped')

        with historical.container():
            st.dataframe(historicalData, hide_index=True, use_container_width=True)
        

        time.sleep(1)



