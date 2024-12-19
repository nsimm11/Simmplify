import streamlit as st
import spotipy as sp
from spotipy.oauth2 import SpotifyOAuth
import os
import requests
import certifi
import datetime
import pandas as pd
from pandas import json_normalize
import time
import pyodbc

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
    

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

#connection string 
# conn = pyodbc.connect('Driver={ODBC Driver 17 for SQL Server};'
#                      f'Server={credentials.dbConnectionLocation};'
#                      f'Database={credentials.dbID};'
#                      'TrustServerCertificate=yes;'
#                      f'UID={credentials.dbUsername};PWD={credentials.dbPassword}')

# cursor = conn.cursor()

def errorLog(errorMessage):
    f = open("error.txt", "a")
    f.write(f"{datetime.datetime.now()} - {errorMessage} \n")
    f.close()

#General Query funciton, returns a dataframe. Use this instead of pd.read_sql
# def getQuery(query):
#     cursor.execute(query)
#     Data = pd.DataFrame.from_records(cursor.fetchall(), columns=[col[0] for col in cursor.description])
#     return Data
    
# def getUserId(uri, userName):
#     userIdQuery = f"SELECT * FROM userInfo WHERE userUri = '{uri}'"
#     userId = getQuery(userIdQuery)
#     if len(userId) > 0:
#         userId = userId.iloc[0].to_dict()
#         if (userName) != userId["userName"]: errorLog("Username in DB and username from Spotify do not match")
#         st.toast(f"Thanks for returing {userId["userName"]}!")
#         return userId["userId"]
#     else:
#         newUserQuery = "SELECT MAX(userId) FROM userInfo"
#         newUserId = getQuery(newUserQuery).values[0][0]
#         if newUserId == None:
#             newUserId = 1
#         else: newUserId = int(newUserId) + 1
#         insertNewUserQuery = "INSERT INTO userInfo (userId, userName, userUri) VALUES (?, ?, ?)"
#         cursor.execute(insertNewUserQuery, (newUserId, userName, uri))
#         conn.commit()
#         return newUserId

def checkUsersPlaylist():

    return True

# def getUsersSongs(userId):
#     usersSongsQuery = f"SELECT * FROM processData WHERE userId = {userId}"
#     songHistory = getQuery(usersSongsQuery)
#     return songHistory

def login():
    query_params = st.query_params
    code = query_params.get("code")

    if code:
        try:
            # No Token in session state, need to get access token
            if st.session_state['access_token'] == "":
                # Exchange the authorization code for an access token
                token_info = sp_oauth.get_access_token(code)
                access_token = token_info['access_token']
                st.session_state['access_token'] = access_token
                st.session_state['refresh_token'] = token_info['refresh_token']
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"You are now authenticated!, expires at {st.session_state['access_token_endTime']}")
            
            # Token Available but expiring w/in 3 minutes
            elif st.session_state['access_token'] != "" and datetime.datetime.now() > st.session_state["access_token_endTime"]:
                st.warning("expiring token about to expire")
                token_info = sp_oauth.refresh_access_token(st.session_state['refresh_token'])
                st.session_state['access_token'] = token_info['access_token']
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"Token Updated!, expires at {st.session_state['access_token_endTime']}")
            
            else:
                st.toast("Using Cached Access Token")
        
        except Exception as e:
            st.warning(f"Error fetching the token: {e}")
    else:
        st.warning("Authorization code not found in URL. Please try again.")

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

#Ge user infomrati9on
def getUserInfo():

    requestsAsJsonUser = submitRequest("https://api.spotify.com/v1/me", "Get Users PlaybackState", {})

    return (str(requestsAsJsonUser["display_name"]), (str(requestsAsJsonUser["uri"])))


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
        userPlaylists["uri"] = userPlaylists["uri"].str.split(":").str[2]

    return userPlaylists

st.set_page_config(layout="wide")
st.title("Simmplify")

st.divider()

player = st.empty()

st.divider()

login()

userName, userUri = getUserInfo()
# userId = getUserId(userUri, userName)

st.session_state["UserName"] = userName
st.session_state["UserUri"] = userUri
# st.session_state["UserId"] = userId

userPlaylists = spotifyUsersPlaylists(userName)
playlists = st.empty()

st.divider()

st.markdown("## Historical Data (Last 50 songs)")
selectedPlaylistName = st.selectbox("Choose Playlist",placeholder="", options=list(userPlaylists["name"].unique()))
st.session_state['SelectedPlaylist'] = userPlaylists[userPlaylists["name"] == selectedPlaylistName]["uri"].values[0]
historical = st.empty()

# Streamlit app - callback page
def callback_page():

    startTime = datetime.datetime.now()

    while True:
    
        if (startTime - datetime.datetime.now()).total_seconds() % 10 < 1:
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
            c1.markdown("## Player")
            if st.session_state["is_playing"] == True:
                c2.markdown(f'SONG: {userCurrentSongPlayingDict["name"]}')
                c2.markdown(f'Artists: {','.join(userCurrentSongPlayingDict["artists"])}')
                c2.markdown(f'Album: {userCurrentSongPlayingDict["album.name"]}')
                playlistName = userPlaylists[userPlaylists["uri"] == userCurrentSongPlayingDict["CurrentPlaylistUri"]]["name"].values[0]
                c2.markdown(f'Playlist: {playlistName}')
            
                if userCurrentSongPlayingDict["album.images"] != "": c3.image(userCurrentSongPlayingDict["album.images"], width=150)
                c2.progress(float(userCurrentSongPlayingDict["SongCurrentPosition"]) / userCurrentSongPlayingDict["duration_ms"])
                c4.markdown(f"Welcome: {st.session_state["UserName"]}")
            else: c2.markdown("## Player Paused")
        
        with historical.container():
            st.dataframe(st.session_state["historicalDataDisplay"])

        time.sleep(1)


if __name__ == "__main__":
    callback_page()