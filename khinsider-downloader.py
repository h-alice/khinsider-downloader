import os
import requests
import asyncio
from typing import Dict, List
from bs4 import BeautifulSoup

KHINSIDER_SITE_ROOT = "https://downloads.khinsider.com/"

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
