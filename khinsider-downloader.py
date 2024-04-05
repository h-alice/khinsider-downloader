import os
import requests

from typing import Dict, List
from bs4 import BeautifulSoup

def get_format_from_link(file_url: str) -> str:
    """
    ### Get the format of the file from the link.
    It simply extract the extension of the file.

    ### Parameters:
        - file_url (str): The link url of the file.
    """

    return os.path.splitext(file_url)[1].replace(".", "")


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
        x.parent["href"].lower() # type: ignore
        for x in download_link_buttons 
        if x.parent and x.parent.has_attr("href")
    ]

    # Get the format of the file from the link.
    all_available_format = [get_format_from_link(x) for x in all_download_link]

    return dict(zip(all_available_format, all_download_link))