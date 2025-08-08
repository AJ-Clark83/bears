import streamlit as st
from supabase import create_client, Client
import os
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
APP_PASSWORD = os.getenv("APP_PASSWORD") or st.secrets.get("app_password")


# Password protection
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.text_input("Enter Password", type="password")
    if password == APP_PASSWORD:
        st.session_state.authenticated = True
        st.rerun()  # Updated method
    else:
        st.stop()

# ─────────────────────────────
# Set Wide Layout
# ─────────────────────────────
st.set_page_config(layout="wide")

# ─────────────────────────────
# Supabase Read-Only Client
# ─────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or st.secrets["SUPABASE_ANON_KEY"]
supabase_anon: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ─────────────────────────────
# Bowling Economy Rate Function
# ─────────────────────────────
def convert_decimal_overs_to_float(overs_series):
    """Convert cricket-style decimal overs (e.g. 3.5) to float overs (e.g. 3.8333)"""
    overs_series = overs_series.astype(float).fillna(0)
    full_overs = overs_series.astype(int)
    balls = ((overs_series - full_overs) * 10).round().astype(int)
    return full_overs + (balls / 6)

# ─────────────────────────────
# Bowling Over Display (Fix 15.9 overs)
# ─────────────────────────────
def convert_overs_to_balls(overs_series):
    """Convert overs like 3.5 to total balls."""
    overs = overs_series.astype(float).fillna(0)
    whole = overs.astype(int)
    decimal = (overs - whole).round(1) * 10
    return (whole * 6 + decimal).astype(int)

def convert_balls_to_overs(total_balls):
    """Convert balls (int) to overs in cricket format."""
    overs = total_balls // 6
    balls = total_balls % 6
    return overs + balls / 10

# ─────────────────────────────
# Column Reorder Function
# ─────────────────────────────
def reorder_columns(df: pd.DataFrame, desired_order: list) -> pd.DataFrame:
    actual = [col for col in desired_order if col in df.columns]
    return df[actual]

# ─────────────────────────────
# Page Header and Description
# ─────────────────────────────
st.markdown("""
<style>
.centered-logo {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-top: -35px;
}
</style>
<div class="centered-logo">
    <img src="https://raw.githubusercontent.com/AJ-Clark83/bears/refs/heads/main/Bayswater-Morley-Logo.png" alt="Bayswater Bears" width="150">
</div>
""", unsafe_allow_html=True)

st.title("Play.Cricket - Cricket Stats Extractor")
st.markdown('''This tool enhances Play.Cricket player data for both batting and bowling statistics and is updated weekly during the WA Premier Cricket Season''')
st.divider()

# ─────────────────────────────
# Season, Grade and Team Selection
# ─────────────────────────────
@st.cache_data(ttl=300)
def get_player_links():
    res = supabase_anon.table("player_links").select("player_name,team,season,grade,player_url").execute()
    return pd.DataFrame(res.data)

player_links_df = get_player_links()

# Select Season
seasons = sorted(player_links_df["season"].dropna().unique())
season = st.selectbox("Select Season", seasons)

# Select Grade based on Season
grades = sorted(
    player_links_df[player_links_df["season"] == season]["grade"]
    .dropna()
    .unique()
)
grade = st.selectbox("Select Grade", grades)

# Select Team based on Season + Grade (and exclude 'BAY')
teams = sorted(
    player_links_df[
        (player_links_df["season"] == season) &
        (player_links_df["grade"] == grade)
    ]["team"]
    .dropna()
    .unique()
)
teams = [t for t in teams if t != "BAY"]
team = st.selectbox("Select Team", teams)

# To include BAY replace teams above with this:
#teams = sorted(player_links_df[player_links_df["season"] == season]["team"].dropna().unique())
#team = st.selectbox("Select Team", teams)

# Maintain state after clicking 'Get Player Data'
if "load_data" not in st.session_state:
    st.session_state.load_data = False

