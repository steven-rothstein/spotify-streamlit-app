import json
import requests
import jmespath
import base64
import yaml

import ipywidgets as widgets
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import time
import streamlit as st

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 600)


# Helper function
# A field of JSON from a row of data is converted to its own dataframe
# In addtion, the unique id columns from its source are appended on as the first columns.
# Args:
# pd_series is a row of data from a pandas DataFrame.
# id_names is either a string of the id column's name, or a list of strings of the id columns' names.
# json_col_to_parse is the name of the JSON column to convert to a DataFrame.
def assign_id_and_parse(pd_series, id_names, json_col_to_parse):
    # Convert to a list if not one already
    id_names = id_names if isinstance(id_names, list) else [id_names]

    # Convert the nested lists of dictionaries to a DataFrame
    retVal = pd.DataFrame(pd_series[json_col_to_parse])

    # Insert the current ID as the first column, going backwards through the list.
    for curr_id_name in id_names[::-1]:
        retVal.insert(0, curr_id_name, pd_series[curr_id_name])

    return retVal


# This function takes a DataFrame and parses a column, for which each row is JSON.
# Each JSON value is converted to its own DataFrame.
# In addtion, for each new DataFrame, the unique id columns from its source are appended on as the first columns.
# Finally, the resultant DataFrames are unioned together and returned.
# Args:
# df is the DataFrame to parse
# id_col_names is either a string of the id column's name, or a list of strings of the id columns' names.
# json_col_name is the name of the JSON column to convert to a DataFrame.
def convert_json_col_to_dataframe_with_key(df, id_col_names, json_col_name):
    retVal_list = list()

    # Go through all rows, parse the JSON, assign the unique ID(s). Union the results.
    for i, df_row in df.iterrows():
        retVal_list.append(assign_id_and_parse(df_row, id_col_names, json_col_name))

    return pd.concat(retVal_list).reset_index(drop=True)


# Convenience function to write a pandas DataFrame into the data_out folder of the project setup.
# Args:
# pd_df is the pandas DataFrame
# filename is the name for the new file to write
def spotify_write_df_to_data_out_csv(pd_df, filename):
    pd_df.to_csv(f"data_out/{filename}.csv", index=False)


# Convenience function to call the Spotify API
# Args:
# access_token: the token retrieved through Oauth 2.0
# endpoint: the Spotify endpoint to hit
# content_type: a string of the value to pass to the API Content-Type header
# query: a dictionary of key value pairs to send via the API. Defaulted to an empty dictionary if not needed.
# max_parse_level: passed to pd.normalize and controls how JSON is flattened. The default, 0, ensures max flattening.
# base_obj: a string to pass if the returned JSON is wrapped in a tag. Used to filter out the tag for parsing efficiency.
def spotify_get_all_results(
    access_token,
    endpoint,
    content_type,
    query={},
    max_parse_level=0,
    base_obj=None,
    balloons=False,
):
    # Header setup
    api_call_headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": content_type,
    }

    # Variable setup for loop to get all results
    next_api_url = endpoint

    curr_page_num = 0
    first_call = True
    retVal_list = list()

    # Loop through the API-provided next endpoints until no more exist. Union the results.
    while next_api_url is not None:
        # HTTP GET
        # raise_for_status() will stop execution on this fatal error.
        api_request = requests.get(
            next_api_url, headers=api_call_headers, params=query if first_call else {}
        )
        api_request.raise_for_status()

        # Get the repsonse in JSON
        api_request_json = api_request.json()

        # Filter out the base_obj if it exists
        if base_obj is not None:
            # Too simple for JMESPath...
            # TODO convert to JMESPath if more complex use cases arise
            api_request_json = api_request_json[base_obj]

        # If the first call, determine how many pages of data the API will have to retrieve.
        # Use this calculation to create a progress bar to display.
        if first_call:
            num_pages = int(
                np.ceil(api_request_json["total"] / api_request_json["limit"])
            )

            first_call = False

            progress_bar = st.progress(curr_page_num, text="Loading...")

        # Get the next endpoint to call, and convert the current JSON response to a DataFrame.
        next_api_url = api_request_json["next"]

        retVal_list.append(
            pd.json_normalize(api_request_json["items"], max_level=max_parse_level)
        )

        curr_page_num += 1

        # Update the progress bar
        progress_bar.progress(
            curr_page_num / num_pages,
            text=f"Loaded Page: {curr_page_num} of {num_pages}",
        )

    # When processing is complete, stop showing the progress bar
    progress_bar.empty()

    if balloons:
        st.balloons()

    # Return the unioned result
    return pd.concat(retVal_list).reset_index(drop=True)


