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

import credentials

st.set_page_config(layout="wide")

# Use certifi's certificate bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = ''
if 'access_token_endTime' not in st.session_state:
    st.session_state['access_token_endTime'] = ''
if 'refresh_token' not in st.session_state:
    st.session_state['refresh_token'] = ''

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

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
def submitRequest(endpoint, functionName, params):

    # Define the endpoint for currently playing track
    headers = {
    "Authorization": f"Bearer {st.session_state["access_token"]}"}   

    response = requests.get(endpoint, headers=headers, params=params)

    # Check if the response is successful
    if response.status_code == 200:
        current_response = response.json()
    else:
        st.write(f"error, {functionName}, {response.status_code}")
        current_response = None
    
    if current_response is not None:
        return current_response
    
    return None

# Get Information for the Live Player
def getUserCurrentSongPlaying():

    requestsAsJsonPlayer = submitRequest("https://api.spotify.com/v1/me/player", "Get Users PlaybackState", {})
    requestsAsJsonSong = requestsAsJsonPlayer["item"]

    requestsAsDict = {}

    if requestsAsJsonSong is not None:
        requestsAsDict["SongName"] = requestsAsJsonSong["name"]
        requestsAsDict["ArtistsName"] = requestsAsJsonSong["artists"][0]["name"]
        requestsAsDict["AlbumName"] = requestsAsJsonSong["album"]["name"]
        requestsAsDict["AlbumArtHMTL"] = requestsAsJsonSong['album']['images'][0]['url']
        requestsAsDict["SongLength"] = requestsAsJsonSong['duration_ms']
    
    if requestsAsJsonPlayer is not None:
        requestsAsDict["SongCurrentPosition"] = requestsAsJsonPlayer['progress_ms']

    return requestsAsDict


# Get Information for Listening History and Skip Function

# Function to extract 'name' from each JSON object in the array
def extract_item(json_array, key='name'):
    return [item[key] for item in json_array if key in item]

def getHistoricalListening(after, before):

    params = {"limit": 10, "after": after, "before": before}

    requestsAsJsonHistory = submitRequest("https://api.spotify.com/v1/me/player/recently-played", "Get Users History", params)

    if requestsAsJsonHistory is not None and requestsAsJsonHistory["items"] != []:
        userHistory = json_normalize(requestsAsJsonHistory["items"])
        userHistory = userHistory[["played_at", "track.duration_ms", "track.id", "track.is_local", "track.name", "track.artists"]]
        userHistory['artists'] = userHistory['track.artists'].apply(extract_item)
        userHistory.drop("track.artists", axis=1, inplace=True)
        userHistory["played_at"] = pd.to_datetime(userHistory["played_at"])
        beforeStamp = requestsAsJsonHistory["cursors"]["before"]
        return userHistory, beforeStamp

    else:
        st.write("Issue with History Request")
        return (None, None)
    

st.title("Simmplify")

st.divider()

player = st.empty()

st.divider()

login()
st.markdown("## Historical Listening")
historicalData, beforeStamp = getHistoricalListening(None, None)

for i in range(10):
    print(i)
    newHL, beforeStamp = getHistoricalListening(None, beforeStamp)
    if newHL is not None:
        historicalData = pd.concat([historicalData, newHL])
    else:
        break

historicalData = historicalData.drop_duplicates(subset="track.id")
historicalData.reset_index(inplace=True)

st.dataframe(historicalData)



# Streamlit app - callback page
def callback_page():

    startTime = datetime.datetime.now()

    while True:
        if (startTime - datetime.datetime.now()).total_seconds() % 10 < 1:
            login()
            getUserCurrentSongPlayingDict = getUserCurrentSongPlaying()

        else: getUserCurrentSongPlayingDict["SongCurrentPosition"] = min(float(getUserCurrentSongPlayingDict["SongLength"]), float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) + 1000)

        with player.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown("## Player")
            c2.markdown(f'SONG: {getUserCurrentSongPlayingDict["SongName"]}')
            c2.markdown(f'Artists: {getUserCurrentSongPlayingDict["ArtistsName"]}')
            c2.markdown(f'Album: {getUserCurrentSongPlayingDict["AlbumName"]}')
            c3.image(getUserCurrentSongPlayingDict["AlbumArtHMTL"], width=150)
            c2.progress(float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) / float(getUserCurrentSongPlayingDict["SongLength"]))

        time.sleep(1)


if __name__ == "__main__":
    callback_page()