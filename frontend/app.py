import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth

import credentials

# Spotify API credentials
CLIENT_ID = credentials.CLIENT_ID
CLIENT_SECRET = credentials.CLIENT_SECRET
REDIRECT_URI = credentials.REDIRECT_URI

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing user-read-recently-played playlist-read-private"

sp_oauth = SpotifyOAuth(client_id=CLIENT_ID, 
                        client_secret=CLIENT_SECRET,
                        redirect_uri=REDIRECT_URI,
                        scope=SCOPE,
                        cache_path=None)  # Disable caching

# Streamlit app
def main():
    st.title("Spotify Currently Playing Track")

    # Step 1: Get the authentication URL
    auth_url = sp_oauth.get_authorize_url()
    
    # Step 2: Display the link using markdown
    st.write("### Step 1: Click the link to authenticate with Spotify")
        # Embed HTML with target="_self"
    st.markdown(f"""
        <a href="{auth_url}" target="_self">
            <button>Authenticate with Spotify</button>
        </a>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