# Set the default layout for the frontend
st.set_page_config(layout="wide")

spotify_accounts_endpoint = "https://accounts.spotify.com/"
spotify_api_endpoint = "https://api.spotify.com/v1/"

with st.spinner("Authorizing..."):
    # Install the web driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    # Get the app and user credentials from the YAML file
    # Note: this application is meant for local use only.
    # Never publish or give out your credentials, or leave them unencrypted in an untrusted location.
    with open("config/config.yml", "r") as file:
        config_contents = yaml.safe_load(file)

    config_contents_creds = config_contents["creds"]

    client_id = config_contents_creds["client_id"]
    client_secret = config_contents_creds["client_secret"]
    scopes = "user-read-private user-read-email playlist-read-private user-follow-read user-top-read user-read-recently-played user-library-read"

    redirect_uri = config_contents["redirect_uri"]

    oath_token_url = f"{spotify_accounts_endpoint}authorize?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&scope={scopes}"

    # Load the page and enter the username and password
    driver.get(oath_token_url)

    username_input = driver.find_element("id", "login-username")
    username_input.send_keys(config_contents_creds["username"])

    password_input = driver.find_element("id", "login-password")
    password_input.send_keys(config_contents_creds["password"])

    login_button = driver.find_element("id", "login-button")
    login_button.click()

    # If needed, click the proper "Accept" button to proceed to the next page
    if driver.current_url.startswith(f"{spotify_accounts_endpoint}en/authorize?"):
        agree_button = driver.find_element(
            "xpath", '//button[@data-testid="auth-accept"]'
        )
        agree_button.click()

    # Sleep to ensure the page loads
    time.sleep(2)

    # Finally, obtain the oauth initial token
    oauth_initial_token = driver.current_url.replace(f"{redirect_uri}/?code=", "")

    # Quit out of selenium-based items
    driver.close()
    driver.quit()

    # Set up for the API call to retrieve an access token
    base64_encoding = "ascii"
    content_type_dictionary = {"Content-Type": "application/x-www-form-urlencoded"}

    # Headers with Base64 auth encoding
    get_bearer_token_headers = {
        "Authorization": "Basic "
        + base64.b64encode(
            f"{client_id}:{client_secret}".encode(base64_encoding)
        ).decode(base64_encoding)
    } | content_type_dictionary

    # Payload
    get_bearer_token_payload = {
        "grant_type": "authorization_code",
        "code": oauth_initial_token,
        "redirect_uri": redirect_uri,
    }

    # HTTP POST
    get_bearer_token_response = requests.post(
        f"{spotify_accounts_endpoint}api/token",
        headers=get_bearer_token_headers,
        data=get_bearer_token_payload,
    )

    # Crash on error (no automated data pipelines to disrupt here...)
    get_bearer_token_response.raise_for_status()

    # Read the resulting JSON and retrieve your access token!
    get_bearer_token_response_json = get_bearer_token_response.json()
    access_token = get_bearer_token_response_json["access_token"]

track_str = "track"
track_id_str = f"{track_str}_id"

added_at_str = "added_at"
name_str = "name"
id_str = "id"
artists_str = "artists"

count_track_id_str = f"count_{track_id_str}"

added_at_ymd_str = added_at_str + "_ymd"
max_added_at_ymd_str = f"max_{added_at_ymd_str}"

