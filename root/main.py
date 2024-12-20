import logging

import nltk
from dotenv import load_dotenv

load_dotenv()

from parsers import WorkUaParser, RobotaUaParser
from telegram_bot import TelegramBot

nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("stopwords")

work_ua_parser = WorkUaParser()
robota_ua_parser = RobotaUaParser()

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = logging.INFO
logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)

if __name__ == "__main__":
    bot = TelegramBot(work_ua_parser, robota_ua_parser)
    bot.run()
