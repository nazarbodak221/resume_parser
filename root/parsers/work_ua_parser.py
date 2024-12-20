import os
import re
import math
import json
import logging

import requests
from urllib.parse import urlencode
from bs4 import BeautifulSoup

import schemas
import utils

logger = logging.getLogger(__name__)


class WorkUaParser:
    """
    A parser for interacting with the Work.ua website to search resumes and handle related data.
    """

    base_url = os.getenv("WORK_UA_URL")

    def __init__(self):
        """
        Initializes the Work.ua parser with the base URL for resumes.
        """
        self.REGIONS = self.__load_regions()
        self.SALARY_FROM_OPTIONS, self.SALARY_TO_OPTIONS = self.__load_salary_options()
        self.EXPERIENCE_OPTIONS = self.__load_experience_options()

    def __load_regions(self):
        """
        Loads the region data from a JavaScript URL or JSON file.
        """
        json_file_path = os.getenv("WORK_UA_REGIONS_JSON_PATH")
        try:
            with open(json_file_path, "r") as json_file:
                return json.load(json_file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.info(
                f"Failed to load regions from file: {e}. Fetching from JS URL..."
            )

        js_url = os.getenv("WORK_UA_MIN_JS_URL")
        response = requests.get(js_url)
        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch JavaScript content: {response.status_code}"
            )

        return self.__extract_regions(response.text)

    def __extract_regions(self, js_content):
        """
        Extracts region data from JavaScript content.
        """
        pattern = r"citiesTH\s*=\s*\[(.*?)];"
        match = re.search(pattern, js_content, re.DOTALL)

        if match:
            cities_th_raw = match.group(1)
            cities_th_json = re.sub(r"(\w+):", r'"\1":', cities_th_raw)
            try:
                cities_th_list = json.loads(f"[{cities_th_json}]")
                regions = {city["en"]: city["id"] for city in cities_th_list}
                return regions
            except json.JSONDecodeError as e:
                raise Exception(f"Error decoding JSON: {e}")
        else:
            raise Exception("citiesTH list not found in the JavaScript content.")

    def __load_salary_options(self):
        """
        Loads salary data from a JSON file.
        """
        salary_json_path = os.getenv("WORK_UA_SALARY_JSON_PATH")
        try:
            with open(salary_json_path, "r") as json_file:
                salary_data = json.load(json_file)
                return salary_data.get("from", {}), salary_data.get("to", {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.info(f"Failed to load salary options from file: {e}.")
            return {}, {}

    def __load_experience_options(self):
        """
        Loads experience data from a JSON file.
        """
        experience_json_path = os.getenv("WORK_UA_EXPERIENCE_JSON_PATH")
        try:
            with open(experience_json_path, "r") as json_file:
                return json.load(json_file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.info(f"Failed to load experience options from file: {e}.")
            return {}

    @staticmethod
    def get_total_candidates(html: str) -> int:
        """
        Parses the HTML content to extract the total number of candidates.
        """
        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text()
        match = re.search(
            r"(\d+)\s+(candidate|candidates)", text_content, re.IGNORECASE
        )
        if match:
            return int(match.group(1))
        else:
            raise Exception("Unable to find candidate count in the HTML content.")

    @staticmethod
    def build_resumes_url(params: dict) -> str:
        """
        Builds the URL for fetching resume data using query parameters.
        """
        return f"{WorkUaParser.base_url}{os.getenv('WORK_UA_RESUMES_URL')}?{urlencode(params)}"

    @staticmethod
    def format_experience_detail(experience: str) -> str:
        """
        Formats the experience detail by removing unnecessary characters.
        """
        return experience.strip().replace("\xa0", " ")

    def __unpack_search_options(self, params: schemas.SearchOptions) -> dict:
        """
        Converts the provided search options into a dictionary suitable for API requests.
        """
        payload = {
            "search": params.search,
        }

        if params.region:
            region = utils.get_most_similar_word(params.region, self.REGIONS.keys())
            payload["region"] = self.REGIONS.get(region)
        if params.salary_from:
            payload["salaryfrom"] = self.SALARY_FROM_OPTIONS.get(
                str(params.salary_from)
            )
        if params.salary_to:
            payload["salaryto"] = self.SALARY_TO_OPTIONS.get(str(params.salary_to))
        if params.experience:
            payload["experience"] = "+".join(
                self.EXPERIENCE_OPTIONS.get(exp, "") for exp in params.experience
            )

        return payload

    def get_resume_pages(self, params: schemas.SearchOptions) -> list[str]:
        """
        Fetches HTML content of the Work.ua resume section, formatted with pagination and search parameters.
        """
        payload = self.__unpack_search_options(params)
        page = 1
        payload["page"] = page
        url = WorkUaParser.build_resumes_url(payload)
        scraper_api_url = utils.wrap_with_scraper_api(url)

        html_pages = []
        try:
            response = requests.get(scraper_api_url, timeout=60)
            response.raise_for_status()
            html_pages.append(response.text)

            total_candidates = WorkUaParser.get_total_candidates(response.text)
            total_pages = math.ceil(total_candidates / 14)
            logger.info(
                f"Total candidates: {total_candidates}, Total pages: {total_pages} on Work.ua"
            )

            for page in range(2, total_pages + 1, 2):
                payload["page"] = page
                url = self.build_resumes_url(payload)
                scraper_api_url = utils.wrap_with_scraper_api(url)
                response = requests.get(scraper_api_url, timeout=60)
                response.raise_for_status()
                html_pages.append(response.text)

            for page in range(3, total_pages + 1, 2):
                payload["page"] = page
                url = self.build_resumes_url(payload)
                scraper_api_url = utils.wrap_with_scraper_api(url)
                response = requests.get(scraper_api_url, timeout=60)
                response.raise_for_status()
                html_pages.append(response.text)

        except requests.RequestException as e:
            logger.info(f"Error fetching URL {url} on page {page}: {e}")
            raise

        return html_pages

    @staticmethod
    def get_resume_href_from_html(html: str) -> list[str]:
        """
        Parses the HTML content and extracts relevant data from the Work.ua resume section.
        """
        soup = BeautifulSoup(html, "html.parser")
        divs = soup.find_all(
            "div",
            class_=lambda class_name: class_name
            and "card" in class_name
            and "resume-link" in class_name,
        )
        return [
            div.find("a", href=True)["href"] for div in divs if div.find("a", href=True)
        ]

    @staticmethod
    def get_resume_html_from_href(href: str) -> str | None:
        """
        Fetches the HTML content of a resume page from Work.ua using the provided URL.
        """
        url = f"{WorkUaParser.base_url}{href}"
        scraper_api_url = utils.wrap_with_scraper_api(url)

        try:
            response = requests.get(scraper_api_url, timeout=60)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.info(f"Error fetching URL {url}: {e}")
            return None

    @staticmethod
    def parse_resume(link, html: str) -> dict:
        """
        Parses the HTML content of a resume page and extracts relevant details.
        """
        soup = BeautifulSoup(html, "html.parser")
        resume = {"salary_expectation": "", "experience": [], "filling_percentage": 0}

        # Extract salary expectation
        description_meta = soup.find("meta", attrs={"name": "Description"})
        if description_meta:
            description_content = description_meta.get("content", "")
            if "salary starting at" in description_content:
                salary_part = description_content.split("salary starting at")[-1]
                salary = salary_part.split()[0].strip()
                resume["salary expectation"] = salary

        # Extract work experience
        work_experience_header = soup.find("h2", string="Work experience")
        if work_experience_header:
            experience_section = work_experience_header.find_next_siblings(
                "h2", class_="h4"
            )
            for position_tag in experience_section:
                position = position_tag.text.strip()
                details_tag = position_tag.find_next_sibling("p", class_="mb-0")
                if details_tag:
                    duration_tag = details_tag.find("span", class_="text-default-7")
                    duration = (
                        WorkUaParser.format_experience_detail(duration_tag.text)
                        if duration_tag
                        else None
                    )
                    details_text = details_tag.get_text(separator=" ", strip=True)
                    details = WorkUaParser.format_experience_detail(
                        details_text.replace(duration or "", "")
                    )
                    experience = {
                        "position": position,
                        "duration": duration,
                        "details": details,
                    }
                    resume["experience"].append(experience)

        link = WorkUaParser.base_url + link
        resume["href"] = link
        return schemas.Resume(**resume)

    def search_resumes(self, params: schemas.SearchOptions) -> list[dict]:
        """
        Searches resumes on Work.ua by extracting data and formatting it into structured information.
        """
        html_pages = self.get_resume_pages(params)
        resume_data = []
        for html_page in html_pages:
            resume_links = self.get_resume_href_from_html(html_page)
            for link in resume_links:
                resume_html = self.get_resume_html_from_href(link)
                if resume_html:
                    logger.info(f"Processing: {WorkUaParser.base_url + link}")
                    resume_data.append(
                        self.parse_resume(WorkUaParser.base_url + link, resume_html)
                    )
        return resume_data
