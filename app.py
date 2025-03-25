import streamlit as st
import pandas as pd
import time
import os
import tempfile

# NEW driver setup
import undetected_chromedriver as uc

# Selenium + Scraping
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from bs4 import BeautifulSoup

# Function to start undetected Chrome
def get_chromedriver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = "/usr/bin/chromium"
    driver = uc.Chrome(options=options, headless=True)
    return driver

# --- Streamlit UI ---
st.set_page_config(page_title="Cricket Stats Extractor", layout="wide")

# Display a logo at the top center of the page
st.markdown(
    """
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
    """,
    unsafe_allow_html=True
)

st.title("Play.Cricket - Cricket Stats Extractor")
st.markdown('''This tool will extract all of the current players for a selected team, and then obtain the count by mode of dismissal, strike rate, and average for the number of seasons selected. To use the tool, 
simply paste the **:red[competition link]** in the field below and press enter. Then choose your team from the options presented, and finally the number of  seasons to scrape stats from.  
  
The competition link can be found on [Play.Cricket](https://play.cricket.com.au/competitions), by visiting the competitions page, and copying the link to the individual competition of interest. 
  
**Note:** The link must take you to a page where the fixtures/ results are presented, and not a page that lists the various sub-competitions within that competition.  
  An example link that **will work** is as follows - The John Inverarity Shield (Male Under 13s): [https://play.cricket.com.au/grade/5ba93ab9-e716-4c0e-861b-65337c17cbad?tab=matches](https://play.cricket.com.au/grade/5ba93ab9-e716-4c0e-861b-65337c17cbad?tab=matches) ''')
st.divider()

if "submitted" not in st.session_state:
    st.session_state.submitted = False

# Set up chromedriver path with local directory to avoid permission issues
chromedriver_path = os.path.join(".", "temp_driver")
os.makedirs(chromedriver_path, exist_ok=True)
chromedriver_autoinstaller.install(path=chromedriver_path)

# Step 1: Get competition URL
competition_url = st.text_input("**Please Enter a Competition URL and Press Enter:**")

selected_team = None
user_defined_season_count = None
submit_button = False

# Step 2: Fetch team list and let user select
if competition_url and not st.session_state.submitted:
    with st.spinner("Loading team list..."):
        try:
            options = Options()
            options.add_argument("--headless")
            driver = get_chromedriver()
            driver.get(competition_url)
            wait = WebDriverWait(driver, 10)
            team_dropdown_button = wait.until(EC.element_to_be_clickable((By.ID, "competition-matches-team")))
            team_dropdown_button.click()
            team_options_ul = wait.until(EC.presence_of_element_located((By.ID, "competition-matches-team-options-list")))
            team_buttons = team_options_ul.find_elements(By.CLASS_NAME, "o-dropdown__item-trigger")
            teams = [btn.get_attribute("label") for btn in team_buttons if btn.get_attribute("label") != "All teams"]
            driver.quit()

            selected_team = st.selectbox("**Select Team**", options=teams)
            user_defined_season_count = st.slider("**How many seasons do you want to scrape?**", 1, 5, 2)
            submit_button = st.button("**Submit**",type="primary")

            if submit_button:
                st.session_state.submitted = True
                st.session_state.competition_url = competition_url
                st.session_state.selected_team = selected_team
                st.session_state.user_defined_season_count = user_defined_season_count

        except Exception as e:
            st.error("Failed to load team list. Please check the URL.")
            st.stop()

