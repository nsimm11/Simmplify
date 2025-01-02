import requests
import pandas as pd
from datetime import datetime, timedelta
from spotipy.oauth2 import SpotifyOAuth

import credentials as credentials

# Scopes required for accessing user's currently playing track
SCOPE = "user-read-playback-state user-read-currently-playing"

sp_oauth = SpotifyOAuth(client_id=credentials.CLIENT_ID, 
                        client_secret=credentials.CLIENT_SECRET,
                        redirect_uri=credentials.REDIRECT_URI,
                        scope=SCOPE)

def getSpotifyHistory(access_token, after_timestamp):

    #Print statement to show the datetime, convert timestamp to datetime
    print(f"Processing Spotify History after {datetime.fromtimestamp(after_timestamp)}")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "limit": 50,
        "after": after_timestamp
    }

    response = requests.get(f"https://api.spotify.com/v1/me/player/recently-played", headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        return None


def processSpotifyHistory(response):
    #Turn listening data into a dataframe, with columns: track_id, track_name, artist_name, album_name, listening_start_time, listening_end_time, percentage_listened, percentage_skipped
    listening_data = []
    for item in response["items"]:
        listening_data.append({
            "track_id": item["track"]["id"],
            "track_name": item["track"]["name"],
            "artist_name": item["track"]["artists"][0]["name"],
            "album_name": item["track"]["album"]["name"],
            "listening_start_time": item["played_at"],
            "listening_end_time": item["played_at"],
            "percentage_listened": 0,
            "percentage_skipped": 0
        })
    df = pd.DataFrame(listening_data)

    #Take Cursor from response and return it to use in the main loop to get the next 50 items
    next_cursor = response["cursors"]["after"]
    return listening_data, next_cursor

loop_limit = 3
after_timestamp = datetime.now().timestamp() - timedelta(days=1).total_seconds()
listening_data_main = pd.DataFrame()
access_token = "BQAmDSXC22TfoM074aslq_CzcfVf34Hl_p8KiLuaiDEog2gXzfZ9LTofZbejn3XXgkx-b2ZlSr9CuLUioWIUfaJbfGVm_ewAG2ysZyOR-LGnWawRY_yOJSjxs9jUUMri8qYlfr2DuBuz3-NtBYsDgcywjQVOIdRnyRveZ1BTKAKVtZTnFLylJ3LKHNn9VQ"

for i in range(loop_limit):
    response = getSpotifyHistory(access_token, after_timestamp)
    listening_data, next_cursor = processSpotifyHistory(response)
    listening_data_main = pd.concat([listening_data, listening_data_main])
    after_timestamp = next_cursor

print(listening_data_main)
