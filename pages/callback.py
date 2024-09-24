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

def errorLog(errorMessage):
    f = open("error.txt", "a")
    f.write(f"{datetime.datetime.now()} - {errorMessage} \n")
    f.close()

#General Query funciton, returns a dataframe. Use this instead of pd.read_sql
@st.cache_data
def getQuery(query):
    cursor.execute(query)
    Data = pd.DataFrame.from_records(cursor.fetchall(), columns=[col[0] for col in cursor.description])
    return Data

def getUserId(uri, userName):
    userIdQuery = f"SELECT * FROM userInfo WHERE userUri = '{uri}'"
    userId = getQuery(userIdQuery)
    if len(userId) > 0:
        userId = userId.iloc[0].to_dict()
        if (userName) != userId["userName"]: errorLog("Username in DB and username from Spotify do not match")
        st.toast(f"Thanks for returing {userId["userName"]}!")
        return userId["userId"]
    else:
        newUserQuery = "SELECT MAX(userId) FROM userInfo"
        newUserId = getQuery(newUserQuery).values[0][0]
        if newUserId == None:
            newUserId = 1
        else: newUserId = int(newUserId) + 1
        insertNewUserQuery = "INSERT INTO userInfo (userId, userName, userUri) VALUES (?, ?, ?)"
        cursor.execute(insertNewUserQuery, (newUserId, userName, uri))
        conn.commit()
        return newUserId

def checkUsersPlaylist():

    return True

def getUsersSongs(userId):
    usersSongsQuery = f"SELECT * FROM processData WHERE userId = {userId}"
    songHistory = getQuery(usersSongsQuery)
    return songHistory


def insertHistoricalData(userId, userHistoricalData):
    # Prepare data for insertion
    data_to_insert = []
    for i, r in userHistoricalData.iterrows():
        timestamp = int(datetime.datetime.timestamp(r["played_at"]))  # Assuming r["played_at"] is a datetime object
        songUri = r["track.id"]
        playlistUri = r["context.uri"]
        fractionListened = r["ListeningFraction"]
        fractionSkipped = r["SkippedFraction"]
        data_to_insert.append((timestamp, userId, playlistUri, songUri, fractionListened, fractionSkipped))

    # Construct the SQL MERGE query dynamically
    merge_sql = """
    MERGE INTO processData AS target
    USING (VALUES {}) AS source (timestamp, userId, playlistUri, songUri, ListeningFraction, SkippedFraction)
    ON target.timestamp = source.timestamp AND target.userId = source.userId
    WHEN NOT MATCHED THEN
        INSERT (timestamp, userId, playlistUri, songUri, ListeningFraction, SkippedFraction)
        VALUES (source.timestamp, source.userId, source.playlistUri, source.songUri, source.ListeningFraction, source.SkippedFraction);
    """.format(', '.join(['(?, ?, ?, ?, ?, ?)'] * len(data_to_insert)))

    # Flatten the data list for execution
    flattened_data = [item for sublist in data_to_insert for item in sublist]

    # Execute the merge query in one go
    cursor.execute(merge_sql, flattened_data)
    conn.commit()

def login():

    query_params = st.query_params  # Updated from experimental_get_query_params()
    code = query_params.get("code")

    if code:
        try:
            #No Token is session state, need to get access token
            if st.session_state['access_token'] == "":
                token_info = sp_oauth.get_cached_token() # Directly the token string
                if isinstance(token_info, str):
                    access_token = token_info
                else:
                    access_token = token_info['access_token']
                st.session_state['access_token'] = access_token
                st.session_state['refresh_token'] = token_info['refresh_token']
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"You are now authenticated!, expires at {st.session_state["access_token_endTime"]}")
            
            #Token Available but expiring w/in 3 minutes
            elif st.session_state['access_token'] != "" and datetime.datetime.now() > st.session_state["access_token_endTime"]:
                st.warning("expiring token about to expire")
                token_info = sp_oauth.refresh_access_token(st.session_state['refresh_token'])
                st.session_state['access_token'] = token_info['access_token']
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"Token Updated!, expires at {st.session_state["access_token_endTime"]}")
            
            else:
                st.toast("Using Cached Access Token")
        
        except Exception as e:
            st.error(f"Error fetching the token: {e}")
    else:
        st.error("Authorization code not found in URL. Please try again.")

