import json
import requests
import base64

import numpy as np
import pandas as pd

import time
import streamlit as st

import sys

# import plotly.express as px

# pd.set_option("display.max_columns", None)
# pd.set_option("display.max_rows", 600)

# Variable setup

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
primary_artist_name_str = f"primary_{artist_name_str}"

album_str = "album"
url_str = "url"
rank_str = "rank"
track_rank_str = f"{track_str}_{rank_str}"

images_str = "images"

height_str = "height"

spotify_accounts_endpoint = "https://accounts.spotify.com/"
spotify_api_endpoint = "https://api.spotify.com/v1/"


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


# Convenience function to call the Spotify API
# Args:
# access_token: the token retrieved through OAuth 2.0
# endpoint: the Spotify endpoint to hit
# content_type: a string of the value to pass to the API Content-Type header
# query: a dictionary of key value pairs to send via the API. Defaulted to an empty dictionary if not needed.
# max_parse_level: passed to pd.normalize and controls how JSON is flattened. The default, 0, ensures max flattening.
# base_obj: a string to pass if the returned JSON is wrapped in a tag. Used to filter out the tag for parsing efficiency.
# balloons: a Boolean to control if Streamlit balloons should show after API call completion.
# paginated: a Boolean to indicate if pagination is part of the API call.
def spotify_get_all_results(
    access_token,
    endpoint,
    content_type,
    query={},
    max_parse_level=0,
    base_obj=None,
    balloons=False,
    paginated=True,
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

        # If paginated and the first call, determine how many pages of data the API will have to retrieve.
        # Use this calculation to create a progress bar to display.
        if paginated and first_call:
            num_pages = int(
                np.ceil(api_request_json["total"] / api_request_json["limit"])
            )

            first_call = False

            progress_bar = st.progress(curr_page_num, text="Loading...")

        # Get the next endpoint to call, and convert the current JSON response to a DataFrame.
        # End the loop if paginated by setting "next" to None.
        next_api_url = api_request_json["next"] if paginated else None

        retVal_list.append(
            pd.json_normalize(
                api_request_json["items"] if paginated else api_request_json,
                max_level=max_parse_level,
            )
        )

        # Update the progress bar for paginated queries
        if paginated:
            curr_page_num += 1

            # Update the progress bar
            progress_bar.progress(
                curr_page_num / num_pages,
                text=f"Loaded Page: {curr_page_num} of {num_pages}",
            )

    # Clear the progress bar for paginated queries
    if paginated:
        # When processing is complete, stop showing the progress bar
        progress_bar.empty()

    # Potentially show balloons
    if balloons:
        st.balloons()

    # Return the unioned result
    return pd.concat(retVal_list).reset_index(drop=True)


# Helper function to unroll image data held in JSON.
# Looks for an "images" column and creates a DataFrame linking that unrolled JSON with the "id" column value for that row.
# Returns arg `df` with a `url` column added with an image link from the above described processing.
# Args:
# df: the DataFrame with the "images" column to unroll.
def spotify_unroll_image_helper(df):
    my_image_size = 320
    df_imgs = convert_json_col_to_dataframe_with_key(
        df.dropna(subset=images_str),
        id_str,
        images_str,
    )[[id_str, url_str, height_str]]

    df_imgs = df_imgs[df_imgs[height_str] == my_image_size]

    # Drop the "height" column
    df_imgs.drop(height_str, axis=1, inplace=True)

    df_imgs = pd.merge(
        df,
        df_imgs,
        how="left",
        on=id_str,
    )

    # Fill NA URLs with a stock image
    df_imgs[url_str].fillna(
        "https://www.freeiconspng.com/uploads/no-image-icon-15.png", inplace=True
    )

    # Drop the unrolled "images" column.
    df_imgs.drop(images_str, axis=1, inplace=True)

    return df_imgs


# Generates HTML style code for images used in the app.
# Args:
# img_size_px: size in pixels for the image
# style_tag_suffix: a unique suffix to add to CSS classes so multiple styles with slight differences can be configured with the same function.
def generate_html_style_code(img_size_px, style_tag_suffix):
    return f"""
<style>
    body {{
        margin: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100vh;
    }}

    .container-{style_tag_suffix} {{
        display: flex;
        align-items: center;
    }}

    .number-container-{style_tag_suffix} {{
        margin-right: 20px;
        text-align: center;
        font-size: 24px;
    }}

    .image-container-{style_tag_suffix} {{
        margin-right: 20px;
        margin-top: 20px;
        margin-bottom: 20px;
    }}

    .image-container-{style_tag_suffix} img {{
        width: {img_size_px}px;
        height: auto;
        display: block;
    }}

    .text-container-{style_tag_suffix} {{
        display: flex;
        flex-direction: column;
        text-align: left;
    }}

    .text-container-{style_tag_suffix} p {{
        margin: 0;
    }}

    .text-subheader-{style_tag_suffix} {{
        color: grey;
    }}
</style>"""


# Function to generate the div block that goes along with images in the app
# Args:
# style_tag_suffix: a unique suffix to add to CSS classes so multiple styles with slight differences can be configured with the same function.
# img_src_holder_str: the image URL
# strong_txt_holder_str: text for line 1 to the right of the image
# p_txt_holder_str: text for line 2 to the right of the image
# b_txt_holder_str: text to the left of the image
def generate_div_block(
    style_tag_suffix,
    img_src_holder_str,
    strong_txt_holder_str,
    p_txt_holder_str,
    b_txt_holder_str=None,
):
    div_start = f"""
<div class='container-{style_tag_suffix}'>"""

    div_num_container = ""
    if b_txt_holder_str:
        div_num_container = f"""
    <div class="number-container-{style_tag_suffix}">
        <b>{b_txt_holder_str}</b>
    </div>"""

    div_main_containers = f"""
    <div class="image-container-{style_tag_suffix}">
        <img src="{img_src_holder_str}" alt="Image">
    </div>
    <div class="text-container-{style_tag_suffix}">
        <strong>{strong_txt_holder_str}</strong>
        <p class="text-subheader-{style_tag_suffix}">{p_txt_holder_str}</p>
    </div>
</div>"""

    return div_start + div_num_container + div_main_containers


# Utility function to generate the style and div blocks together.
# Args:
# img_size_px: size in pixels for the image
# style_tag_suffix: a unique suffix to add to CSS classes so multiple styles with slight differences can be configured with the same function.
# img_src_holder_str: the image URL
# strong_txt_holder_str: text for line 1 to the right of the image
# p_txt_holder_str: text for line 2 to the right of the image
# b_txt_holder_str: text to the left of the image
def generate_style_and_div_blocks(
    img_size_px,
    style_tag_suffix,
    img_src_holder_str,
    strong_txt_holder_str,
    p_txt_holder_str,
    b_txt_holder_str=None,
):
    return (
        generate_html_style_code(img_size_px, style_tag_suffix)
        + "\n"
        + generate_div_block(
            style_tag_suffix,
            img_src_holder_str,
            strong_txt_holder_str,
            p_txt_holder_str,
            b_txt_holder_str,
        )
    )


# Where the real magic starts. Retrieves an access token and runs the rest of the app.
# Args:
# initial_oauth_token: the OAuth 2.0 token
# client_id: Spotify client ID
# client_secret: Spotify client secret
# redirect_uri: OAuth 2.0 redirect uri
def run_app(initial_oauth_token, client_id, client_secret, redirect_uri):
    # Set up for the API call to retrieve an access token
    base64_encoding = "ascii"

    # Headers with Base64 auth encoding
    get_bearer_token_headers = {
        "Authorization": "Basic "
        + base64.b64encode(
            f"{client_id}:{client_secret}".encode(base64_encoding)
        ).decode(base64_encoding),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Payload
    get_bearer_token_payload = {
        "grant_type": "authorization_code",
        "code": initial_oauth_token,
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
    run_app_contents(get_bearer_token_response_json["access_token"])


# Pulls all the Spotify data and populates the Streamlit app
# Args:
# access_token: the access token needed to call the Spotify API
def run_app_contents(access_token):
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

    # Unroll artist data
    track_artists_df = convert_json_col_to_dataframe_with_key(
        my_tracks, track_id_str, artists_str
    )

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

    # Create the logout button
    st.link_button("Logout", "https://spotify.com/logout", type="primary")

    # Some plotly code that did not make the cut because it made the UX of mobile scrolling worse:
    # my_px_color_theme = px.colors.sequential.Sunset

    # px_top_artists_by_track_count = px.bar(
    #     num_tracks_per_artist.head(num_top_artists).sort_values(
    #         count_track_id_str, ascending=True
    #     ),
    #     x=count_track_id_str,
    #     y=name_str,
    #     text_auto=True,
    #     orientation="h",
    #     color_continuous_scale=my_px_color_theme,
    #     color=count_track_id_str,
    #     labels={name_str: artist_str, count_track_id_str: num_liked_tracks_str},
    # )
    # px_top_artists_by_track_count.update_traces(
    #     textangle=0, textposition="outside", cliponaxis=False
    # )
    # px_top_artists_by_track_count.update_coloraxes(showscale=False)
    # px_top_artists_by_track_count.update_layout(margin=dict(l=10, r=10, t=30, b=80))

    # px_displaybarconfig = {"displayModeBar": False}

    # The top DataFrame to display
    st.subheader("All Artists and Liked Track Counts")
    st.dataframe(
        num_tracks_per_artist[
            [name_str, count_track_id_str, max_added_at_ymd_str]
        ].rename(
            columns={
                name_str: artist_str,
                max_added_at_ymd_str: last_liked_date_str,
            }
        ),
        column_config={
            count_track_id_str: st.column_config.ProgressColumn(
                num_liked_tracks_str,
                width=None,
                min_value=0,
                format="%d",
                max_value=num_tracks_per_artist[count_track_id_str].max().item(),
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

    # Short, medium, and long term tracks section

    # Convert the tuple to a list
    bcols = list(st.columns(3))

    term_str = "term"
    underscore_term_str = f"_{term_str}"
    term_timeframes_friendly = ["short", "medium", "long"]
    term_timeframes = [f"{x}{underscore_term_str}" for x in term_timeframes_friendly]

    # For each of short/medium/long term track API calls, populate a Streamlit column with the data visualizations.
    for bcol_index in range(len(bcols)):
        bcol = bcols[bcol_index]
        with bcol:
            # Subheader
            st.subheader(
                f"My {term_timeframes_friendly[bcol_index]}-{term_str} Top Tracks".title()
            )

            # API Call
            my_top_tracks = spotify_get_all_results(
                access_token,
                f"{spotify_api_endpoint}me/top/tracks",
                "application/json",
                query={"time_range": term_timeframes[bcol_index]},
            ).rename(columns={id_str: track_id_str, name_str: track_name_str})

            # Wrap each value in a list to use the helper functions easily.
            my_top_tracks[album_str] = my_top_tracks[album_str].apply(lambda x: [x])

            # First, unwrap the "album" JSON.
            # Next, unwrap the album.images JSON
            my_top_tracks_album_images = convert_json_col_to_dataframe_with_key(
                convert_json_col_to_dataframe_with_key(
                    my_top_tracks, track_id_str, album_str
                ),
                track_id_str,
                images_str,
            )

            # My Top Tracks come back sorted, so add a rank to each one.
            my_top_tracks[track_rank_str] = range(1, len(my_top_tracks) + 1)

            # Bring in artist information
            # Tracks can have more than 1 artist, so flatten the artist_name column so each is seperated by a "; ".
            # We do so to have 1 row per track.
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
                .reset_index()[
                    [track_rank_str, track_id_str, artist_name_str, track_name_str]
                ]
            )

            # Link back to each 300 px height album image
            my_top_tracks_with_artist_and_album_img = pd.merge(
                my_top_tracks_with_artist,
                my_top_tracks_album_images[
                    my_top_tracks_album_images[height_str] == 300
                ][[track_id_str, url_str]].reset_index(),
                on=track_id_str,
            )

            # Add a column for the first artist, if multiple
            my_top_tracks_with_artist_and_album_img[
                primary_artist_name_str
            ] = my_top_tracks_with_artist_and_album_img[artist_name_str].str.replace(
                ";.+", "", regex=True
            )

            # For each row, generate the frontend html/css code and write it
            for i, df_row in my_top_tracks_with_artist_and_album_img.iterrows():
                st.markdown(
                    generate_style_and_div_blocks(
                        100,
                        "toptracks",
                        df_row[url_str],
                        df_row[track_name_str],
                        df_row[primary_artist_name_str],
                        f"{df_row[track_rank_str]:02d}",
                    ),
                    unsafe_allow_html=True,
                )

    # Get unique artists whose tracks are liked
    artist_ids_to_query = num_tracks_per_artist[id_str].drop_duplicates()
    max_artists_per_section = 50

    # Convert the pandas Series to a list. The endpoint can only handle 50 artists at a time.
    # Calculate the number of pages and split. Formula: ceiling(number of rows divided by the page limit).
    # Collapse each list of strings by a comma.
    artist_ids_to_query_list = [
        ",".join(x)
        for x in np.array_split(
            list(artist_ids_to_query),
            np.ceil(len(artist_ids_to_query) / max_artists_per_section),
        )
    ]

    # Call the API for all artists in the list
    my_artists_list = []
    for artist_id_query_string in artist_ids_to_query_list:
        my_artists_list.append(
            spotify_get_all_results(
                access_token,
                f"{spotify_api_endpoint}artists",
                "application/json",
                query={"ids": artist_id_query_string},
                base_obj="artists",
                paginated=False,
            )
        )

    # Union the results and bring in liked tracks metadata, also retaining image data
    my_liked_artists = pd.merge(
        pd.concat(my_artists_list).reset_index(drop=True)[[id_str, images_str]],
        num_tracks_per_artist,
        on=id_str,
        how="inner",
    )

    # Get image URL for each artist appended to the DataFrame
    my_liked_artists_imgs = spotify_unroll_image_helper(my_liked_artists)

    # Call the API for followed artist data
    my_followed_artists = spotify_get_all_results(
        access_token,
        f"{spotify_api_endpoint}me/following",
        "application/json",
        query={"type": "artist"},
        base_obj="artists",
    )

    # Get image URL for each artist appended to the DataFrame
    my_followed_artists_imgs = spotify_unroll_image_helper(my_followed_artists)

    # Perform an outer join between liked and followed artists
    my_left = my_liked_artists_imgs
    my_right = my_followed_artists_imgs

    my_left_cols = [x for x in my_left.columns]

    merge_str = "_merge"
    underscore_y_str = "_y"
    url_y_str = url_str + underscore_y_str
    name_y_str = name_str + underscore_y_str

    my_followed_and_liked_artists_df = pd.merge(
        my_left,
        my_right,
        on=id_str,
        how="outer",
        suffixes=("", underscore_y_str),
        indicator=True,
    )[my_left_cols + [name_y_str, url_y_str, merge_str]]

    # Look for rows where an artist is followed with no liked songs.
    # "name" would be NA but "name_y" would not be.
    unfollow_artist_rec_rows_to_retrieve = my_followed_and_liked_artists_df[
        name_str
    ].isna()

    # Get the name and URL for those rows
    unfollow_artist_rec_replace_vals = my_followed_and_liked_artists_df.loc[
        unfollow_artist_rec_rows_to_retrieve, [name_y_str, url_y_str]
    ]

    # Replace "name" and "url" columns with the retrieved values
    my_followed_and_liked_artists_df.loc[
        unfollow_artist_rec_rows_to_retrieve, [name_str, url_str]
    ] = unfollow_artist_rec_replace_vals.values

    # Remove extraneous columns
    my_followed_and_liked_artists_df = my_followed_and_liked_artists_df[
        my_left_cols + [merge_str]
    ]

    # Start to populate follow/unfollow recommendations
    followrecscol, unfollowrecscol = st.columns(2)
    no_recs_str = "No recommendations. You're on top of things!"
    recs_img_size = 200

    # Get artists with a liked song count >= 8 that are not followed, and present them via the visualization function.
    # If no recommendations, show a success message.
    with followrecscol:
        st.subheader("Recommended Artists to Follow")
        to_iter = my_followed_and_liked_artists_df[
            (my_followed_and_liked_artists_df[merge_str] == "left_only")
            & (my_followed_and_liked_artists_df[count_track_id_str] >= 8)
        ]
        if len(to_iter) > 0:
            to_iter = to_iter.astype({count_track_id_str: int})
            for i, df_row in to_iter.iterrows():
                st.markdown(
                    generate_style_and_div_blocks(
                        recs_img_size,
                        "followrec",
                        df_row[url_str],
                        df_row[name_str],
                        f"{df_row[count_track_id_str]} Liked Songs",
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.success(no_recs_str)

    # Get artists with no liked songs that are followed, and present them via the visualization function.
    # If no recommendations, show a success message.
    with unfollowrecscol:
        st.subheader("Recommended Artists to Unfollow")
        to_iter = my_followed_and_liked_artists_df[
            my_followed_and_liked_artists_df[merge_str] == "right_only"
        ]
        if len(to_iter) > 0:
            for i, df_row in to_iter.iterrows():
                st.markdown(
                    generate_style_and_div_blocks(
                        recs_img_size,
                        "unfollowrec",
                        df_row[url_str],
                        df_row[name_str],
                        "No Liked Songs",
                    ),
                    unsafe_allow_html=True,
                )
        else:
            st.success(no_recs_str)


# Generates a simple horizontalled centered div
# Args:
# html_element: the html component for inside the div
# text: text to write
# html_element_attr: attributes html syntax for the html_element
def generate_centered_div(html_element, text, html_element_attr=None):
    html_element_start = html_element + (
        f" {html_element_attr}" if html_element_attr else ""
    )

    return f"""
<div style="text-align: center;">
    <{html_element_start}>{text}</{html_element}>
</div>"""


# Streamlit wrapper to write a centered div
# Args:
# html_element: the html component for inside the div
# text: text to write
# html_element_attr: attributes html syntax for the html_element
def st_write_centered_text(html_element, text, html_element_attr=None):
    st.markdown(
        generate_centered_div(html_element, text, html_element_attr),
        unsafe_allow_html=True,
    )


# Get the query parameters of the URL in the browser
query_params = st.experimental_get_query_params()

# Variable setup
code_str = "code"
scopes = "user-read-private user-read-email playlist-read-private user-follow-read user-top-read user-read-recently-played user-library-read"
client_id_str = "client_id"
client_secret_str = "client_secret"
redirect_uri_str = "redirect_uri"

# Read from local secrets (when locally run) file or app secrets (when running deployed version).
client_id = st.secrets[client_id_str]
client_secret = st.secrets[client_secret_str]
redirect_uri = st.secrets[redirect_uri_str]

# If there is no OAuth 2.0 code in the query parameters, generate the Welcome screen.
if code_str not in query_params:
    oath_token_url = f"{spotify_accounts_endpoint}authorize?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&scope={scopes}"

    st_write_centered_text("h2", "Welcome to Your Spotify Dashboard 👋")

    st_write_centered_text(
        "p",
        """
This Streamlit app works directly and exclusively with the Spotify API to surface some insights on your music preferences.

Now, let's get you signed in. Clicking the link at the bottom of this page will initiate the sign-in process. So, if you are logged into Spotify already in your browser, you won't need to enter your password again! Just click the link. If not, have no fear. You will be redirected to Spotify's login page and then brought back here.

**One last note:** once you are in your dashboard, be sure to click the "logout" button when you are done. Refresh this page and your data will disappear from your session. You will remain logged in to the Spotify web app in your browser unless you explicitly log out.""",
    )

    st_write_centered_text("h5", "Are you ready to see your data?")

    rounded_button_class_raw = "rounded-button"
    rounded_button_class = f".{rounded_button_class_raw}"

    # Set some CSS and HTML to center the elements (not supported in Streamlit natively)
    st.markdown(
        f"""
<style>
    /* Styling for the button */
    {rounded_button_class} {{
        display: inline-block;
        padding: 10px 20px;
        border-radius: 10px;
        background-color: #4CAF50; /* Green background color */
        color: white !important; /* White text color */
        text-align: center;
        text-decoration: none;
        font-size: 16px;
        cursor: pointer;
        transition: background-color 0.3s;
    }}

    /* Hover effect */
    {rounded_button_class}:hover {{
        background-color: #45a049; /* Darker green on hover */
        color: white !important;
    }}

    /* Override default link styles */
    {rounded_button_class}:link, {rounded_button_class}:visited, {rounded_button_class}:hover, {rounded_button_class}:active {{
        color: white !important;
        text-decoration: none;
    }}
</style>
{generate_centered_div("a", "Let's go!", f'href="{oath_token_url}" class="{rounded_button_class_raw}"')}
""",
        unsafe_allow_html=True,
    )
# If there is an OAuth 2.0 code in the query parameters, run the analysis.
else:
    # Grab your token
    oauth_initial_token = query_params[code_str][0]

    # Removes the query parameters from the browser URL and does not rerun the page
    st.experimental_set_query_params()

    # Set the default layout for the frontend
    st.set_page_config(layout="wide")

    # Run the analysis!
    run_app(oauth_initial_token, client_id, client_secret, redirect_uri)