num_top_artists = 15
artist_str = "Artist"
num_liked_tracks_str = "Number of Liked Tracks"
last_liked_date_str = "Last Liked Date"

track_name_str = f"{track_str}_{name_str}"
artist_name_str = f"{artist_str.lower()}_{name_str}"

# API call happens here
my_tracks = spotify_get_all_results(
    access_token,
    f"{spotify_api_endpoint}me/tracks",
    "application/x-www-form-urlencoded",
    max_parse_level=1,
    balloons=True,
)

# Header and column cleanup
my_tracks.columns = my_tracks.columns.str.replace(f"{track_str}.", "", regex=False)
my_tracks.rename(columns={id_str: track_id_str}, inplace=True)

my_tracks[added_at_str] = pd.to_datetime(my_tracks[added_at_str])

# Comment out the following line for personal uses
# my_tracks[name_str] = my_tracks[name_str].apply(hash)

track_artists_df = convert_json_col_to_dataframe_with_key(
    my_tracks, track_id_str, artists_str
)

# Comment out the following line for personal uses
# track_artists_df[name_str] = track_artists_df[name_str].apply(hash)

# Pull in the added_at field for each track
track_artists_df_with_added_at = pd.merge(
    track_artists_df, my_tracks[[track_id_str, added_at_str]], on=track_id_str
)

# Create field for added_at formatted as YYYY-MM-DD
track_artists_df_with_added_at[added_at_ymd_str] = track_artists_df_with_added_at[
    added_at_str
].dt.date

# Use the DataFrame linking tracks to artists to get the number of tracks liked per artist.
num_tracks_per_artist = (
    track_artists_df_with_added_at.groupby([id_str, name_str])
    .agg({track_id_str: "count", added_at_ymd_str: "max"})
    .sort_values(track_id_str, ascending=False)
    .reset_index()
    .rename(
        columns={
            track_id_str: count_track_id_str,
            added_at_ymd_str: max_added_at_ymd_str,
        }
    )
)

# hash_str = "hash"
# num_tracks_per_artist[hash_str] = num_tracks_per_artist[name_str].apply(hash)

my_px_color_theme = px.colors.sequential.Sunset

px_top_artists_by_track_count = px.bar(
    num_tracks_per_artist.head(num_top_artists).sort_values(
        count_track_id_str, ascending=True
    ),
    x=count_track_id_str,
    y=name_str,
    text_auto=True,
    orientation="h",
    color_continuous_scale=my_px_color_theme,
    color=count_track_id_str,
    labels={name_str: artist_str, count_track_id_str: num_liked_tracks_str},
    title=f"Top {num_top_artists} Artists by Liked Track Count",
)
px_top_artists_by_track_count.update_traces(
    textangle=0, textposition="outside", cliponaxis=False
)
px_top_artists_by_track_count.update_coloraxes(showscale=False)
px_top_artists_by_track_count.update_layout(margin=dict(l=10, r=10, t=30, b=80))

px_displaybarconfig = {"displayModeBar": False}

topcol1, topcol2 = st.columns(2)

with topcol1:
    st.plotly_chart(
        px_top_artists_by_track_count,
        use_container_width=True,
        config=px_displaybarconfig,
    )

