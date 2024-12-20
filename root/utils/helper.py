import os
import logging
import tempfile
from rapidfuzz import process, fuzz

import webbrowser


logger = logging.getLogger(__name__)


def wrap_with_scraper_api(url):
    """
    Builds a URL with the ScraperAPI endpoint and required query parameters.
    """
    return f'http://api.scraperapi.com?api_key={os.getenv("SCRAPER_API_KEY")}&url={url}'


def get_most_similar_word(word, vocabulary):
    """
    Finds the most similar word from a given vocabulary based on a similarity threshold.
    """
    matched_region = process.extractOne(word, vocabulary, scorer=fuzz.token_sort_ratio)

    if matched_region and matched_region[1] > int(
        os.getenv("WORD_SIMILARITY_THRESHOLD")
    ):
        return matched_region[0]


def preview_html(response_text):
    """
    Saves the provided HTML content to a temporary file and opens it in the default web browser.
    """
    try:
        temp_dir = tempfile.mkdtemp()
    except OSError as e:
        logger.info(f"Failed to create temporary directory: {e}")
        return

    try:
        temp_file_path = os.path.join(temp_dir, "page.html")

        with open(temp_file_path, "w", encoding="utf-8") as file:
            file.write(response_text)
    except (OSError, IOError) as e:
        logger.info(f"Failed to write to the temporary file: {e}")
        return

    try:
        webbrowser.open(f"file://{temp_file_path}")
        logger.info(f"HTML file saved to {temp_file_path} and opened in browser.")
    except webbrowser.Error as e:
        logger.info(f"Failed to open the file in the web browser: {e}")
