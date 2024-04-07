import os
import logging
import asyncio
import requests
import argparse
import urllib.parse
from pathlib import Path
from typing import Dict, List
from bs4 import BeautifulSoup

KHINSIDER_SITE_ROOT = "https://downloads.khinsider.com/"
KHINSIDER_ALBUM_ROOT = "https://downloads.khinsider.com/game-soundtracks/album/"

def file_name_cleaner(file_name: str, replace_char: str="_") -> str:
    """
    ### Clean the file name, remove the special characters.
    This method will remove the special characters from the file name.

    Parameters:
        - file_name (str): The file name, what do you expect?
    """

    # Banned character in Windows filenames
    windows_unusable_characters = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']

    # Banned character in Linux filenames
    linux_unusable_characters = ['/', '\0', ':', '\n', '\t', '\r', '?', '*', '|', '>', '<', '"', '\'']

    # Combine both lists
    unusable_characters = windows_unusable_characters + linux_unusable_characters

    # Replace the unusable characters with `_`.
    for char in unusable_characters:
        file_name = file_name.replace(char, replace_char)

    return file_name

def get_format_from_link(file_url: str) -> str:
    """
    ### Get the format of the file from the link.
    It simply extract the extension of the file.

    ### Parameters:
        - file_url (str): The link url of the file.
    """

    return os.path.splitext(file_url)[1].replace(".", "").lower()


def song_download_page_handler(html_content: str) -> Dict[str, str]:
    """
    ### Handle the song download page.
    It will extract the download links of the song.

    Parameters:
        - html_content (str): The html content of the page.
    """

    content_page = BeautifulSoup(html_content, 'html.parser')

    # Get the elements of download buttons.
    download_link_buttons = content_page.select('.songDownloadLink')

    # Trace back to the parent element to get the download link.
    all_download_link: List[str] = [
        x.parent["href"] # type: ignore
        for x in download_link_buttons 
        if x.parent and x.parent.has_attr("href")
    ]

    # Get the format of the file from the link.
    all_available_format = [get_format_from_link(x) for x in all_download_link]

    return dict(zip(all_available_format, all_download_link))

async def album_page_row_parser(song_url: str, semaphore: asyncio.Semaphore) -> Dict[str, str]:
    """
    ### Parse a single row of the album page.
    Return the song download link of the song.
    1. Download the song page content.
    2. Get the available song format along with the download link.

    Parameters:
        - row (str): The html content of the row.
        - semaphore (asyncio.Semaphore): The semaphore to control maximum number of workers.
    """

    async with semaphore:

        # Get the song page.
        song_page = await asyncio.to_thread(requests.get, song_url)

        # Get the song download link.
        song_download_link = song_download_page_handler(song_page.text)

        return song_download_link
    
async def album_page_handler(html_content: str, max_parser_worker: int=3) -> Dict[str, str | List[Dict[str, str]]]:
    """
    ### Handle the album page.
    It will extract the download links of the songs in the album.

    Parameters:
        - html_content (str): The html content of the page.
    """

    content_page = BeautifulSoup(html_content, 'html.parser')

    # Get the album title if available.
    album_title = content_page.select_one(r'#pageContent h2')
    if album_title:
        album_title = album_title.text
    else:
        album_title = ""
    
    # Get the album table.
    album_table = content_page.select_one(r'#songlist')

    if not album_table:
        song_links = []
    else:
        all_rows = album_table.select('tr:nth-child(n+1)') # Skip the header row.
        if len(all_rows) == 0:
            song_links = []
        else:
            # Get the elements of song links.
            song_links = [
                x.select_one('.playlistDownloadSong a')["href"] # type: ignore
                for x in all_rows
                if x.select_one('.playlistDownloadSong a')
            ]

            # Combine the song links with the site root.
            song_links = [
                f"{KHINSIDER_SITE_ROOT}{x}"
                for x in song_links
            ]

    # Create the semaphore.
    semaphore = asyncio.Semaphore(max_parser_worker)

    # Create the tasks.
    tasks = [
        album_page_row_parser(x, semaphore)
        for x in song_links
        if isinstance(x, str)
    ]

    # Run the tasks.
    all_song_download_link = await asyncio.gather(*tasks)

    # Combine the final parsed page.
    parsed_page = dict(
        album_title=album_title,
        songs=all_song_download_link
    )

    return parsed_page

