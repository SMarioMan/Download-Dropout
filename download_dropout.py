import argparse
import os
import requests
import time
import subprocess
import shutil
import sys
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- Configuration ---
BASE_URL = "https://watch.dropout.tv"
SERIES_INDEX = BASE_URL + "/series"
OUTPUT_FILE = "urls.txt"
COOKIES_FILE = "config/cookies.txt"
ARCHIVE_FILE = "config/archive.txt"

# Headers to mimic a browser and avoid bot detection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; dropout-catalog/slow-mode)"
}

REQUEST_DELAY = 2.5   # seconds between requests
TIMEOUT = 60          # seconds

session = requests.Session()
session.headers.update(HEADERS)

def blocking_get(url, allow_400_stop=False):
    """
    Robust GET request that retries on errors.
    Returns the response object.
    """
    while True:
        try:
            print(f"[GET] {url}")
            response = session.get(url, timeout=TIMEOUT)

            # If we allow 400 to stop (used for pagination checks), return it
            if allow_400_stop and response.status_code == 400:
                return response

            response.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return response

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if allow_400_stop and status == 400:
                return e.response
            print(f"HTTP {status} error, retrying slowly...")
            time.sleep(REQUEST_DELAY * 2)

        except requests.exceptions.RequestException as e:
            print(f"Network error ({e}), retrying slowly...")
            time.sleep(REQUEST_DELAY * 2)

def get_series_from_page(page_num):
    """Scrapes a single page of the series index."""
    url = SERIES_INDEX if page_num == 1 else f"{SERIES_INDEX}?page={page_num}"
    r = blocking_get(url, allow_400_stop=True)

    if r.status_code == 400:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    series = []

    for item in soup.select("li.js-collection-item.item-type-series"):
        link = item.select_one("a.browse-item-link[href]")
        title = item.select_one(".browse-item-title strong")

        if link:
            series.append({
                "title": title.get_text(strip=True) if title else "Unknown",
                "url": link["href"]
            })
    return series

def scrape_all_series():
    """Iterates through all pages of the series index."""
    all_series = []
    seen = set()
    page = 1

    print("--- Finding all Series ---")
    while True:
        batch = get_series_from_page(page)
        if batch is None:
            break
        
        for s in batch:
            if s["url"] not in seen:
                seen.add(s["url"])
                all_series.append(s)
        page += 1
    
    print(f"Total Series Found: {len(all_series)}\n")
    return all_series

def get_episode_links(show_url, season_number):
    """Scrapes all episode links from a specific season page."""
    season_url = f"{show_url}/season:{season_number}"
    r = blocking_get(season_url)

    # If the season page redirects to the show page or 404s (softly), it usually means the season doesn't exist
    # However, blocking_get handles 404s by retrying usually, but here we assume valid URLs.
    # Dropout usually just loads the page. If it's empty, we catch it below.
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    
    # We check if we are actually on a season page or redirected back (some sites do this)
    # But strictly speaking, we just look for episode links.
    for a in soup.select("a.browse-item-link[href]"):
        full_url = urljoin(show_url, a["href"])
        links.append(full_url)

    return links

def scrape_show_episodes(show):
    """Generates a list of all episode URLs for a given show."""
    show_title = show["title"]
    show_url = show["url"]
    
    season = 1
    all_episodes = []

    print(f"--- Scraping: {show_title} ---")
    while True:
        episodes = get_episode_links(show_url, season)
        
        if not episodes:
            # No episodes found for this season implies we've reached the end
            break
            
        for url in episodes:
            all_episodes.append(url)
        
        season += 1
        
    return all_episodes


def resolve_binary(names):
    """
    Resolve a binary from:
    1. System PATH
    2. Current directory
    Returns absolute path or None
    """
    for name in names:
        # Check PATH
        path = shutil.which(name)
        if path:
            return path
        # Check current directory
        local = os.path.abspath(name)
        if os.path.isfile(local):
            return local
    return None


def get_ytdlp_binary():
    if os.name == "nt":
        candidates = ["yt-dlp.exe", "yt-dlp"]
    else:
        candidates = ["yt-dlp"]
    binary = resolve_binary(candidates)
    if not binary:
        raise FileNotFoundError("yt-dlp binary not found in PATH or current directory")
    return binary