@st.cache_data(ttl=86400, show_spinner=False)
def cached_scrape(competition_url, selected_team, user_defined_season_count):
    options = Options()
    options.add_argument("--headless")
    driver = get_chromedriver()

    driver.get(competition_url)
    wait = WebDriverWait(driver, 10)
    team_dropdown_button = wait.until(EC.element_to_be_clickable((By.ID, "competition-matches-team")))
    team_dropdown_button.click()
    team_options_ul = wait.until(EC.presence_of_element_located((By.ID, "competition-matches-team-options-list")))
    team_buttons = team_options_ul.find_elements(By.CLASS_NAME, "o-dropdown__item-trigger")

    team_abbrev = selected_team[:3].upper()
    for btn in team_buttons:
        if btn.get_attribute("label") == selected_team:
            btn.click()
            break
    time.sleep(3)

    match_links = []
    match_card_anchors = driver.find_elements(By.CSS_SELECTOR, "a.o-play-match-card__link")
    for a in match_card_anchors:
        match_links.append(a.get_attribute("href"))

    player_links = set()
    def get_player_links(match_url):
        try:
            driver.get(match_url)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "o-toggle__label")))
            toggle_labels = driver.find_elements(By.CLASS_NAME, "o-toggle__label")
            for label in toggle_labels:
                if team_abbrev in label.text:
                    label.click()
                    time.sleep(2)
                    break
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.w-play-match-centre-scorecard__table--batting")))
            batting_table = driver.find_element(By.CSS_SELECTOR, "table.w-play-match-centre-scorecard__table--batting")
            rows = batting_table.find_elements(By.CSS_SELECTOR, "a.w-play-match-centre-scorecard__player-name--link")
            for link in rows:
                href = link.get_attribute("href")
                if href:
                    player_links.add(href + '?tab=matches')
        except:
            pass

    st.subheader("Scraping Progress")
    match_progress = st.progress(0, text="Collecting player links...")
    for i, match in enumerate(match_links):
        get_player_links(match)
        match_progress.progress((i + 1) / len(match_links), text=f"Match {i+1}/{len(match_links)}")

    def extract_table(soup, season):
        name_tag = soup.find("h1", class_="w-play-player-header__player-name")
        player_name = name_tag.get_text(strip=True) if name_tag else "Unknown Player"
        table = soup.find("table", class_="o-table__table")
        if not table or not table.find("tbody"):
            return pd.DataFrame()
        rows = table.find("tbody").find_all("tr")
        data = []
        for row in rows:
            if "Did not bat" in row.get_text():
                continue
            heading = row.find("th")
            cells = row.find_all("td")
            match_name = heading.find("a").get_text(strip=True) if heading else ""
            grade = heading.find("span").get_text(strip=True) if heading and heading.find("span") else ""
            values = []
            for td in cells:
                divs = td.find_all("div", class_="w-play-player-matches__inning-line")
                if not divs:
                    continue
                div = divs[0]
                tooltip = div.find("div", class_="o-tooltip")
                if tooltip:
                    abbrev = tooltip.contents[0].strip() if tooltip.contents else ""
                    values.append(abbrev)
                else:
                    values.append(div.get_text(strip=True))
            if len(values) == 7:
                inn, runs, balls, fours, sixes, sr, how_out = values
                data.append([match_name, grade, inn, runs, balls, fours, sixes, sr, how_out])
        columns = ["Match", "Grade", "Innings", "Runs", "Balls", "4s", "6s", "SR", "How Out"]
        df = pd.DataFrame(data, columns=columns)
        df["Season"] = season
        df["Player"] = player_name
        df["How Out"] = df["How Out"].replace({"no": "Not Out", "rtno": "Not Out", "c": "Caught", "b": "Bowled", "lbw": "LBW", "ro": "Run Out", "hw": "Hit Wicket"})
        return df

    retry_players = set()
    combined_player_df = []

    def scrape_player(player_url, retry_set=None):
        try:
            driver.get(player_url)
            wait = WebDriverWait(driver, 13)
            wait.until(EC.element_to_be_clickable((By.ID, "season")))
            season_button = driver.find_element(By.ID, "season")
            season_button.click()
            season_options = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#season-options-list button.o-dropdown__item-trigger")))
            season_dfs = []
            for i, option in enumerate(season_options[:user_defined_season_count]):
                try:
                    label = option.get_attribute("label")
                    option.click()
                    time.sleep(2)
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    df = extract_table(soup, label)
                    if not df.empty:
                        season_dfs.append(df)
                    if i < user_defined_season_count - 1 and len(season_options) > i + 1:
                        season_button = wait.until(EC.element_to_be_clickable((By.ID, "season")))
                        season_button.click()
                        time.sleep(1)
                except Exception:
                    if retry_set is not None:
                        retry_set.add(player_url)
                    return None
            if season_dfs:
                return pd.concat(season_dfs, ignore_index=True)
            else:
                if retry_set is not None:
                    retry_set.add(player_url)
                return None
        except Exception:
            if retry_set is not None:
                retry_set.add(player_url)
            return None

    player_progress = st.progress(0, text="Scraping player stats...")
    for i, player in enumerate(player_links):
        df = scrape_player(player, retry_players)
        if df is not None:
            combined_player_df.append(df)
        player_progress.progress((i + 1) / len(player_links), text=f"Player {i+1}/{len(player_links)}")

    for attempt in range(3):
        if not retry_players:
            break
        still_failed = set()
        for player in retry_players:
            df = scrape_player(player, still_failed)
            if df is not None:
                combined_player_df.append(df)
        retry_players = still_failed

    driver.quit()

    if not combined_player_df:
        return None, None

    final_combined = pd.concat(combined_player_df, ignore_index=True)
    final_combined['Runs'] = pd.to_numeric(final_combined['Runs'], errors='coerce')
    final_combined['Balls'] = pd.to_numeric(final_combined['Balls'], errors='coerce')
    final_combined['Dismissed'] = final_combined['How Out'].apply(lambda x: 0 if x == 'Not Out' else 1)

    player_totals = final_combined.groupby(['Player', 'How Out'])['Match'].count().unstack(fill_value=0).reset_index()
    batting_totals = final_combined.groupby(['Player']).agg({'Runs': 'sum', 'Balls': 'sum', 'Dismissed': 'sum'}).reset_index()
    batting_totals['S/R'] = batting_totals.apply(lambda row: round((row['Runs'] / row['Balls']) * 100, 2) if row['Balls'] > 0 else 0, axis=1)
    batting_totals['Avg.'] = batting_totals.apply(lambda row: round((row['Runs'] / row['Dismissed']), 2) if row['Dismissed'] > 0 else None, axis=1)
    merged_df_at = player_totals.merge(batting_totals[['Player', 'S/R', 'Avg.']], on='Player', how='left')
    expected_cols_at = ['Player', 'Caught', 'Bowled', 'LBW', 'Run Out', 'Hit Wicket', 'Not Out', 'S/R', 'Avg.']
    for col in expected_cols_at:
        if col not in merged_df_at.columns:
            merged_df_at[col] = 0
    merged_df_at = merged_df_at[expected_cols_at]

    player_totals_season = final_combined.groupby(['Player', 'Season', 'How Out'])['Match'].count().unstack(fill_value=0).reset_index()
    batting_totals_season = final_combined.groupby(['Player', 'Season']).agg({'Runs': 'sum', 'Balls': 'sum', 'Dismissed': 'sum'}).reset_index()
    batting_totals_season['S/R'] = batting_totals_season.apply(lambda row: round((row['Runs'] / row['Balls']) * 100, 2) if row['Balls'] > 0 else 0, axis=1)
    batting_totals_season['Avg.'] = batting_totals_season.apply(lambda row: round((row['Runs'] / row['Dismissed']), 2) if row['Dismissed'] > 0 else None, axis=1)
    merged_df = player_totals_season.merge(batting_totals_season[['Player', 'Season', 'S/R', 'Avg.']], on=['Player', 'Season'], how='left')
    expected_cols_season = ['Player', 'Season', 'Caught', 'Bowled', 'LBW', 'Run Out', 'Hit Wicket', 'Not Out', 'S/R', 'Avg.']
    for col in expected_cols_season:
        if col not in merged_df.columns:
            merged_df[col] = 0
    merged_df = merged_df[expected_cols_season]

    return merged_df_at, merged_df

if st.session_state.submitted:
    with st.spinner("Scraping match and player data..."):
        merged_df_at, merged_df = cached_scrape(
            st.session_state.competition_url,
            st.session_state.selected_team,
            st.session_state.user_defined_season_count
        )

    if merged_df_at is not None:
        st.subheader("All Time Stats")
        selected_names_at = st.multiselect("Filter by Player (All Time)", options=merged_df_at['Player'].unique())
        df_display_at = merged_df_at[merged_df_at['Player'].isin(selected_names_at)] if selected_names_at else merged_df_at
        st.dataframe(df_display_at.reset_index(drop=True), use_container_width=True, hide_index=True)

        st.subheader("Season Stats")
        selected_names_season = st.multiselect("Filter by Player (Season)", options=merged_df['Player'].unique())
        df_display_season = merged_df[merged_df['Player'].isin(selected_names_season)] if selected_names_season else merged_df
        st.dataframe(df_display_season.reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.error("No player data was extracted.")