#General Request call for Spotify
@st.cache_data
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
def getUserCurrentSongPlaying():

    requestsAsJsonPlayer = submitRequest("https://api.spotify.com/v1/me/player", "Get Users PlaybackState", {})
    requestsAsDict = {}

    if requestsAsJsonPlayer is not None:
        requestsAsJsonSong = requestsAsJsonPlayer["item"]
        playerCurrent = json_normalize(requestsAsJsonSong)
        playerCurrent["SongCurrentPosition"] = requestsAsJsonPlayer['progress_ms']
        playerCurrent["CurrentPlaylistUri"] = requestsAsJsonPlayer['context']["uri"].split(":")[2]

        if  requestsAsJsonSong is not None:
            playerCurrent = playerCurrent[["id", "name","album.name","duration_ms","is_local","artists","album.images","SongCurrentPosition","CurrentPlaylistUri"]]
            playerCurrent['artists'] = playerCurrent['artists'].apply(extract_item)
            playerCurrent['album.images'] = json_normalize(playerCurrent['album.images'][0])["url"]
            
        return playerCurrent

    else:
        requestsAsJsonSong = None

# Function to extract 'name' from each JSON object in the array
def extract_item(json_array, key='name'):
    return [item[key] for item in json_array if key in item]

def getHistoricalListening(after, before):

    params = {"limit": 50, "after": after, "before": before}

    requestsAsJsonHistory = submitRequest("https://api.spotify.com/v1/me/player/recently-played", "Get Users History", params)

    if requestsAsJsonHistory is not None and requestsAsJsonHistory["items"] != []:
        userHistory = json_normalize(requestsAsJsonHistory["items"])
        userHistory = userHistory[["played_at", "track.duration_ms", "track.id", "track.is_local", "track.name", "track.artists", "context.uri"]]
        userHistory['artists'] = userHistory['track.artists'].apply(extract_item)
        userHistory.drop("track.artists", axis=1, inplace=True)
        userHistory["played_at"] = pd.to_datetime(userHistory["played_at"])
        beforeStamp = requestsAsJsonHistory["cursors"]["before"]
        return userHistory, beforeStamp

    elif "items" not in requestsAsJsonHistory:
        print("No more data")
        return (None, None)

    else:
        print("Issue with History Request")
        errorLog("Issue with History Request")

        return (None, None)
    
def getAsMuchHistoricalData():

    historicalData, beforeStamp = getHistoricalListening(None, None)

    while (1):
        newHL, beforeStamp = getHistoricalListening(None, beforeStamp)
        if newHL is not None:
            historicalData = pd.concat([historicalData, newHL])
        else:
            break

    historicalData = historicalData.drop_duplicates(subset="track.id")
    historicalData["played_at"] = historicalData["played_at"] - datetime.timedelta(hours=4) #Spotify seems to give data 4 hours ahead
    historicalData.reset_index(inplace=True, drop=True)

    return historicalData

def calculateSkipFraction(listeningHistory):
    lH = list((listeningHistory["played_at"].diff().dt.total_seconds()*1000*-1).dropna())
    lH.append(None)
    listeningHistory["played_for"] = lH
    listeningHistory.dropna(axis=0, inplace=True)
    listeningHistory["ListeningFraction"] = (1 - (listeningHistory["track.duration_ms"] - listeningHistory["played_for"]) / listeningHistory["track.duration_ms"]).clip(upper=1)
    listeningHistory["SkippedFraction"] = 1 - listeningHistory["ListeningFraction"]
    listeningHistory["context.uri"] = listeningHistory["context.uri"].str.split(':').str[2]
    return listeningHistory

