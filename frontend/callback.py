import streamlit as st
from spotipy.oauth2 import SpotifyOAuth
import os
import numpy as np
import requests
import certifi
from datetime import datetime, timedelta, timezone
import pandas as pd
from pandas import json_normalize
import time
import pytz
import matplotlib.pyplot as plt
import psycopg2
from sshtunnel import SSHTunnelForwarder
import tempfile

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
if 'conn' not in st.session_state:
    st.session_state['conn'] = ""
if 'cursor' not in st.session_state:
    st.session_state['cursor'] = ""
if 'server' not in st.session_state:
    st.session_state['server'] = None
if 'last_active' not in st.session_state:
    st.session_state.last_active = time.time()
if 'grace' not in st.session_state:
    st.session_state.grace = None

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing user-read-recently-played playlist-modify-private playlist-modify-public"

sp_oauth = SpotifyOAuth(client_id=st.secrets["spotify"]["CLIENT_ID"], 
                        client_secret=st.secrets["spotify"]["CLIENT_SECRET"],
                        redirect_uri=st.secrets["spotify"]["REDIRECT_URI"],
                        scope=SCOPE)

class GracefulSSHTunnel:
    def __init__(self, ssh_username, ssh_password, ssh_private_key, db_host, db_port, db_name, db_user, db_password):
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.tunnel = None
        self.conn = None
        self.temp_key_path = None

        # Write the private key to a temporary file
        with tempfile.NamedTemporaryFile("w", delete=False) as temp_key_file:
            temp_key_file.write(self.ssh_private_key)
            self.temp_key_path = temp_key_file.name

    def start_tunnel(self):
        attempts = 0
        max_attempts = 5
        while attempts < max_attempts:
            try:
                self.tunnel = SSHTunnelForwarder(
                    ssh_address_or_host=('ssh.pythonanywhere.com', 22),
                    ssh_username=self.ssh_username,
                    ssh_pkey=self.temp_key_path,
                    ssh_private_key_password=self.ssh_password,
                    remote_bind_address=(self.db_host, self.db_port),
                    local_bind_address=('127.0.0.1', 43219)
                )
                self.tunnel.start()
                print("SSH Tunnel started.")
                return self.tunnel
            except Exception as e:
                attempts += 1
                print(f"Attempt {attempts} failed: {e}")
                time.sleep(2)  # Wait for 2 seconds before retrying

        st.warning("Failed to start SSH Tunnel after 5 attempts.")
        raise RuntimeError("Failed to start SSH Tunnel after 5 attempts.")

    def connect_to_db(self):
        attempts = 0
        max_attempts = 5
        while attempts < max_attempts:
            try:
                if not self.tunnel or not self.tunnel.is_active:
                    raise RuntimeError("SSH tunnel is not active. Start the tunnel before connecting to the database.")
                
                self.conn = psycopg2.connect(
                    host='127.0.0.1',  # Local address of the tunnel
                    port=self.tunnel.local_bind_port,
                    database=self.db_name,
                    user=self.db_user,
                    password=self.db_password
                )
                print("Database connection established.")
                return self.conn
            except Exception as e:
                attempts += 1
                print(f"Attempt {attempts} to connect to the database failed: {e}")
                time.sleep(3)  # Wait for 2 seconds before retrying

        st.warning("Failed to connect to the database after 5 attempts.")
        raise RuntimeError("Failed to connect to the database after 5 attempts.")

    def close_resources(self):
        if self.conn:
            self.conn.close()
            print("Database connection closed.")
        if self.tunnel and self.tunnel.is_active:
            self.tunnel.stop()
            print("SSH Tunnel closed.")


# Track user activity
if 'last_active' not in st.session_state:
    st.session_state.last_active = time.time()

# Update activity timestamp
st.session_state.last_active = time.time()

# Initialize and manage resources
if 'grace' not in st.session_state or st.session_state.grace == None:
    grace = GracefulSSHTunnel(
        ssh_username = st.secrets["ssh"]["username_ssh"],
        ssh_password = st.secrets["ssh"].get("private_key_passphrase", None),
        ssh_private_key = st.secrets["ssh"]["private_key_ssh"],
        db_user = st.secrets["postgres"]["username_post"],
        db_password = st.secrets["postgres"]["password_post"],
        db_name = st.secrets["postgres"]["database_post"],
        db_host = st.secrets["postgres"]["hostname"],
        db_port = st.secrets["postgres"]["port"]
    )
    st.session_state.grace = grace
else: grace = st.session_state.grace










def hide_streamlit_style():
    hide_style = """
    <style>
        header {display: none !important;}
        footer {display: none !important;}
        section.main > div {padding: 0rem 5rem 0 rem;}
        #MainMenu {display: none !important;}
        section {top: 0px !important;}
    </style>
    """
    st.markdown(hide_style, unsafe_allow_html=True)

hide_streamlit_style()


def errorLog(errorMessage):
    f = open("error.txt", "a")
    f.write(f"{datetime.now()} - {errorMessage} \n")
    f.close()


#General Query funciton, returns a dataframe. Use this instead of pd.read_sql
def getQuery(query, params=None):
    if params is None:
        params = []
    try:
        st.session_state["cursor"].execute(query, params)
        Data = pd.DataFrame.from_records(
            st.session_state["cursor"].fetchall(), 
            columns=[col.name for col in st.session_state["cursor"].description]
        )
        return Data
    except psycopg2.Error as e:
        st.write(f"Error executing query: {e}")
        return pd.DataFrame()  # Return an empty DataFrame on error