async def download_single_song(song_url: str, semaphore: asyncio.Semaphore, dir: Path = Path("."), content_length_check: bool=False) -> str:
    """
    ### Download the song.
    It will download the song from the link.

    Parameters:
        - song_url (str): The link url of the song.
        - semaphore (asyncio.Semaphore): The semaphore to control
            maximum number of workers.
    """
    
    async with semaphore:

        # Extract the file name from the url.
        song_name = os.path.basename(song_url)

        # URL decode the song name.
        song_name = urllib.parse.unquote(song_name, encoding='utf-8', errors='replace')

        # Replace some special characters in both Linux and Windows with `_`.
        song_name = file_name_cleaner(song_name)

        # Get the song content.
        song_content = await asyncio.to_thread(requests.get, song_url)

        # Check if length of the content matches the content length.
        if content_length_check:
            if "Content-Length" in song_content.headers:  # Check if the content length field is available.
                content_length = int(song_content.headers["Content-Length"]) # Get the downloaded content length.
                if content_length != len(song_content.content): # Check if the content length matches.
                    raise ValueError("Content length mismatch.")


        # Everything is OK, write the song content to the file.
        song_name = dir / song_name
        with open(song_name, 'wb') as f:
            f.write(song_content.content)

        return song_name.as_posix()
    

async def main(args):
    """
    ### The main function.
    It will handle the main logic of the script.

    Parameters:
        - args (argparse.Namespace): The command line arguments.
    """

    # Get the album page.
    album_page = requests.get(args.album_link)

    logging.info(f"[.] Parsing the album page.")

    full_album_parsed = await album_page_handler(
        album_page.text,
        args.max_worker
    )

    logging.info(f"[.] Album title: {full_album_parsed['album_title']}")
    logging.info(f"[.] Total songs: {len(full_album_parsed['songs'])}")

    # Check if format in the available formats.
    for song in full_album_parsed['songs']:
        if isinstance(song, dict): # Just to be sure nothitng is wrong.
            if args.format not in song.keys():
                logging.error(f"Format {args.format} is not available in the song: {song}")
                exit(1)

    logging.info(f"[+] Album parsing completed.")

    logging.info(f"[.] Starting the download.")

    # Create the semaphore.
    semaphore = asyncio.Semaphore(args.max_worker)

    # Target links.
    target_links = [
        song[args.format]
        for song in full_album_parsed['songs']
    ]

    # Create directory to save the album.
    if isinstance(full_album_parsed['album_title'], str):
        if full_album_parsed['album_title'] == "":
            file_name_cleaned = "downloaded_album"
        album_dir = Path(args.save_dir) / file_name_cleaner(full_album_parsed['album_title'])
    else:
        album_dir = Path(args.save_dir) / "downloaded_album"

    album_dir.mkdir(parents=True, exist_ok=True)
    

    # Create the tasks.
    tasks = [
        download_single_song(song[args.format], semaphore, dir=album_dir, content_length_check=True)
        for song in full_album_parsed['songs']
    ]

    # Invoke the tasks.
    downloaded_songs = await asyncio.gather(*tasks)

    logging.info(f"[+] Download completed.")
def parse_args():
    """
    ### Parse the command line arguments.

    Parameters:
        - None
    """
    parser = argparse.ArgumentParser(description="Script description here")

    # Album link argument
    parser.add_argument("-l", "--album-link", type=str, default=None, help="The URL of the target album")

    # Album name argument
    parser.add_argument("-a", "--album", type=str, default=None, help="The album name")

    # Max worker argument
    parser.add_argument("--max-worker", type=int, default=3, help="The max concurrent worker number")

    # Perfered format argument: One of ["mp3", "flac", "ogg"]
    parser.add_argument("-f", "--format", type=str, default="mp3", help="Download format: mp3, flac, ogg")

    # Directory to save the album
    parser.add_argument("-d", "--save-dir", type=str, default=".", help="The directory to save the album")

    # Capture the other argument
    parser.add_argument("positional_arg", nargs="?", default=None, help="The album url, if no flag is provided.")

    args = parser.parse_args()

    # If the positional argument is provided, assign it to the album link.
    if args.album_link is None and args.album is None:
        if args.positional_arg is not None:
            args.album_link = args.positional_arg
        else:
            parser.error("Please provide at least one of the following: --album-link, --album")

    if args.album and args.album_link:
        # NOTE: In future, `--album-link` will be ignored if `--album` is provided.
        parser.error("Please provide either --album or --album-link, not both.")

    if args.album:
        # Currently not implemented.
        # TODO: Convert the album name to album link.
        parser.error("The --album option is not implemented yet.")

    return args

if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=logging.INFO)

    asyncio.run(main(args))