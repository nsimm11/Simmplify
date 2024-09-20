import streamlit as st
import spotipy as sp
from spotipy.oauth2 import SpotifyOAuth
import os
import requests
import certifi
import datetime
import pandas as pd
import time

import credentials

# Use certifi's certificate bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = ''
if 'access_token_endTime' not in st.session_state:
    st.session_state['access_token_endTime'] = ''

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
            #Acess Code Handling
            if st.session_state['access_token'] == "":
                token_info = sp_oauth.get_access_token(code)
                if isinstance(token_info, str):
                    access_token = token_info
                else:
                    access_token = token_info['access_token']
                st.session_state['access_token'] = access_token
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"You are now authenticated!, expires at {st.session_state["access_token_endTime"]}")
            
            elif st.session_state['access_token'] != "" and datetime.datetime.now() > st.session_state["access_token_endTime"]:
                st.warning("expiring token about to expire")
                token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
                st.session_state['access_token'] = access_token
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"Token Updated!, expires at {st.session_state["access_token_endTime"]}")
            
            else:
                access_token = st.session_state['access_token']
                st.toast("Using Cached Access Token")
            
            return access_token
        
        except Exception as e:
            st.error(f"Error fetching the token: {e}")
    else:
        st.error("Authorization code not found in URL. Please try again.")


def submitRequest(endpoint, headers, functionName):

    response = requests.get(endpoint, headers=headers)
    # Check if the response is successful
    if response.status_code == 200:
        current_response = response.json()
    
    if current_response is not None:
        return current_response
    
    return None

def getUserCurrentSongPlaying(access_token):
    # Define the endpoint for currently playing track
    headers = {
    "Authorization": f"Bearer {access_token}"}   

    requestsAsJsonPlayer = submitRequest("https://api.spotify.com/v1/me/player", headers, "Get Users PlaybackState")
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

st.title("Simmplify")

player = st.empty()

# Streamlit app - callback page
def callback_page():

    startTime = datetime.datetime.now()

    while True:
        if (startTime - datetime.datetime.now()).total_seconds() % 10 < 1:
            access_token = login()
            getUserCurrentSongPlayingDict = getUserCurrentSongPlaying(access_token)

        else: getUserCurrentSongPlayingDict["SongCurrentPosition"] = min(float(getUserCurrentSongPlayingDict["SongLength"]), float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) + 1000)

        with player.container():
            st.markdown(f'SONG: {getUserCurrentSongPlayingDict["SongName"]}')
            st.markdown(f'Artists: {getUserCurrentSongPlayingDict["ArtistsName"]}')
            st.markdown(f'Album: {getUserCurrentSongPlayingDict["AlbumName"]}')
            st.progress(float(getUserCurrentSongPlayingDict["SongCurrentPosition"]) / float(getUserCurrentSongPlayingDict["SongLength"]))
            st.image(getUserCurrentSongPlayingDict["AlbumArtHMTL"])

        time.sleep(1)



if __name__ == "__main__":
    callback_page()