import os
import json
import logging

import requests

import schemas
import utils


logger = logging.getLogger(__name__)


class RobotaUaParser:
    """
    A parser for interacting with the Robota.ua website to search resumes and handle related data.
    """

    base_url = "https://robota.ua"

    def __init__(self):
        """
        Initializes the RobotaUaParser by logging in, setting headers, and loading regions and experience options.
        """
        self.__login()
        self.__set_headers()
        self.__load_regions()
        self.__load_experience_options()

    def __load_regions(self) -> None:
        """
        Loads the region data either from a JSON file or from a remote URL if the file is unavailable.
        If fetched from the URL, the data is saved to the JSON file for future use.
        """
        region_file_path = os.getenv("ROBOTA_UA_REGIONS_JSON_PATH")

        try:
            with open(region_file_path, "r") as region_file:
                region_data = json.load(region_file)
                self.REGIONS = region_data
                return
        except (FileNotFoundError, json.JSONDecodeError) as error:
            logger.info(
                f"Failed to load regions from file: {error}. Fetching from URL..."
            )

        regions_url = os.getenv("ROBOTA_UA_REGIONS_URL")
        response = requests.get(regions_url)

        if response.status_code != 200:
            raise Exception("Failed to fetch regions from Robota.ua")

        fetched_data = response.json()
        region_data = {city["en"]: city["id"] for city in fetched_data}

        with open(region_file_path, "w") as region_file:
            json.dump(region_data, region_file, indent=4)
            logger.info(f"Regions fetched and saved to {region_file_path}.")

        self.REGIONS = region_data
        return

    def __load_experience_options(self) -> None:
        """
        Loads the experience options data from a JSON file. If the file doesn't exist or is invalid,
        the method logs the error and does nothing.
        """
        experience_file_path = os.getenv("ROBOTA_UA_EXPERIENCE_JSON_PATH")

        try:
            with open(experience_file_path, "r") as experience_file:
                experience_data = json.load(experience_file)
                self.EXPERIENCE_OPTIONS = experience_data
                return
        except (FileNotFoundError, json.JSONDecodeError) as error:
            logger.info(f"Failed to load experience options from file: {error}.")
            return

    def __login(self) -> None:
        """
        Logs in to the Robota.ua website and retrieves a token for authentication.
        """
        login_url = os.getenv("ROBOTA_UA_LOGIN_URL")

        user_name = os.getenv("ROBOTA_UA_USERNAME")
        pass_word = os.getenv("ROBOTA_UA_PASSWORD")

        login_payload = {"username": user_name, "password": pass_word}

        response = requests.post(login_url, json=login_payload)

        if response.status_code == 200:
            self.__token = response.json()
        else:
            raise Exception("Failed to login to Robota.ua")

    def __set_headers(self) -> None:
        """
        Sets the HTTP headers required for making authenticated requests.
        """
        request_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.__token}",
        }

        self.__headers = request_headers

    @staticmethod
    def format_salary_expectation(salary_str: str) -> str:
        """
        Formats the salary expectation by stripping extra spaces and replacing non-breaking spaces.
        """
        return salary_str.strip().replace("\xa0", " ")

    @staticmethod
    def unpack_resume_from_response(resume_data: schemas.Resume) -> dict:
        """
        Unpacks a resume from the response into a structured dictionary.
        """
        resume_info = {
            "href": f"{RobotaUaParser.base_url}/candidates/{resume_data['resumeId']}",
            "salary_expectation": RobotaUaParser.format_salary_expectation(
                resume_data["salary"]
            ),
            "experience": [
                {
                    "position": exp["position"],
                    "duration": exp["datesDiff"],
                    "details": exp["company"],
                }
                for exp in resume_data["experience"]
            ],
            "filling_percentage": resume_data["fillingPercentage"],
        }

        return resume_info

    def __unpack_search_options(self, search_params: schemas.SearchOptions) -> dict:
        """
        Prepares the search payload based on the user's search options.
        """
        region_name = utils.get_most_similar_word(
            search_params.region, self.REGIONS.keys()
        )
        region_id = self.REGIONS[region_name] if region_name else None

        search_payload = {
            "cityId": region_id,
            "keyWords": search_params.search,
            "salary": {
                "from": search_params.salary_from,
                "to": search_params.salary_to,
            },
            "experienceIds": [
                self.EXPERIENCE_OPTIONS.get(exp)
                for exp in search_params.experience
                if self.EXPERIENCE_OPTIONS.get(exp)
            ],
        }

        if "More than 5 years" in search_params.experience:
            search_payload["experienceIds"].append(
                self.EXPERIENCE_OPTIONS["5 to 10 years"]
            )
            search_payload["experienceIds"].append(
                self.EXPERIENCE_OPTIONS["More than 10 years"]
            )

        return search_payload

    def search_resumes(
        self, search_params: schemas.SearchOptions = None
    ) -> list[schemas.Resume]:
        """
        Searches for resumes on Robota.ua based on the provided search options.
        """
        resumes_url = os.getenv("ROBOTA_UA_RESUMES_URL")

        request_headers = self.__headers
        search_payload = self.__unpack_search_options(search_params)

        response = requests.post(
            resumes_url, json=search_payload, headers=request_headers
        )

        total_resumes = response.json()["total"]
        logger.info(f"Found {total_resumes} resumes on Robota.ua")

        search_payload["count"] = total_resumes
        response = requests.post(
            resumes_url, json=search_payload, headers=request_headers
        )

        resumes_list = []
        if response.status_code == 200:
            response_data = response.json()

            for resume in response_data["documents"]:
                resume_info = RobotaUaParser.unpack_resume_from_response(resume)
                resumes_list.append(schemas.Resume(**resume_info))

            return resumes_list

        else:
            logger.info(
                f"Request failed with status code {response.status_code}: {response.text}"
            )
            response.raise_for_status()