def getUsersPlaylists(username):
    params = {"limit": 35}
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

def getSongName(idList):
    params = {}
    songNames = []
    for id in list(idList):
        songNames.append(submitRequest(f"https://api.spotify.com/v1/tracks/{id}", "Get song name", params)["name"])
    print(songNames)
    return songNames

st.set_page_config(layout="wide")
st.title("Simmplify")

st.divider()

player = st.empty()

st.divider()

login()
userName, userUri = getUserInfo()
userId = getUserId(userUri, userName)

st.session_state["UserName"] = userName
st.session_state["UserUri"] = userUri
st.session_state["UserId"] = userId

st.markdown("## User Created Playlists")
userPlaylists = getUsersPlaylists(userName)
playlists = st.empty()

st.divider()

st.markdown("## Historical Data (Last 50 songs)")
selectedPlaylistName = st.selectbox("Choose Playlist", options=list(userPlaylists["name"].unique()))
st.session_state['SelectedPlaylist'] = userPlaylists[userPlaylists["name"] == selectedPlaylistName]["uri"].values[0]
historicalData = getAsMuchHistoricalData()
historicalDataWCalc = calculateSkipFraction(historicalData)
insertHistoricalData(userId, historicalDataWCalc)
historical = st.empty()

with playlists.container():
    userPlaylists

# Streamlit app - callback page
def callback_page():

    startTime = datetime.datetime.now()

    while True:
    
        if (startTime - datetime.datetime.now()).total_seconds() % 30 < 1:
            login()
            getUserCurrentSongPlayingDict = getUserCurrentSongPlaying().to_dict('records')[0]

        else: getUserCurrentSongPlayingDict["SongCurrentPosition"] = min(float(getUserCurrentSongPlayingDict["duration_ms"]), float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) + 1000)

        with player.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown("## Player")
            c2.markdown(f'SONG: {getUserCurrentSongPlayingDict["name"]}')
            c2.markdown(f'Artists: {','.join(getUserCurrentSongPlayingDict["artists"])}')
            c2.markdown(f'Album: {getUserCurrentSongPlayingDict["album.name"]}')
            playlistName = userPlaylists[userPlaylists["uri"] == getUserCurrentSongPlayingDict["CurrentPlaylistUri"]]["name"].values[0]
            c2.markdown(f'Playlist: {playlistName}')
            
            if getUserCurrentSongPlayingDict["album.images"] != "": c3.image(getUserCurrentSongPlayingDict["album.images"], width=150)
            c2.progress(float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) / float(getUserCurrentSongPlayingDict["duration_ms"]))
            c4.markdown(f"Welcome: {st.session_state["UserName"]}")
        
        with historical.container():
            if (startTime - datetime.datetime.now()).total_seconds() % 60*30 < 1:
                print("Getting Historical Data") 
                historicalData = getAsMuchHistoricalData()
                historicalDataWCalc = calculateSkipFraction(historicalData)
                insertHistoricalData(userId, historicalDataWCalc)
                historicalDataRaw = getUsersSongs(userId)
                historicalDataEdits = historicalDataRaw.drop(["userId","timestamp"], axis=1)
                historicalDataEdits = historicalDataEdits.groupby('songUri').agg({
                    'playlistUri': 'first',    # Sum the values
                    'ListeningFraction': 'sum',  # Keep the same value
                    'SkippedFraction': 'sum'   # Keep the same value
                    }).reset_index()
                
                historicalDataEdits["songNames"] = getSongName(historicalDataEdits["songUri"])

                historicalDataDisplay = historicalDataEdits[historicalDataEdits["playlistUri"] == st.session_state['SelectedPlaylist']]
                historicalDataDisplay

        time.sleep(1)


if __name__ == "__main__":
    callback_page()