def getUserId(userUri):
    
    cursor = st.session_state["cursor"]

    if userUri != "" and st.session_state["UserUri"] == "":
        st.session_state["UserUri"] = userUri
        userTokens = getQuery("SELECT * FROM USERTOKENS WHERE useruri = %s", (userUri,))

    # Ensure the correct table name and schema
    userUri = st.session_state['UserUri'].strip()
    userIdQuery = f"SELECT * FROM USERS WHERE useruri = '{userUri}';"

    if userUri == "" or userUri == None:
        st.write("Trying to get users info without userUri")

    userId = getQuery(userIdQuery, (userUri,))
    
    if len(userId.dropna()) > 0:
        userId = userId.iloc[0].to_dict()
        if (st.session_state["UserName"]) != userId["username"]: 
            errorLog("Username in DB and username from Spotify do not match")
            st.write("Please reauthenticate from the home page")
            return None
            
        else:
            st.toast(f"Thanks for returning {userId['username']}!")
            st.session_state["UserDbId"] = userId["userid"]
        return userId["userid"]
    else:
        newUserQuery = "SELECT MAX(userId) FROM USERS"
        newUserId = getQuery(newUserQuery) #returns dataframe with max in columns, length is still 1, but check if input is none
        if newUserId["max"].values[0] is None:
            newUserId = 1
        else:
            newUserId = int(newUserId["max"].values[0]) + 1 

        # Convert current time to Unix timestamp
        utc_now = datetime.now(pytz.utc)
        unix_timestamp = int(utc_now.timestamp())

        insertNewUserQuery = """
            INSERT INTO USERS (dbid, useruri, userid, username, lastlogin) 
            VALUES (%s, %s, %s, %s, %s);
        """
        userName = st.session_state["UserName"]

        # Execute and commit the query with the provided parameters
        cursor.execute(insertNewUserQuery, (newUserId, userUri, newUserId, userName, unix_timestamp))
        conn.commit()
        st.session_state["UserDbId"] = newUserId

        return newUserId


def getRefreshTokenFromUserUri(userUri):
    userTokens = getQuery("SELECT * FROM USERTOKENS WHERE useruri = %s", [userUri])
    if len(userTokens) > 0:
        st.session_state['access_token'] = userTokens.iloc[0]['accesstoken']
        st.session_state["access_token_endTime"] = pd.to_datetime(userTokens.iloc[0]['accesstokenendtime'])
        st.session_state["refresh_token"] = userTokens.iloc[0]['refreshtoken']
    else:
        return None


def login():

    if query_params_user != None:
        #Pull refresh token from database using username from query params in usertokens
        getRefreshTokenFromUserUri(query_params_user)

    if st.session_state['access_token'] != '' and st.session_state["access_token_endTime"] != '' and st.session_state["refresh_token"] != '':
        return True
    
    query_params = st.query_params  # Use st.query_params directly
    code = query_params.get("code")  # Get the code directly

    if code:
        # Store the code in session state
        st.session_state['auth_code'] = code  
        # Proceed with token exchange using the new function
        exchange_code_for_token(code)  # Call the new function to exchange the code for a token

    else:
        st.warning("Authorization code not found in URL. Please try again.")


def addUsernametoQueryParams(username):
    query_params = st.query_params
    query_params["username"] = username
    st.query_params = query_params


def exchange_code_for_token(auth_code):
    token_url = "https://accounts.spotify.com/api/token"
    payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': st.secrets["spotify"]["REDIRECT_URI"],
        'client_id': st.secrets["spotify"]["CLIENT_ID"],
        'client_secret': st.secrets["spotify"]["CLIENT_SECRET"]
    }
    
    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        token_info = response.json()
        st.session_state['access_token'] = token_info['access_token']
        st.session_state["access_token_endTime"] = datetime.now(pytz.utc) + timedelta(seconds=token_info['expires_in'])
        st.session_state["refresh_token"] = token_info['refresh_token']
        requestsAsJsonUser = submitRequest("https://api.spotify.com/v1/me", "Get Users PlaybackState", {})
        if requestsAsJsonUser and "uri" in requestsAsJsonUser:
            st.session_state["UserUri"] = requestsAsJsonUser["uri"]
        st.toast(f"You are now authenticated!, expires at {st.session_state['access_token_endTime']}")
    else:
        st.toast(f"Error fetching the token: {response.status_code} - {response.text}")


def getUserInfo():
    try:
        requestsAsJsonUser = submitRequest("https://api.spotify.com/v1/me", "Get Users PlaybackState", {})
        
        if requestsAsJsonUser is None:
            st.markdown("Failed to retrieve user information. Please re-authenticate from the login page <a href='/'>here</a>.", unsafe_allow_html=True)
            return None, None, None

        userUri = requestsAsJsonUser["uri"]

        st.session_state["UserName"] = str(requestsAsJsonUser["display_name"])
        st.session_state["UserUri"] = userUri
        st.session_state["UserId"] = str(requestsAsJsonUser["id"])

        addUsernametoQueryParams(st.session_state["UserUri"])

        return st.session_state["UserName"], st.session_state["UserUri"], st.session_state["UserId"]

    except requests.exceptions.RequestException as e:
        errorLog(f"API request error in getUserInfo: {e}")
        st.warning("An error occurred while connecting to the Spotify API. Please try again later.")
        return None, None, None
    

