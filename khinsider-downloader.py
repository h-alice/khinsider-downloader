import os
import requests
from bs4 import BeautifulSoup

def get_format_from_link(file_url: str) -> str:
    """
    ### Get the format of the file from the link.
    It simply extract the extension of the file.

    Parameters:
        - file_url (str): The link url of the file.
    """

    return os.path.splitext(file_url)[1].replace(".", "")
