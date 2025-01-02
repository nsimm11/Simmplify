import requests
import pandas as pd
from datetime import datetime, timedelta
from spotipy.oauth2 import SpotifyOAuth
import time

import credentials as credentials

def getSpotifyHistory(access_token, after_timestamp):
    print(after_timestamp)

    # Print statement to show the datetime, convert timestamp to datetime
    print(f"Processing Spotify History after {datetime.fromtimestamp(after_timestamp/1000)}")

    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "limit": 20,
        "after": after_timestamp  # Use milliseconds
    }

    response = requests.get(f"https://api.spotify.com/v1/me/player/recently-played", headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")  # Print error message for debugging
        return None


def processSpotifyHistory(response):
    #Turn listening data into a dataframe, with columns: track_id, track_name, artist_name, album_name, listening_start_time, listening_end_time, percentage_listened, percentage_skipped
    listening_data = []
    for item in response["items"]:
        listening_data.append({
            "track_id": item["track"]["id"],
            "track_name": item["track"]["name"],
            "artist_name": item["track"]["artists"][0]["name"],
            "listening_start_time": item["played_at"],
            "percentage_listened": 100,
        })
    listening_data_df = pd.DataFrame(listening_data)

    #Take Cursor from response and return it to use in the main loop to get the next 50 items, check if cursors and after is in milliseconds
    if "cursors" in response and response["cursors"] is not None and "after" in response["cursors"]:
        print(response["cursors"])
        next_cursor = response["cursors"]["after"]
    else:
        next_cursor = None
    return listening_data_df, next_cursor

loop_limit = 10
after_timestamp = int(datetime.now().timestamp() - timedelta(days=30).total_seconds()) * 1000
listening_data_main = pd.DataFrame()
access_token = "BQDXJZ7JTlVOSsZf0kFpbu0y0IG17dDdC-1pB-L_jNt-XonEMKyGO8VY_V4AX0pFCjPI03M-5QfCDByr9NCqOH0ijeRSo1ZjIcWV5rAZ3hq6Ko7KoeQvNd3acia_LxKMXGQZzQEbtxDbr14icyJdlyY7F5eIKgxz-L9lj0luMBjlkNfmXA-g3ZK--vL92qYv"

while loop_limit > 0:
    response = getSpotifyHistory(access_token, after_timestamp)
    if response is None or "items" not in response or len(response["items"]) == 0:
        break  # Exit if there's an error or no items

    listening_data, _ = processSpotifyHistory(response)
    listening_data_main = pd.concat([listening_data_main, listening_data])
    
    # Update after_timestamp to the played_at of the last track in the current response
    after_timestamp = int(datetime.fromisoformat(response["items"][-1]["played_at"].replace("Z", "+00:00")).timestamp() * 1000)  # Convert to milliseconds

    loop_limit -= 1  # Decrement loop limit
    time.sleep(1)

print(len(listening_data_main))
listening_data_main = listening_data_main.reset_index(drop=True)
listening_data_main.drop_duplicates(subset=["listening_start_time"], keep="first", inplace=True)
print(listening_data_main)