def storeTokensInDatabase():

    if not st.session_state["UserUri"]:
        errorLog("UserUri is empty. Cannot proceed with token operations.")
        st.warning("UserUri is not set. Please try logging in again.")
        return
    elif st.session_state["UserUri"] != "" and st.session_state["refresh_token"] == "":
        userTokens = getQuery("SELECT * FROM USERTOKENS WHERE useruri = %s", [st.session_state["UserUri"]])
        if len(userTokens) > 0:
            if pd.to_datetime(userTokens.iloc[0]['accesstokenendtime']) > datetime.now(pytz.utc):
                st.session_state['access_token'] = userTokens.iloc[0]['accesstoken']
                st.session_state["access_token_endTime"] = pd.to_datetime(userTokens.iloc[0]['accesstokenendtime'])
                st.session_state["refresh_token"] = userTokens.iloc[0]['refreshtoken']
                st.session_state['UserDbId'] = int(userTokens.iloc[0]['dbid'])
                st.toast(f"You are now authenticated!, expires at {st.session_state['access_token_endTime']}")
            else:
                st.toast("Your access token has expired. Please re-authenticate.")
        else:
            st.toast("No user tokens found. Please re-authenticate.")

    db_id = st.session_state['UserDbId']
    access_token = st.session_state['access_token']
    expires_at_utc = pd.to_datetime(st.session_state["access_token_endTime"]).tz_convert('UTC') - timedelta(minutes=3)
    refresh_token = st.session_state['refresh_token']
    userUri = st.session_state.get('UserUri', '').strip()

    # Check if a token entry already exists for this user
    check_token_query = "SELECT id FROM USERTOKENS WHERE dbid = %s"
    cursor.execute(check_token_query, (db_id,))
    result = cursor.fetchone()

    if result:
        # Update existing token entry
        update_token_query = """
        UPDATE USERTOKENS 
        SET accesstoken = %s, accesstokenendtime = %s, refreshtoken = %s, lastupdated = %s, useruri = %s
        WHERE dbid = %s;
        """
        cursor.execute(update_token_query, (access_token, expires_at_utc, refresh_token, datetime.now(pytz.utc), userUri, db_id))
    else:
        # Insert new token entry
        insert_token_query = """
        INSERT INTO USERTOKENS (dbid, accesstoken, accesstokenendtime, refreshtoken, lastupdated, useruri) 
        VALUES (%s, %s, %s, %s, %s, %s);
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

def spotifyUsersPlaylists(username, userPlaylists, offset=0, limit=50):
    params = {"limit": limit, 'offset': offset}
    requestsAsJsonPlaylists = submitRequest("https://api.spotify.com/v1/me/playlists", "Get Users History", params)

    if len(requestsAsJsonPlaylists["items"]) == 0:
        print("Request Empty - No Playlists")
        errorLog("Request Empty - No Playlists")
        return userPlaylists

    else:
        loopPlaylists = (json_normalize(requestsAsJsonPlaylists["items"]))[["uri", "name", "owner.display_name", "owner.id"]]
        userPlaylists = pd.concat([userPlaylists, loopPlaylists[(loopPlaylists["owner.id"] == username) | (loopPlaylists["owner.display_name"] == username)]])


    if requestsAsJsonPlaylists["total"] >= limit:
        userPlaylists = spotifyUsersPlaylists(username, userPlaylists, offset+limit, limit)
        return userPlaylists
    else:
        userPlaylists = pd.concat([userPlaylists, pd.DataFrame.from_dict({"uri": [f"spotify:user:{username}:collection"], "name": ["Liked Songs"], "owner.display_name": [username], "owner.id": [username]})])

    return userPlaylists

def getHistoricalData(userUri, userPlaylists):

    # Join with SONGDATA table to get song details
    historicalDataQuery = """
    SELECT 
        ld.useruri, 
        ld.playlisturi,
        si.songname,
        si.artistname,
        si.albumname,
        si.songlengthms,
        ld.percentlistened,
        ld.percentskipped,
        ld.songuri,
        CAST(ld.listeningstarttime AS TIMESTAMPTZ) AS listeningstarttime
    FROM LISTENERDATA ld
    JOIN SONGDATA si ON ld.songuri = si.songuri
    WHERE ld.useruri = %s
    ORDER BY ld.listeningstarttime DESC
    """
    historicalData = getQuery(historicalDataQuery, [userUri])

    # Convert listeningStartTime to user's local timezone and round to nearest second
    user_timezone = pytz.timezone('America/New_York')  # Replace with the user's actual timezone
    historicalData['listeningstarttime'] = historicalData['listeningstarttime'].apply(
        lambda x: x.replace(tzinfo=pytz.utc).astimezone(user_timezone).replace(microsecond=0)
    )

    playlist_map = userPlaylists.set_index('uri')['name'].to_dict()
    historicalData['Playlist Name'] = historicalData['playlisturi'].map(playlist_map).fillna("Non-User Playlist")

    return historicalData

def highlight_historical_data_row(row):
    listened_percentage = row['Percentage Listened']
    # Use the RdYlGn colormap to determine the background color
    color = plt.cm.RdYlGn(listened_percentage / 100)  # Normalize to [0, 1]
    return [
        f'background-color: rgba({int(color[0] * 255)}, {int(color[1] * 255)}, {int(color[2] * 255)}, 1); color: {"black" if 45 <= row["Percentage Listened"] <= 55 else "white"}' 
        for _ in row
    ]

def format_historical_data(df, playlist_name):
    # Limit to the last 150 rows since the data will become too large to display

    df = df.sort_values(by='listeningstarttime', ascending=False)
    df = df.head(150)

    df["Seconds Listened"] = (df["percentlistened"]/100) * df["songlengthms"]/1000
    df["Seconds Skipped"] = (df["percentskipped"]/100) * df["songlengthms"]/1000

    # Rename columns for better readability
    df = df.rename(columns={
        'songname': 'Song Name',
        'artistname': 'Artist Name',
        'albumname': 'Album Name',
        'percentlistened': 'Percentage Listened',
        'percentskipped': 'Percentage Skipped',
        'listeningstarttime': 'Listening Start Time'
    })

    # Drop the playlistUri and songUri columns
    df = df.drop(columns=['playlisturi', 'songuri'], errors='ignore')
    df = df.sort_values(by='Listening Start Time', ascending=False)

    # Reorder columns to move Playlist Name to the first position
    columns_order = ['Playlist Name', 'Song Name', 'Artist Name', 'Album Name', 'Seconds Listened', 'Seconds Skipped', 'Percentage Listened', 'Percentage Skipped', 'Listening Start Time']
    df = df[columns_order]

    # Apply gradient formatting to all columns based on the 'Percentage Listened'
    styled_df = df.style.apply(highlight_historical_data_row, axis=1)

    return styled_df

def getSummarizedData(historicalData):

    # Group by 'playlistUri', 'songName', 'artistName', 'albumName' and aggregate sums
    summarizedData = historicalData.groupby(['playlisturi', 'songname', 'artistname', 'albumname', 'songuri','Playlist Name']).agg({
        'percentlistened': 'sum',
        'percentskipped': 'sum',
        'listeningstarttime': 'count'  # Count the number of times the song has been listened to in this playlist
    }).reset_index()

    # Rename columns for better readability
    summarizedData = summarizedData.rename(columns={
        'songname': 'Song Name',
        'artistname': 'Artist Name',
        'albumname': 'Album Name',
        'percentlistened': 'Listened Total',
        'percentskipped': 'Skipped Total',
        'listeningstarttime': 'Play Count'  # Rename the count column
    })

    # Add a new column for Preference Score
    summarizedData['Preference Score'] = summarizedData['Listened Total'] - summarizedData['Skipped Total']

    # Add a new column for Preference Rate
    summarizedData['Preference Rate'] = np.round(summarizedData['Preference Score'] / summarizedData['Play Count'].replace(0, 1), 2)  # Avoid division by zero

    # Sort by Preference Rate with negative values first, then 0 to 100, and finally 100
    summarizedData['Preference Rate'] = summarizedData['Preference Rate'].astype(int)  # Ensure it's float for proper sorting
    summarizedData = summarizedData.sort_values(by='Preference Score', ascending=True)  # Sort in ascending order

    return summarizedData

# Apply conditional formatting based on Preference Score
def highlight_row(row):

    score = row['Preference Score']
    if score >= 100:
        color = plt.cm.RdYlGn(0.99)
    elif score < -100:
        color = plt.cm.RdYlGn(0.25)
    elif score < -300:
        color = plt.cm.RdYlGn(0)
    else:
        normalized_score = (score + 300) / 400  # Normalize to [0, 1]
        color = plt.cm.RdYlGn(normalized_score)  # Get color from colormap

    return [
        f'background-color: rgba({int(color[0] * 255)}, {int(color[1] * 255)}, {int(color[2] * 255)}, 1); color: {"black" if -300 <= row["Preference Score"] <= 100 else "white"}' 
        for _ in row
    ]

def filterAndStyleSummarizedData(summarizedData, selectedPlaylistUri, userPlaylists, playMin, scoreMin, scoreMax):
    if selectedPlaylistUri is not None:
        summarizedData = summarizedData[summarizedData['playlisturi'] == selectedPlaylistUri]
    
    summarizedData = summarizedData[summarizedData['Play Count'] >= playMin]
    summarizedData = summarizedData[summarizedData['Preference Score'] >= scoreMin]
    summarizedData = summarizedData[summarizedData['Preference Score'] <= scoreMax]

    # Drop the 'playlistUri' column before returning
    stylesummarizedData = summarizedData.drop(columns=['playlisturi'])

    stylesummarizedData = stylesummarizedData[["Playlist Name", "Song Name", "Artist Name", "Album Name", "Play Count", "Preference Score", "Preference Rate"]]

    styled_summarizedData = stylesummarizedData.style.apply(highlight_row, axis=1)

    return styled_summarizedData, len(summarizedData), summarizedData

def create_summarized_data_for_artists(summarizedDataForArtists):
    # Split the 'Artist Name' column by comma and expand it into separate rows
    summarizedDataForArtists['Artist Name'] = summarizedDataForArtists['Artist Name'].str.split(", ")
    summarizedDataForArtists = summarizedDataForArtists.explode('Artist Name').reset_index(drop=True)

    return summarizedDataForArtists

# Function to remove 'spotify:track:' prefix if present
def remove_spotify_track_prefix(uri):
    return uri.replace('spotify:track:', '')


def summarizedAdvancedStats(summarizedData):

    summarizedDataForArtists = create_summarized_data_for_artists(summarizedData.copy())

    # Apply the function to the 'songuri' column
    summarizedData['songuri'] = summarizedData['songuri'].apply(remove_spotify_track_prefix)
    
    # Apply the function to the 'songuri' column
    summarizedData['songuri'] = summarizedData['songuri'].apply(remove_spotify_track_prefix)

    bottomArtists = summarizedDataForArtists.groupby('Artist Name').agg({'Preference Score': 'sum'}).reset_index().sort_values(by='Preference Score', ascending=True).head(5)
    
    bottomSongs = summarizedData.groupby(['Song Name', 'Artist Name']).agg({'Preference Score': 'sum'}).reset_index().sort_values(by='Preference Score', ascending=True).head(5)
    
    topSongs = summarizedData.groupby(['Song Name', 'Artist Name']).agg({'Preference Score': 'sum'}).reset_index().sort_values(by='Preference Score', ascending=False).head(5)
    
    topArtists = summarizedDataForArtists.groupby('Artist Name').agg({'Preference Score': 'sum'}).reset_index().sort_values(by='Preference Score', ascending=False).head(5)

    playlistRankings = summarizedData.groupby(['Playlist Name', 'playlisturi']).agg({
        'Preference Score': 'sum',
        'Play Count': 'sum'
    }).reset_index()

    playlistRankings = playlistRankings[playlistRankings["Playlist Name"] != "Non-User Playlist"]

    playlistRankings['Preference Rate'] = ((playlistRankings['Preference Score'] / playlistRankings['Play Count'] + 100) / 200) * 100
    playlistRankings = playlistRankings.sort_values(by='Preference Rate', ascending=False)
    topPlaylists = playlistRankings.head(5)
    bottomPlaylists = playlistRankings.tail(5).sort_values(by='Preference Rate', ascending=True)

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

    #First look for songUris in SONGDATA by artistName, if there are multiple artist names, take the first one by delimiting by ","
    songUri = getQuery("SELECT songUri FROM SONGDATA WHERE artistName = %s", (artistName.split(",")[0].strip(),))

    #Check if query comes back empty
    if len(songUri) == 0:
        return None

    # Define the endpoint for searching the artist
    search_url = "https://api.spotify.com/v1/tracks/" + str(songUri["songuri"].iloc[0])
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
def get_playlist_image_url(playlistUri):

    if "playlist:" in playlistUri:
        playlistUri = playlistUri.split(":")[2]

    search_url = "https://api.spotify.com/v1/playlists/" + str(playlistUri)
    response = submitRequest(search_url, "Get Playlist Image", {})

    if response and "images" in response and response["images"]:
        url = response["images"][0]["url"]
        return url
    else:
        return "https://via.placeholder.com/150/CCCCCC/FFFFFF?text=No+Image"  # Placeholder grey box


def get_NoahImage():
    
    search_url = "https://api.spotify.com/v1/users/nsimm22/"
    response = submitRequest(search_url, "Get Playlist Image", {})

    if response and "images" in response and len(response["images"]) > 0:
        image_url = response["images"][0]["url"]
    else:
        image_url = "https://via.placeholder.com/150/CCCCCC/FFFFFF?text=No+Image"  # Placeholder grey box

    return image_url

# Function to display statistics for artists or songs
def display_stats(column, title, statType, display_percentage):
    st.markdown("""
                <style>
                    .center-text {
                        text-align: center;
                        }
                </style>""", unsafe_allow_html=True)
    st.markdown(f"<h4 style='color: #1DB954; text-align: center;'>{title}</h4>", unsafe_allow_html=True)
    if statType == "Artist" or statType == "Song":
        st.markdown(f"""<div style='color: #FFFFFF; text-align: center; padding: 10px;'>
                <strong>Metric: Total Score</strong>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style='color: #FFFFFF; text-align: center; padding: 10px;'>
                        <strong>Metric: Average Percent Listened</strong>
                    </div>""", unsafe_allow_html=True)
    count = 1
    if len(column) > 0:
        for index, item in column.iterrows():
            # Determine if it's the last row
            border_style ="1px solid #ddd"
            
            # Create a row for each item using HTML and CSS
            row_html = f"""
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; border-top: {border_style};">
                <div style="flex: 0.5; text-align: center;">
                    <span style="font-size: 2em; font-weight: bold; color: rgba(255, 255, 255, 0.8);">{count}</span>
                </div>
                <div style="flex: 1.5; text-align: center;">
                    {item['Artist Name'] if statType == 'Artist' else f"{item['Song Name']} by {item['Artist Name']}" if statType == 'Song' else userPlaylists[userPlaylists['uri'] == item['playlisturi']]['name'].values[0] if item['playlisturi'] in userPlaylists['uri'].values else 'Non-User Playlist'}
                </div>
                <div style="flex: 1; text-align: center;">
                    <img src="{get_artist_image_url(item['Artist Name']) if statType == 'Artist' else get_album_cover_url(item['Song Name']) if statType == 'Song' else get_playlist_image_url(item.playlisturi)}" width="80" height="80" style="border-radius: 4px; object-fit: cover; object-position: 50% 50%; padding: 5px;">
                </div>
                <div style="flex: 1; text-align: center;">
                    <p> {item['Preference Score'] if statType == "Artist" or statType == "Song" else np.round(item['Preference Rate'],2)}%</p>
                </div>
            </div>
            """
            st.markdown(row_html, unsafe_allow_html=True)
            count += 1
    else:
        st.markdown(f"<div class='center-text' style='color: #FFFFFF; text-align: center;'>No songs yet! Start listening and come back soon!</div>", unsafe_allow_html=True)

def clearFromSpotifyPlaylist(playlistUri, songUris):
    # Extract the playlist ID from the URI
    playlist_id = playlistUri.split(":")[-1]  # Get the last part after 'playlist:'
    urlForRemoval = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

    tracksToRemove = []
    for songUri in songUris["songuri"]:
        tracksToRemove.append({"uri": "spotify:track:" + songUri})

    print(f"Deleting from: {urlForRemoval}")
    print(f"Tracks to remove: {tracksToRemove}")  # Debugging output

    # Modify the request to be a DELETE request
    response = requests.delete(urlForRemoval, headers={"Authorization": f"Bearer {st.session_state['access_token']}"}, json={"tracks": tracksToRemove})

    print("Response: ", response.json())  # Print the response JSON for better debugging

    return True

def clearFromDatabase(playlistUri, toBeClearedDf):
    for index, row in toBeClearedDf.iterrows():
        deleteQuery = f"DELETE FROM LISTENERDATA WHERE useruri = '{st.session_state['UserUri']}' AND songuri = '{row['songuri']}' AND playlisturi = '{playlistUri}'"
        
        cursor.execute(deleteQuery)
        conn.commit()

def clearFromSpotify(toBeClearedDf):

    playlistUris = list(toBeClearedDf["playlisturi"].unique())

    for playlistUri in playlistUris:
        clearFromSpotifyPlaylist(playlistUri, toBeClearedDf[toBeClearedDf["playlisturi"] == playlistUri])
        clearFromDatabase(playlistUri, toBeClearedDf[toBeClearedDf["playlisturi"] == playlistUri])

def removeUser():

    # Get the user's URI
    userUri = st.session_state["UserUri"]

    # Delete the user's data from the database
    cursor.execute("DELETE FROM USERS WHERE useruri = %s", (userUri,))
    cursor.execute("DELETE FROM USERTOKENS WHERE useruri = %s", (userUri,))
    conn.commit()

    # Clear the session state
    st.session_state["access_token"] = ""
    st.session_state["access_token_endTime"] = ""
    st.session_state["refresh_token"] = ""
    st.session_state["UserUri"] = ""
    st.session_state["UserDbId"] = ""
    st.session_state["UserName"] = ""

    st.rerun()

try:
    grace.start_tunnel()
    conn = grace.connect_to_db()
    st.session_state["conn"] = conn

    # Example query: Fetching data from the database
    cursor = conn.cursor()
    st.session_state["cursor"] = cursor

    # Example infinite loop to simulate app behavior
    timeout = 180  # Timeout in seconds

    query_params = st.query_params  # Use st.query_params directly
    if "username" in query_params:
        query_params_user = query_params.get("username")
    else:
        query_params_user = None
    code = query_params.get("code")  # Get the code directly

    if code == None and st.session_state['auth_code'] == None and query_params_user == None:
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

                </div>
                """,
                unsafe_allow_html=True
            )
        
        image_path = get_NoahImage()

        st.markdown(f"""
            <div style="text-align: center; padding: 10px; border: 2px solid #1DB954; border-radius: 10px; background-color: rgba(255, 255, 255, 0.0);">
                <h4 style="color: #1DB954; font-size: 1.5em; margin-bottom: 5px;">Creator Info:</h4>
                <img src="{image_path}" width="80" height="80" style="border-radius: 50%; object-fit: cover; object-position: 40% 50%;">
                <p style="color: #1DB954; font-size: 1.0em; margin-bottom: 5px;">Noah Simms - Developer and Music Enthusiast</p>
                <a href="https://www.instagram.com/nsimm22/?hl=en" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">Instagram 🌟</a>
                <a href="https://github.com/nsimm11" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">GitHub 💻</a>
                <a href="https://ca.linkedin.com/in/noah-simms-360724162" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">LinkedIn 💼</a>
            </div>
        """, unsafe_allow_html=True)


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

        cursor = st.session_state["cursor"]
        conn = st.session_state["conn"]


        # Call the login function at the start of the script
        login()

        #Pull user information from database or spotify
        userName, userUri, userId = getUserInfo()
        if st.session_state["UserUri"] != userUri and st.session_state["UserUri"] != "":
            userName, userUri, userId = getUserInfo()
        if userName is None and userUri is None and userId is None:
            st.warning("No user information found, please authenticate again.")
            st.stop()
        useDbId = getUserId(userUri)
        storeTokensInDatabase()

        #Get users playlists, allow user to select a playlist
        userPlaylists = spotifyUsersPlaylists(userName, pd.DataFrame())

        # Display historical data for all playlists
        historicalData = getHistoricalData(userUri, userPlaylists)
        summarizedData = getSummarizedData(historicalData)

        # Add the "Liked Songs" playlist to the DataFrame
        liked_songs = pd.DataFrame({'uri': [f'spotify:user:{userName}:collection'], 'name': ['Liked Songs'], 'owner.display_name': [userName], 'owner.id': [userId]})
        userPlaylists = pd.concat([userPlaylists, liked_songs], ignore_index=True)

        # Add "ALL" option to the list of playlist names
        playlist_options = ["ALL"] + list(userPlaylists["name"].unique())
        st.markdown("##### Filters:")
        sde1, sde2, sde3 = st.columns(3)
        selectedPlaylistName = sde1.selectbox("Filter by Playlist", placeholder="-", options=playlist_options)
        if len(summarizedData) > 0:
            playMin = sde2.slider("Filter by Minimum Number of Plays", min_value=1, max_value=max(summarizedData["Play Count"])+1, value=1)
            scoreMin_start = min(summarizedData["Preference Score"])
            scoreMin_end = max(summarizedData["Preference Score"])
            scoreMin, scoreMax = sde3.slider("Filter By Maximum Preference Score", min_value=scoreMin_start-1, max_value=scoreMin_end+1, value=[scoreMin_start, 0])
        else:
            playMin = 1
            scoreMin = 0
            scoreMax = 100

        if selectedPlaylistName == "ALL":
            selectedPlaylistUri = None  # No filtering by playlist
        else:
            selectedPlaylistUri = userPlaylists[userPlaylists["name"] == selectedPlaylistName]["uri"].values[0]

        st.session_state['SelectedPlaylist'] = selectedPlaylistUri

        summarizedListeningData, lengthPostFilter, filteredSummarizedData = filterAndStyleSummarizedData(summarizedData.copy(), selectedPlaylistUri, userPlaylists, playMin, scoreMin, scoreMax)
        topArtists, topSongs, bottomArtists, bottomSongs, bottomPlaylists, topPlaylists = summarizedAdvancedStats(summarizedData)

        historicalDataStyled = format_historical_data(historicalData, selectedPlaylistName)    

        simmplify = st.empty()


        cb1, cb2, cb3, cb4 = st.columns([4,4,4,6])

        with cb1.expander("Remove Orange Songs (Score < -100)"):
            orange_songs = filteredSummarizedData[filteredSummarizedData["Preference Score"] < -100]
            st.warning(f"This will remove {len(orange_songs)} songs which have a score less than -100 from Playlist: {selectedPlaylistName}.")
            clearYellowSongsButton = st.button("Clear Yellow Songs")
            if clearYellowSongsButton:
                clearFromSpotify(orange_songs)
        with cb2.expander("Remove Red Songs (Score < -300)"):
            red_songs = filteredSummarizedData[filteredSummarizedData["Preference Score"] < -300]
            st.warning(f"This will remove {len(red_songs)} songs from Playlist: {selectedPlaylistName}.")
            clearRedSongsButton = st.button("Clear Red Songs")
            if clearRedSongsButton:
                clearFromSpotify(red_songs)
        with cb3.expander("Clear Filtered Songs"):
            st.warning(f"This will remove {lengthPostFilter} songs from Playlist: {selectedPlaylistName}.")
            filteredSongsButton = st.button("Clear Filtered Songs")
            if filteredSongsButton:
                clearFromSpotify(filteredSummarizedData)

        st.markdown("""
            <div style="text-align: center">
                <hr style="border: 1px solid #1DB954; width: 100%" />
                <h3 style="color: #1DB954; font-size: 2em;">Biggest Hits</h3>
            </div>
        """, unsafe_allow_html=True)

        biggestHits = st.empty()

        st.markdown("""
            <div style="text-align: center">
                <hr style="border: 1px solid #1DB954; width: 100%" />
                <h3 style="color: #1DB954; font-size: 2em;">Biggest Misses</h3>
            </div>  
        """, unsafe_allow_html=True)

        biggestMisses = st.empty()

        st.markdown("""
            <div style="text-align: left">
                <hr style="border: 1px solid #1DB954; width: 100%" />
                <h3 style="color: #1DB954; font-size: 2em;">Historical Listening Data (Last 150 Songs):</h3>
            </div>
        """, unsafe_allow_html=True)

        historical = st.empty()

        image_path = get_NoahImage()

        st.markdown(f"""
            <div style="text-align: center; padding: 10px; border: 2px solid #1DB954; border-radius: 10px; background-color: rgba(255, 255, 255, 0.0);">
                <h4 style="color: #1DB954; font-size: 1.5em; margin-bottom: 5px;">Creator Info:</h4>
                <img src="{image_path}" width="80" height="80" style="border-radius: 50%; object-fit: cover; object-position: 40% 50%;">
                <p style="color: #1DB954; font-size: 1.0em; margin-bottom: 5px;">Noah Simms - Developer and Music Enthusiast</p>
                <a href="https://www.instagram.com/nsimm22/?hl=en" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">Instagram 🌟</a>
                <a href="https://github.com/nsimm11" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">GitHub 💻</a>
                <a href="https://ca.linkedin.com/in/noah-simms-360724162" style="color: #1DB954; text-decoration: none; margin: 0 5px; font-weight: bold; transition: color 0.3s;">LinkedIn 💼</a>
            </div>
        """, unsafe_allow_html=True)

        startTime = datetime.now(pytz.utc)

        with biggestHits.container():

            # Clear previous columns
            as1, as2, as3 = st.columns(3, gap="medium", border=True)

            # Display Most Listened to Artists
            with as1:
                display_stats(topArtists, "Most Played Artists", "Artist", display_percentage='listened')

            # Display Most Listened to Songs
            with as2:
                display_stats(topSongs, "Most Played Songs", "Song", display_percentage='listened')

            # Display Most Skipped Artists
            with as3:
                display_stats(topPlaylists, "Most Played Playlists", "Playlist", display_percentage='listened')

        with biggestMisses.container():
            # Clear previous columns
            bm1, bm2, bm3 = st.columns(3, gap="medium", border=True)

            # Display Most Skipped Artists
            with bm1:
                display_stats(bottomArtists, "Most Skipped Artists", "Artist", display_percentage='skipped')

            # Display Most Skipped Songs
            with bm2:
                display_stats(bottomSongs, "Most Skipped Songs", "Song", display_percentage='skipped')

            # Display Most Skipped Playlists
            with bm3:   
                display_stats(bottomPlaylists, "Most Skipped Playlists", "Playlist", display_percentage='skipped')

        st.markdown(""" 
            <div style="text-align: center" padding: 10px;>
            </div>
        """, unsafe_allow_html=True) 

        # Inject custom CSS to style the expander, expander should have the spotify green border
        custom_css = """
        <style>
            .stExpander {
                border: 1px solid #1DB954 !important; /* Thicker green border */
                border-radius: 8px; /* Optional: adjust border radius */
                box-shadow: none !important; /* Remove any shadows */
                text-align: cemter; /* Align text to the left */
            }
        </style>
        """

        # Inject CSS using st.markdown
        st.markdown(custom_css, unsafe_allow_html=True)

        with st.expander("Stop Tracking"):
            stopTracking = st.button("Stop Tracking")
            if stopTracking:
                removeUser()
        
        with st.expander("Privacy Policy"):

            st.markdown("""
                        <div style=color:#1DB954; padding:10px;">
                            <h2>Privacy Policy for Simmplify</h2>
                        </div>

                        <p><strong>Effective Date:</strong> 13/01/2025</p>

                        <p>At Simmplify, we are committed to protecting your privacy and being transparent about how we collect and use your data. This Privacy Policy outlines the types of data we collect from you when you use our web app and how we use, store, and safeguard that data. By using Simmplify, you agree to the collection and use of information in accordance with this policy.</p>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>1. Information We Collect</h3>
                        </div>

                        <p>When you use Simmplify, we collect the following data related to your Spotify activity:</p>
                        <ul>
                            <li><strong>Songs Listened To:</strong> We track each song you listen to on Spotify, including the song title, artist, and timestamp of when you start listening.</li>
                            <li><strong>Listening Duration:</strong> We monitor how much of each song you listen to, based on the timestamp of when you start the song and when it ends, or when the song is skipped.</li>
                            <li><strong>Skip Data:</strong> We identify songs that you skip by polling the Spotify player at regular intervals. If the song title changes on the next polling loop, we calculate the previous song’s skip timestamp and the duration of time you listened to the song before skipping.</li>
                        </ul>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>2. How We Use Your Data</h3>
                        </div>

                        <p>The data we collect is used for the following purposes:</p>
                        <ul>
                            <li><strong>Song Tracking:</strong> To track and store the songs you listen to and skip in order to give you insights about your listening habits, including the songs you skip most often.</li>
                            <li><strong>Personalized Insights:</strong> To generate insights based on your listening history, providing you with details about songs you skip frequently and offering recommendations accordingly.</li>
                            <li><strong>App Functionality:</strong> The app requires continuous data polling to function properly. Without this data collection, the app cannot deliver the core features, including song tracking and skip analysis.</li>
                        </ul>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>3. Data Retention and Deletion</h3>
                        </div>

                        <p>Your data is retained for as long as you use Simmplify. If you wish to stop using the app, you can delete all of your data by clicking the "Stop Tracking" button:</p>
                        <ul>
                            <li><strong>Stop Tracking:</strong> Clicking the "Stop Tracking" button will immediately delete all data associated with your usage of Simmplify, including the songs you’ve listened to, the time you’ve spent listening, and skip data.</li>
                            <li><strong>Data Usage Continuation:</strong> If you continue using the app, your data will be collected as described above.</li>
                        </ul>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>4. User Control and Rights</h3>
                        </div>

                        <p>You have control over your data with the following options:</p>
                        <ul>
                            <li>You can stop tracking by clicking the "Stop Tracking" button at any time. This will delete all of your stored data.</li>
                            <li>Please note that once you choose to stop tracking, you will no longer have access to the app's primary features, as the app requires continuous data polling to provide personalized insights.</li>
                        </ul>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>5. Data Security</h3>
                        </div>

                        <p>We prioritize the security of your data and implement standard security protocols to protect it from unauthorized access or disclosure. However, please note that no method of data transmission over the internet is fully secure, and we cannot guarantee absolute security.</p>

                        <div style="color:#1DB954;padding:10px;">
                            <h3>6. Third-Party Links</h3>
                        </div>

                        <p>Simmplify may contain links to third-party websites or services that are not operated by us. We have no control over and assume no responsibility for the content, privacy policies, or practices of any third-party sites or services.</p>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>7. Changes to This Privacy Policy</h3>
                        </div>

                        <p>We may update our Privacy Policy periodically. When we make changes, we will update the "Effective Date" at the top of this page. We encourage you to review this Privacy Policy periodically for any updates or changes.</p>

                        <div style="color:#1DB954; padding:10px;">
                            <h3>8. Contact Us</h3>
                        </div>

                        <p>If you have any questions or concerns regarding this Privacy Policy or our data practices, please contact Noah at simms.noah11@gmail.com</p>

                        <p>By using Simmplify, you acknowledge that you have read and understood this Privacy Policy and agree to its terms.</p>
                        """, unsafe_allow_html=True)
        

        userCurrentSongPlayingDict = {}

        while True:
            if time.time() - st.session_state.last_active > timeout:
                st.write("No user interaction detected. Exiting...")
                break
        
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

            elif "SongCurrentPosition" not in userCurrentSongPlayingDict:
                    userCurrentSongPlayingDict = {
                        "name": "No song playing",
                        "artists": [],
                        "album.name": "",
                        "duration_ms": 0,
                        "SongCurrentPosition": 0,
                        "CurrentPlaylistUri": ""
                    }
            else:
                userCurrentSongPlayingDict["SongCurrentPosition"] = min(float(userCurrentSongPlayingDict["duration_ms"]), float(userCurrentSongPlayingDict["SongCurrentPosition"]) + 1000)


            with player.container():
                c1, c2, c3, c4 = st.columns(4)

                c4.markdown("All data provided by:")
                c4.image("frontend/images/Spotify_Full_Logo_RGB_Green.png", width=150)

                if st.session_state["is_playing"] == True:
                    if st.session_state["previous_song_name"] != userCurrentSongPlayingDict["name"]:
                        st.session_state.last_active = time.time()
                        st.session_state["previous_song_name"] = userCurrentSongPlayingDict["name"]
                        historicalData = getHistoricalData(userUri, userPlaylists)
                        summarizedData = getSummarizedData(historicalData)
                        summarizedListeningData, lengthPostFilter, filteredSummarizedData = filterAndStyleSummarizedData(summarizedData.copy(), selectedPlaylistUri, userPlaylists, playMin, scoreMin, scoreMax)
                        historicalDataStyled = format_historical_data(historicalData, selectedPlaylistName)
                        topArtists, topSongs, bottomArtists, bottomSongs, bottomPlaylists, topPlaylists = summarizedAdvancedStats(summarizedData)

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


            with historical.container():
                st.dataframe(historicalDataStyled, column_order=['Playlist Name', 'Song Name', 'Artist Name', 'Album Name', 'Seconds Listened', 'Seconds Skipped', 'Listening Start Time'], hide_index=True, use_container_width=True)
            

            time.sleep(1)
finally:
    # Ensure all resources are cleaned up
    grace.close_resources()



