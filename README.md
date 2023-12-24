# Spotify OAuth 2.0 Streamlit Application

This repository is the home of my live Streamlit app, found at [this link](https://spotify-dashboard.streamlit.app/) (currently in beta and invite-only). 

The Streamlit app allows a Spotify user to log in via OAuth 2.0 and see a breakdown of their liked tracks - including their most-liked artists and short, medium, and long-term top tracks.

This app showcases some of the capabilities of the Spotify API and how its data could be extracted, presented, and analyzed.

To fully use this repository for local development, you will need to install Python and all of the libraries at the top of `/spotify_streamlit_app.py` (i.e. `pandas`, `numpy`, `streamlit`, etc.). Most of the libraries needed are built-in to Python.

## Instructions to Get Started

After the required installations, rename `/.streamlit/secrets_template.toml` to `/.streamlit/secrets.toml`.

Next, register / follow the instructions within the [Spotify Developer portal](https://developer.spotify.com/documentation/web-api) to retrieve your client id and client secret. Input these 2 fields' respective values into `/.streamlit/secrets.toml`.

To run, use a terminal to navigate to the cloned repository and run command `streamlit run spotify_streamlit_app.py`.

## Repository File Structure

- **/.gitignore**

  A very simple file to help with file management.

- **/README.md**

  This file.

- **/spotify_streamlit_app.py**

  The actual Streamlit app where all of the fun happens.

- **/.streamlit/secrets_template.toml**

  A template meant to contain Spotify app and user credentials for the local Streamlit app runs.