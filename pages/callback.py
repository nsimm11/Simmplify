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

def submitRequest(endpoint, headers, functionName):

    response = requests.get(endpoint, headers=headers)
    # Check if the response is successful
    if response.status_code == 200:
        current_track = response.json()
    
    if current_track is not None:
        return current_track["item"]
    
    return None

def getUserCurrentSongPlaying(access_token):
    # Define the endpoint for currently playing track
    endpoint = "https://api.spotify.com/v1/me/player/currently-playing"
    headers = {
    "Authorization": f"Bearer {access_token}"}   

    requestsAsJson = submitRequest(endpoint, headers, "Get Users Current Playing Song")

    if requestsAsJson is not None:
        st.write(requestsAsJson)

    #return requestsAsDataframe

# Streamlit app - callback page
def callback_page():
    st.title("OAuth Callback")
    
    # Step 2: Detect the authorization code from the URL query parameters
    query_params = st.query_params  # Updated from experimental_get_query_params()
    code = query_params.get("code")

    if code:
        try:
            #Acess Code Handling
            if st.session_state['access_token'] == "":
                token_info = sp_oauth.get_access_token(code)
                st.write(token_info)
                if isinstance(token_info, str):
                    access_token = token_info
                else:
                    access_token = token_info['access_token']
                st.session_state['access_token'] = access_token
                st.session_state["access_token_endTime"] = datetime.datetime.fromtimestamp(token_info['expires_at']) - datetime.timedelta(minutes=3)
                st.toast(f"You are now authenticated!, expires at {st.session_state["access_token_endTime"]}")
            
            else:
                access_token = st.session_state['access_token']
                st.toast("Using Old Access Token")
        except Exception as e:
            st.error(f"Error fetching the token: {e}")
    else:
        st.error("Authorization code not found in URL. Please try again.")

    while True:
        if datetime.datetime.now() > st.session_state["access_token_endTime"]:
            st.warning("Code about to expire")
        getUserCurrentSongPlaying(access_token)
        time.sleep(10)


if __name__ == "__main__":
    callback_page()