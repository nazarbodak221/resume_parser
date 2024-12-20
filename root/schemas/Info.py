from enum import Enum
from typing import Optional
from pydantic import BaseModel


class Experience(BaseModel):
    position: Optional[str]
    duration: Optional[str]
    details: Optional[str]


class Resume(BaseModel):
    href: str
    salary_expectation: Optional[str]
    experience: Optional[list[Experience]]
    filling_percentage: int

    def __lt__(self, other):
        return self.filling_percentage < other.filling_percentage


class SearchOptions(BaseModel):
    search: str
    region: Optional[str]
    salary_from: Optional[int]
    salary_to: Optional[int]
    experience: Optional[list[str]]


class UserState(str, Enum):
    ASKING_KEYWORDS = "asking_keywords"
    ASKING_REGION = "asking_region"
    ASKING_SALARY = "asking_salary"
    ASKING_EXPERIENCE = "asking_experience"
    ASKING_SALARY_FROM = "asking_salary_from"
    ASKING_SALARY_TO = "asking_salary_to"
    FREE = "free"
