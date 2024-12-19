# Import necessary libraries
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import csv
import time
import pyodbc
import datetime
import requests
import pandas as pd
from pandas import json_normalize


import frontend.credentials as credentials

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
def getQuery(query):
    cursor.execute(query)
    Data = pd.DataFrame.from_records(cursor.fetchall(), columns=[col[0] for col in cursor.description])
    return Data

# Function to extract 'name' from each JSON object in the array
def extract_item(json_array, key='name'):
    return [item[key] for item in json_array if key in item]

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

def updateHistoricalDataDisplay():
    print("Getting Historical Data") 
    historicalData = getAsMuchHistoricalData()
    historicalDataWCalc = calculateSkipFraction(historicalData)
    insertHistoricalData(st.session_state['UserId'], historicalDataWCalc)
    historicalDataRaw = getUsersSongs(st.session_state['UserId'])
    historicalDataEdits = historicalDataRaw.drop(["userId","timestamp"], axis=1)
    historicalDataEdits = historicalDataEdits.groupby('songUri').agg({
        'playlistUri': 'first',    # Sum the values
        'ListeningFraction': 'sum',  # Keep the same value
        'SkippedFraction': 'sum'   # Keep the same value
        }).reset_index()

    historicalDataDisplay = historicalDataEdits[historicalDataEdits["playlistUri"] == st.session_state['SelectedPlaylist']]
    historicalDataDisplay["songNames"] = getSongName(historicalDataDisplay["songUri"])
    st.session_state["historicalDataDisplay"] = historicalDataDisplay

def getSongName(idList):
    params = {}
    songNames = []
    for id in list(idList):
        songNames.append(submitRequest(f"https://api.spotify.com/v1/tracks/{id}", "Get song name", params)["name"])
    print(songNames)
    return songNames