if st.button("Get Player Data"):
    st.session_state.load_data = True

if st.session_state.load_data:
    with st.spinner("Fetching data..."):
        selected_links = player_links_df[
            (player_links_df["season"] == season) &
            (player_links_df["team"] == team) &
            (player_links_df["grade"] == grade)
        ][["player_name", "player_url"]].drop_duplicates()

        player_urls = selected_links["player_url"].unique().tolist()

        # ─────────── Batting Data ───────────
        res = supabase_anon.table("player_data_batting").select("*").in_("player_link", player_urls).execute()
        batting_df = pd.DataFrame(res.data)

        if not batting_df.empty:
            # Ensure player_name exists
            if "player_name" not in batting_df.columns or batting_df["player_name"].isna().all():
                batting_df = batting_df.merge(
                    selected_links,
                    how="left",
                    left_on="player_link",
                    right_on="player_url",
                    validate="many_to_one"
                )

            # ─────── Filter Section ───────
            st.subheader("Filter Data")
            #OLD FILTERING METHOD - CHOOSE ONE ONLY - OPTION 1
            # selected_seasons = st.multiselect("Filter by Season", sorted(batting_df["season"].dropna().unique()), default=sorted(batting_df["season"].dropna().unique()))

            # NEW FILTERING METHOD  - CHOOSE ONE ONLY - OPTION 2
            all_seasons = sorted(batting_df["season"].dropna().unique())
            selected_seasons = st.multiselect("Filter by Season", all_seasons)

            # Show all seasons by default if none selected
            if not selected_seasons:
                selected_seasons = all_seasons
            #END NEW FILTERING METHOD

            filtered = batting_df[batting_df["season"].isin(selected_seasons)]

            numeric_fields = ["runs", "balls", "4s", "6s", "innings"]
            for col in numeric_fields:
                filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0)

            # ─────── Table 1: Overall Batting Summary ───────
            st.subheader("Overall Batting Summary")
            st.markdown("**How Out, Average, Strike Rate and Boundaries Per Innings**")
            overall = filtered.groupby("player_name").agg({
                "how_out": lambda x: x.value_counts().to_dict(),
                "4s": "sum", "6s": "sum", "runs": "sum",
                "balls": "sum", "innings": "sum"
            }).reset_index()

            dismissal_types = set()
            for d in overall["how_out"]:
                dismissal_types.update(d.keys())
            for dtype in dismissal_types:
                overall[dtype] = overall["how_out"].apply(lambda x: x.get(dtype, 0))
            overall.drop(columns="how_out", inplace=True)

            overall["SR"] = ((overall["runs"] / overall["balls"]) * 100).round(2).replace([float("inf"), -float("inf")], 0)
            overall["Average"] = filtered.groupby("player_name")["runs"].mean().round(2).reset_index(drop=True)
            overall["Avg. 4s per inns."] = (overall["4s"] / overall["innings"]).round(2)
            overall["Avg. 6s per inns."] = (overall["6s"] / overall["innings"]).round(2)

            # overall_bowl["Economy"] = (overall_bowl["runs_conceded"] / overall_bowl["overs"]).round(2).replace([float("inf"), -float("inf")], 0) #original wrong formula
            overall.rename(columns={
                "innings":"Innings"

            }, inplace=True)

            st.dataframe(overall.drop(columns=["runs", "balls", "4s", "6s"]).sort_values("Average", ascending=False), use_container_width=True, hide_index=True)

            # ─────── Table 2: Season-by-Season Batting Stats ───────
            st.subheader("Season-by-Season Batting Stats")
            st.markdown("**Season Based Statistics on: How Out, Average, Strike Rate and Boundaries Per Innings**")

            player_options = sorted(filtered["player_name"].dropna().unique())
            selected_players_bat = st.multiselect("Select Players (Batting Table)", player_options, default=[])

            season_df = filtered.copy()
            if selected_players_bat:
                season_df = season_df[season_df["player_name"].isin(selected_players_bat)]

            season_df = season_df.groupby(["player_name", "season"]).agg({
                "how_out": lambda x: x.value_counts().to_dict(),
                "4s": "sum", "6s": "sum", "runs": "sum",
                "balls": "sum", "innings": "sum"
            }).reset_index()

            for dtype in dismissal_types:
                season_df[dtype] = season_df["how_out"].apply(lambda x: x.get(dtype, 0))
            season_df.drop(columns="how_out", inplace=True)

            season_df["SR"] = ((season_df["runs"] / season_df["balls"]) * 100).round(2).replace([float("inf"), -float("inf")], 0)
            season_df["Average"] = filtered.groupby(["player_name", "season"])["runs"].mean().round(2).reset_index(drop=True)
            season_df["Avg. 4s per inns."] = (season_df["4s"] / season_df["innings"]).round(2)
            season_df["Avg. 6s per inns."] = (season_df["6s"] / season_df["innings"]).round(2)

            st.dataframe(season_df.drop(columns=["runs", "balls", "4s", "6s"]).sort_values(["player_name", "season"]), use_container_width=True, hide_index=True)

            # Batting and Bowling Divider
            st.divider()

            # ─────── Table 3: Overall Bowling Summary ───────
            st.subheader("Overall Bowling Summary")
            st.markdown("**Statistics on: Dismissal Types by Bowler**")
            res_bowl = supabase_anon.table("player_data_bowling").select("*").in_("player_link", player_urls).execute()
            bowling_df = pd.DataFrame(res_bowl.data)

            if not bowling_df.empty:
                if "player_name" not in bowling_df.columns or bowling_df["player_name"].isna().all():
                    bowling_df = bowling_df.merge(
                        selected_links,
                        how="left",
                        left_on="player_link",
                        right_on="player_url",
                        validate="many_to_one"
                    )

                for col in ["innings", "overs", "wickets", "runs_conceded", "maidens", "top_4_w", "bottom_4_w", "bowled", "caught", "lbw", "c_and_b", "stumped", "other_wicket"]:
                    bowling_df[col] = pd.to_numeric(bowling_df[col], errors="coerce").fillna(0)

                # Create temporary column for bowling enconomy
                bowling_df["valid_overs"] = convert_decimal_overs_to_float(bowling_df["overs"])
                # calcualte balls bowled to show overs correctly
                bowling_df["balls_bowled"] = convert_overs_to_balls(bowling_df["overs"])

                overall_bowl = bowling_df.groupby("player_name").agg({
                    "innings": "sum", "balls_bowled": "sum", "runs_conceded": "sum",
                    "wickets": "sum", "top_4_w": "sum",
                    "bottom_4_w": "sum", "bowled": "sum", "caught": "sum",
                    "lbw": "sum", "c_and_b": "sum", "stumped": "sum",
                    "valid_overs": "sum","other_wicket": "sum"
                }).reset_index() # include maidens by adding "maidens": "sum" above

                # new economy rate and overs display
                overall_bowl["Economy"] = (overall_bowl["runs_conceded"] / overall_bowl["valid_overs"]).round(2)
                overall_bowl["SR"] = (overall_bowl["balls_bowled"] / overall_bowl["wickets"]).round(2)
                overall_bowl["Overs"] = overall_bowl["balls_bowled"].apply(convert_balls_to_overs)
                overall_bowl["Avg"] = (overall_bowl["runs_conceded"] / overall_bowl["wickets"]).round(2)

                #overall_bowl["Economy"] = (overall_bowl["runs_conceded"] / overall_bowl["overs"]).round(2).replace([float("inf"), -float("inf")], 0) #original wrong formula
                overall_bowl.rename(columns={
                    "top_4_w": "Top 4 Wickets", "bottom_4_w": "Tail Wickets",
                    "c_and_b": "C&B", "other_wicket": "Other","runs_conceded": "Runs Conceded","stumped": "Stumped",
                    "innings": "Innings", "overs": "Overs", "wickets": "Wickets", "lbw":"LBW","bowled":"Bowled","caught":"Caught"

                }, inplace=True)

                #### TEST BLOCK COLUMN REORDER
                desired_bowl_cols = [
                    "player_name", "Innings", "Overs","Wickets","Avg" ,"Runs Conceded", "Economy",
                    "SR", "Top 4 Wickets", "Tail Wickets", "Bowled", "Caught", "LBW", "C&B", "Stumped", "Other", "valid_overs", "balls_bowled"
                ] # maidens to be added here if included in groupby statement

                overall_bowl = reorder_columns(overall_bowl, desired_bowl_cols)

                # Drop the valid over column and show the dataframe
                st.dataframe(overall_bowl.drop(columns=["valid_overs","balls_bowled","Runs Conceded"]).sort_values("Wickets", ascending=False), use_container_width=True, hide_index=True)

                # ─────── Table 4: Season-by-Season Bowling Summary ───────
                st.subheader("Season-by-Season Bowling Stats")
                st.markdown("**Season Based Statistics on: Dismissal Types by Bowler**")

                player_options_bowl = sorted(bowling_df["player_name"].dropna().unique())
                selected_players_bowl = st.multiselect("Select Players (Bowling Table)", player_options_bowl, default=[])

                season_bowl = bowling_df.copy()
                if selected_players_bowl:
                    season_bowl = season_bowl[season_bowl["player_name"].isin(selected_players_bowl)]

                # Create temporary column for bowling enconomy
                season_bowl["valid_overs"] = convert_decimal_overs_to_float(season_bowl["overs"])
                # calcualte balls bowled to show overs correctly
                season_bowl["balls_bowled"] = convert_overs_to_balls(season_bowl["overs"])

                season_bowl = season_bowl.groupby(["player_name", "season"]).agg({
                    "innings": "sum", "balls_bowled": "sum", "runs_conceded": "sum",
                    "wickets": "sum", "top_4_w": "sum",
                    "bottom_4_w": "sum", "bowled": "sum", "caught": "sum",
                    "lbw": "sum", "c_and_b": "sum", "stumped": "sum",
                    "valid_overs": "sum","other_wicket": "sum"
                }).reset_index()
                # to include maidens, add "maidens": "sum" in the list above

                # new economy rate and overs display
                season_bowl["Economy"] = (season_bowl["balls_bowled"] / season_bowl["valid_overs"]).round(2)
                season_bowl["SR"] = (season_bowl["balls_bowled"] / season_bowl["wickets"]).round(2)
                season_bowl["Overs"] = season_bowl["balls_bowled"].apply(convert_balls_to_overs)
                season_bowl["Avg"] = (season_bowl["runs_conceded"] / season_bowl["wickets"]).round(2)

                season_bowl.rename(columns={
                    "top_4_w": "Top 4 Wickets", "bottom_4_w": "Tail Wickets",
                    "c_and_b": "C&B", "other_wicket": "Other","runs_conceded": "Runs Conceded","stumped": "Stumped",
                    "innings": "Innings", "wickets": "Wickets", "lbw":"LBW","bowled":"Bowled","caught":"Caught",

                }, inplace=True)

                #### TEST BLOCK COLUMN REORDER
                desired_bowl_season_cols = [
                    "player_name", "season", "Innings", "Overs", "Wickets","Avg" ,"Runs Conceded", "Economy",
                    "SR","Top 4 Wickets", "Tail Wickets", "Bowled", "Caught", "LBW", "C&B", "Stumped", "Other", "valid_overs", "balls_bowled"
                ] #Include "maidens" here to display if added to the groupby statement

                season_bowl = reorder_columns(season_bowl, desired_bowl_season_cols)

                st.dataframe(season_bowl.drop(columns=["valid_overs","balls_bowled","Runs Conceded"]).sort_values(["player_name", "season"]), use_container_width=True, hide_index=True)