def get_ffmpeg_path():
    if os.name == "nt":
        candidates = ["ffmpeg.exe", "ffmpeg"]
    else:
        candidates = ["ffmpeg"]
    return resolve_binary(candidates)


def run_ytdlp(output_dir="Dropout"):
    # Note: Cookies check is now handled in main(), but we keep the safety check here.
    if not os.path.exists(COOKIES_FILE):
        print(f"\nERROR: '{COOKIES_FILE}' is missing. Cannot proceed with download.")
        return

    try:
        ytdlp = get_ytdlp_binary()
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        return
    ffmpeg_path = get_ffmpeg_path()

    output_template = os.path.join(
        output_dir,
        "%(series)s/Season %(season_number)02d/%(episode_number)02d - %(episode)s.%(ext)s"
    )

    print("\n" + "=" * 50)
    print("STARTING YT-DLP DOWNLOAD")
    print("=" * 50 + "\n")

    command = [
        ytdlp,
        "--cookies", COOKIES_FILE,
        "-a", OUTPUT_FILE,
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--embed-subs",
        "--embed-thumbnail",
        "--add-metadata",
        "--embed-metadata",
        "--write-info-json",
        "--write-description",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "--download-archive", ARCHIVE_FILE,
        "-o", output_template
    ]

    # Explicit ffmpeg location if we found it
    if ffmpeg_path:
        command.extend(["--ffmpeg-location", ffmpeg_path])

    try:
        subprocess.run(command, check=True)
        print("\nDownload batch complete.")
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp encountered an error (Code: {e.returncode}).")
    except KeyboardInterrupt:
        print("\nDownload cancelled by user.")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape Dropout and download episodes with yt-dlp"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="Dropout",
        help="Base directory where videos will be downloaded"
    )
    return parser.parse_args()

def check_prerequisites():
    """Checks for cookies and archive files before starting."""
    print("--- Checking Prerequisites ---")
    
    # Critical Check: Cookies
    if not os.path.exists(COOKIES_FILE):
        print(f"\n[CRITICAL ERROR] Cookies file not found: {os.path.abspath(COOKIES_FILE)}")
        print("You must export your cookies as 'cookies.txt' and place them in the 'config' folder.")
        print("Cannot proceed without cookies.")
        sys.exit(1)
    else:
        print(f"[OK] Cookies found: {COOKIES_FILE}")

    # Warning Check: Archive
    if not os.path.exists(ARCHIVE_FILE):
        print(f"\n[WARNING] Archive file not found: {os.path.abspath(ARCHIVE_FILE)}")
        print("yt-dlp will NOT be able to skip previously downloaded videos.")
        print("A new archive file will be created after this run.")
        print("If this is your first run, you can ignore this warning.\n")
        time.sleep(2) # Give user a moment to read the warning
    else:
        print(f"[OK] Archive found: {ARCHIVE_FILE}")
    print("------------------------------\n")

if __name__ == "__main__":
    args = parse_args()

    # Perform checks immediately
    check_prerequisites()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Expand ~ and environment variables first
    raw_output_dir = os.path.expandvars(os.path.expanduser(args.output_dir))
    # If relative, resolve relative to script location
    if not os.path.isabs(raw_output_dir):
        output_dir = os.path.abspath(os.path.join(script_dir, raw_output_dir))
    else:
        output_dir = os.path.abspath(raw_output_dir)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving results to {output_dir}")

    series_list = scrape_all_series()
    print("--- Scraping Episodes & Writing to File ---")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        pass

    total_urls = 0
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            for show in series_list:
                # Get all episodes for this show
                episode_urls = scrape_show_episodes(show)
                # Write them to file immediately
                for url in episode_urls:
                    f.write(url + "\n")
                    total_urls += 1
    except KeyboardInterrupt:
        print("\nScraping interrupted! Proceeding to download with whatever we found...")

    print(f"\nScraping Finished. Found {total_urls} links.")
    if total_urls > 0:
        run_ytdlp(output_dir)
    else:
        print("No URLs found. Exiting.")