with topcol2:
    st.markdown("**All Artists and Liked Track Counts**")
    st.dataframe(
        num_tracks_per_artist[
            [name_str, count_track_id_str, max_added_at_ymd_str]
        ].rename(
            columns={
                name_str: artist_str,
                count_track_id_str: num_liked_tracks_str,
                max_added_at_ymd_str: last_liked_date_str,
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

my_top_tracks = spotify_get_all_results(
    access_token,
    f"{spotify_api_endpoint}me/top/tracks",
    "application/json",
    query={"time_range": "long_term"},
).rename(columns={id_str: track_id_str, name_str: track_name_str})

album_str = "album"
url_str = "url"
my_top_tracks[album_str] = my_top_tracks[album_str].apply(lambda x: [x])
my_top_tracks_album_images = convert_json_col_to_dataframe_with_key(
    convert_json_col_to_dataframe_with_key(my_top_tracks, track_id_str, album_str),
    track_id_str,
    "images",
)
my_top_tracks_album_images_64 = my_top_tracks_album_images[
    my_top_tracks_album_images["height"] == 64
][[track_id_str, url_str]].reset_index()[[track_id_str, url_str]]

track_rank_str = f"{track_str}_rank"
my_top_tracks[track_rank_str] = range(1, len(my_top_tracks) + 1)

my_top_tracks_with_artist = (
    pd.merge(
        my_top_tracks[[track_id_str, track_rank_str, track_name_str]],
        convert_json_col_to_dataframe_with_key(
            my_top_tracks, track_id_str, artists_str
        ),
        on=track_id_str,
    )
    .rename(columns={name_str: artist_name_str})
    .groupby([track_id_str, track_rank_str, track_name_str])
    .agg({artist_name_str: "; ".join})
    .sort_values(track_rank_str, ascending=True)
    .reset_index()[[track_rank_str, track_id_str, artist_name_str, track_name_str]]
)

my_top_tracks_with_artist_and_album_img = pd.merge(
    my_top_tracks_with_artist, my_top_tracks_album_images_64, on=track_id_str
)

toptrackscol1, toptrackscol2, toptrackscol3 = st.columns(3)

with toptrackscol1:
    for i, df_row in my_top_tracks_with_artist_and_album_img.iterrows():
        with st.container():
            botcol1, botcol2 = st.columns([1, 1])
            botcol1.image(df_row[url_str])
            # botcol2.write(' ')
            botcol2.write(df_row[track_name_str])
            # botcol2.write(df_row[artist_name_str])
            # botcol2.write(' ')

# # Comment out the following line for personal uses
# my_top_tracks[name_str] = my_top_tracks[name_str].apply(hash)

# st.dataframe(my_top_tracks_with_artist, use_container_width=True, hide_index=True)

# my_followed_artists = spotify_get_all_results(
#     access_token,
#     f"{spotify_api_endpoint}me/following",
#     "application/json",
#     query={"type": "artist"},
#     base_obj="artists",
# )

# # Comment out the following line for personal uses
# # my_followed_artists[name_str] = my_followed_artists[name_str].apply(hash)

# display(my_followed_artists.head())

# my_left = num_tracks_per_artist[[id_str, name_str, count_track_id_str]]
# my_right = my_followed_artists

# my_followed_and_liked_artists_df = pd.merge(
#     my_left, my_right, on=id_str, how="inner", suffixes=("", "_y")
# )[my_left.columns]

# display(my_followed_and_liked_artists_df.head())
# print(my_followed_and_liked_artists_df.shape)

# # Create Sets
# my_track_artists_ids = set(my_left[id_str])
# my_followed_artists_ids = set(my_right[id_str])
# my_followed_and_liked_artists_ids = set(my_followed_and_liked_artists_df[id_str])

# # Use Set operations
# my_unfollowed_track_artists_ids = (
#     my_track_artists_ids - my_followed_and_liked_artists_ids
# )
# my_followed_and_nonliked_artists_ids = (
#     my_followed_artists_ids - my_followed_and_liked_artists_ids
# )

# # TODO handle when my_followed_and_nonliked_artists_ids is non-empty

# # Inspect data
# my_unfollowed_track_artists_df = my_left[
#     my_left[id_str].isin(my_unfollowed_track_artists_ids)
# ]

# my_top_unfollowed_artists_indices = (
#     my_unfollowed_track_artists_df[count_track_id_str] > 2
# )

# my_top_unfollowed_artists_df = my_unfollowed_track_artists_df[
#     my_top_unfollowed_artists_indices
# ].reset_index(drop=True)

# my_top_unfollowed_artists_df[hash_str] = my_top_unfollowed_artists_df[name_str].apply(
#     hash
# )

# display(my_top_unfollowed_artists_df[[hash_str, count_track_id_str]].head())
# print(my_top_unfollowed_artists_df.shape)
