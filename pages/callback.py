import streamlit as st
import spotipy as sp
from spotipy.oauth2 import SpotifyOAuth
import os
import certifi

import credentials

# Use certifi's certificate bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

# Streamlit app - callback page
def callback_page():
    st.title("OAuth Callback")
    
    # Step 2: Detect the authorization code from the URL query parameters
    query_params = st.query_params  # Updated from experimental_get_query_params()
    code = query_params.get("code")

    if code:
        try:
            token_info = sp_oauth.get_access_token(code)

            st.write(token_info)

            # Adjust code to handle the future return type (token string) vs. current (dictionary)
            if isinstance(token_info, str):
                # Future behavior (token string)
                access_token = token_info
            else:
                # Current behavior (token dictionary)
                access_token = token_info['access_token']

            # Store access token in session_state
            st.session_state['access_token'] = access_token

            st.toast("You are now authenticated!")
            results = sp.current_user_saved_tracks()
            for idx, item in enumerate(results['items']):
                track = item['track']
                st.write(idx, track['artists'][0]['name'], " – ", track['name'])

        except Exception as e:
            st.error(f"Error fetching the token: {e}")
    else:
        st.error("Authorization code not found in URL. Please try again.")

if __name__ == "__main__":
    callback_page()