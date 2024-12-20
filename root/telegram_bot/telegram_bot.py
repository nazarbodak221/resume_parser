import os
import json
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    filters,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
)

import schemas
from parsers import WorkUaParser
from parsers import RobotaUaParser


logger = logging.getLogger(__name__)


class TelegramBot:
    """
    A Telegram bot for searching resumes on Work.ua and Robota.ua.
    Handles interaction with users to set search parameters and perform searches.
    """

    def __init__(self, work_ua_parser: WorkUaParser, robota_ua_parser: RobotaUaParser):
        """
        Initializes the TelegramBot with parsers for Work.ua and Robota.ua,
        sets up the bot application, and loads salary and experience options from JSON files.
        """
        self.work_ua_parser = work_ua_parser
        self.robota_ua_parser = robota_ua_parser
        self.__application = (
            ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
        )
        self.__user_data = {}
        self.__load_options()

    def __load_options(self) -> None:
        """
        Loads salary and experience options from respective JSON files.
        Logs errors if files cannot be read or parsed.
        """
        self.__load_salary_options()
        self.__load_experience_options()

    def __load_salary_options(self) -> None:
        """
        Loads salary options from the file specified by TELEGRAM_SALARY_JSON_PATH.
        Logs an error if the file is missing or malformed.
        """
        json_file_path = os.getenv("TELEGRAM_SALARY_JSON_PATH")
        try:
            with open(json_file_path, "r") as json_file:
                salary_options = json.load(json_file)
                self.SALARY_FROM_OPTIONS = salary_options.get("SALARY_FROM_OPTIONS", [])
                self.SALARY_TO_OPTIONS = salary_options.get("SALARY_TO_OPTIONS", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Failed to load salary options from {json_file_path}: {e}")

    def __load_experience_options(self) -> None:
        """
        Loads experience options from the file specified by TELEGRAM_EXPERIENCE_JSON_PATH.
        Logs an error if the file is missing or malformed.
        """
        json_file_path = os.getenv("TELEGRAM_EXPERIENCE_JSON_PATH")
        try:
            with open(json_file_path, "r") as json_file:
                experience_options = json.load(json_file)
                self.EXPERIENCE_OPTIONS = experience_options
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Failed to load experience options from {json_file_path}: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Starts interaction with the user, welcoming them and providing a menu of available commands.
        """
        chat_id = update.effective_chat.id
        self.__user_data[chat_id] = {
            "state": schemas.UserState.FREE,
            "search_options": {
                "search": "",
                "region": "",
                "salary_from": 0,
                "salary_to": 0,
                "experience": [],
            },
        }

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Hello! I'm a bot that can find resumes based on the parameters you provide.\n"
                "Choose your option:\n"
                "/keywords - search query\n"
                "/region - region\n"
                "/salary - salary range\n"
                "/experience - required experience\n"
                "/search - start searching\n"
                "/clear - clear all parameters"
            ),
        )

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Stops the bot interaction for the current user and clears their data.
        """
        chat_id = update.effective_chat.id
        self.__user_data.pop(chat_id, None)

        await context.bot.send_message(
            chat_id=chat_id, text="Goodbye! Hope I was helpful."
        )

    async def clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Clears the user's search parameters and restores them to default values.
        """
        chat_id = update.effective_chat.id
        self.__user_data[chat_id] = {
            "state": schemas.UserState.FREE,
            "search_options": {
                "search": "",
                "region": "",
                "salary_from": "",
                "salary_to": "",
                "experience": [],
            },
        }
        await context.bot.send_message(
            chat_id=chat_id,
            text="All parameters cleared. You can now provide new parameters.",
        )

    async def set_parameter(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handles setting a user parameter (keywords, region).
        Asks the user for the specific parameter and updates the user's state.
        """
        chat_id = update.effective_chat.id
        text = update.message.text

        if text.startswith("/keywords"):
            await context.bot.send_message(
                chat_id=chat_id, text="Please provide your search query."
            )
            self.__user_data[chat_id]["state"] = schemas.UserState.ASKING_KEYWORDS

        elif text.startswith("/region"):
            await context.bot.send_message(
                chat_id=chat_id, text="Please provide your desired region."
            )
            self.__user_data[chat_id]["state"] = schemas.UserState.ASKING_REGION

    async def accept_parameter(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Accepts a parameter provided by the user and updates their search options.
        """
        chat_id = update.effective_chat.id
        text = update.message.text

        if not self.__user_data.get(chat_id):
            await context.bot.send_message(
                chat_id=chat_id, text="Please type /start to make a request."
            )
            return

        if self.__user_data[chat_id]["state"] == schemas.UserState.FREE:
            await context.bot.send_message(
                chat_id=chat_id,
                text="It seems you're not choosing any parameter, type one of the following commands: "
                "/keywords, /region, /salary, /experience, /search, /clear",
            )
        elif self.__user_data[chat_id]["state"] == schemas.UserState.ASKING_KEYWORDS:
            self.__user_data[chat_id]["search_options"]["search"] = text
            await context.bot.send_message(
                chat_id=chat_id, text=f"Search query set to: {text}"
            )

        elif self.__user_data[chat_id]["state"] == schemas.UserState.ASKING_REGION:
            self.__user_data[chat_id]["search_options"]["region"] = text
            await context.bot.send_message(
                chat_id=chat_id, text=f"Region set to: {text}"
            )

        self.__user_data[chat_id]["state"] = schemas.UserState.FREE

    def __get_experience_mapping(self) -> dict:
        """
        Maps the experience labels to their corresponding keys.
        """
        return {label: key for key, label in self.EXPERIENCE_OPTIONS.items()}

    def __build_experience_keyboard(
        self, selected_experience: list
    ) -> InlineKeyboardMarkup:
        """
        Builds an inline keyboard for selecting experience levels.
        """
        experience_mapping = self.__get_experience_mapping()

        keyboard = [
            [
                InlineKeyboardButton(
                    f"✅ {label}" if label in selected_experience else label,
                    callback_data=key,
                )
                for key, label in experience_mapping.items()
            ]
        ]

        keyboard.extend(
            [
                [
                    InlineKeyboardButton("🔄 Reset", callback_data="experience_reset"),
                    InlineKeyboardButton(
                        "✔️ Complete", callback_data="experience_complete"
                    ),
                ],
            ]
        )
        return InlineKeyboardMarkup(keyboard)

    async def experience(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handles the user request to set the experience level parameter.
        """
        chat_id = update.effective_chat.id
        experience = self.__user_data[chat_id]["search_options"]["experience"]

        reply_markup = self.__build_experience_keyboard(experience)

        self.__user_data[chat_id]["state"] = schemas.UserState.ASKING_EXPERIENCE

        await context.bot.send_message(
            chat_id=chat_id,
            text="Please choose your experience levels (you can select multiple):",
            reply_markup=reply_markup,
        )

    async def experience_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handles the callback for selecting or deselecting experience options in the user's search query.
        """
        query = update.callback_query
        await query.answer()

        chat_id = query.message.chat_id
        user_data = self.__user_data[chat_id]
        selected_experience = user_data["search_options"].get("experience", [])

        experience_mapping = self.__get_experience_mapping()
        action = query.data

        if action == "experience_complete":
            selected_text = (
                ", ".join(selected_experience) if selected_experience else "None"
            )
            user_data["state"] = schemas.UserState.FREE
            await query.edit_message_text(
                text=f"Experience selection completed: {selected_text}."
            )

        elif action == "experience_reset":
            user_data["search_options"]["experience"] = []
            await query.edit_message_text(
                text="Experience options have been reset. Please select again.",
                reply_markup=self.__build_experience_keyboard(selected_experience),
            )

        else:
            selected_option = experience_mapping[action]
            if selected_option in selected_experience:
                selected_experience.remove(selected_option)
            else:
                selected_experience.append(selected_option)

            await query.edit_message_text(
                text=f"Experience options selected: {', '.join(selected_experience) if selected_experience else 'None'}\n"
                "You can toggle options, reset, or complete your selection.",
                reply_markup=self.__build_experience_keyboard(selected_experience),
            )

    async def search_resumes(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Searches resumes based on the user's parameters (keywords, region, salary, experience).
        Combines results from multiple job websites (Work.ua, Robota.ua), sorts them, and sends
        the top 5 resumes to the user.
        """
        chat_id = update.effective_chat.id
        search_options = self.__user_data[chat_id]["search_options"]

        if "search" not in search_options:
            await context.bot.send_message(
                chat_id=chat_id, text="Please provide at least keywords."
            )
            return

        search_options = schemas.SearchOptions(**search_options)

        # Fetch resumes from both sources
        work_ua_results = self.work_ua_parser.search_resumes(search_options.copy())
        robota_ua_results = self.robota_ua_parser.search_resumes(search_options.copy())

        # Combine and sort results
        combined_results = sorted(work_ua_results + robota_ua_results, reverse=True)
        top_resumes = combined_results[:5]

        # Send the top 5 resumes
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Found {len(combined_results)} resumes\n"
            f"You can see top 5 below:\n"
            f"{'\n'.join([TelegramBot.format_resume(resume) for resume in top_resumes])}",
        )

    async def salary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Initiates the salary parameter selection by sending an inline keyboard with salary options.
        The user is asked to select the minimum salary.

        Args:
            update (Update): The incoming update containing information about the message.
            context (ContextTypes.DEFAULT_TYPE): The context for the bot interaction.
        """
        chat_id = update.effective_chat.id
        self.__user_data[chat_id]["state"] = schemas.UserState.ASKING_SALARY_FROM

        keyboard = [
            [InlineKeyboardButton(label, callback_data=f"salary_from:{value}")]
            for label, value in self.SALARY_FROM_OPTIONS.items()
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text="Select the minimum salary:",
            reply_markup=reply_markup,
        )

    async def salary_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handles the callback for selecting the minimum or maximum salary in the user's search query.
        The user selects either the minimum or maximum salary, and the bot updates the salary parameters.

        Args:
            update (Update): The incoming callback query containing information about the user's choice.
            context (ContextTypes.DEFAULT_TYPE): The context for the bot interaction.
        """
        query = update.callback_query
        await query.answer()

        chat_id = query.message.chat_id
        data = query.data

        if data.startswith("salary_from:"):
            self.__user_data[chat_id]["search_options"]["salary_from"] = int(
                data.split(":")[1]
            )
            self.__user_data[chat_id]["state"] = schemas.UserState.ASKING_SALARY_TO

            keyboard = [
                [InlineKeyboardButton(label, callback_data=f"salary_to:{value}")]
                for label, value in self.SALARY_TO_OPTIONS.items()
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text="Select the maximum salary:", reply_markup=reply_markup
            )

        elif data.startswith("salary_to:"):
            self.__user_data[chat_id]["search_options"]["salary_to"] = int(
                data.split(":")[1]
            )
            self.__user_data[chat_id]["state"] = schemas.UserState.FREE

            await query.edit_message_text(text="Salary range set successfully.")

    @staticmethod
    def format_resume(resume: schemas.Resume) -> str:
        """
        Formats a resume object into a human-readable string.
        """
        formatted_resume = f"Resume: {resume.href}\n"

        if resume.salary_expectation:
            formatted_resume += f"Salary expectation: {resume.salary_expectation}\n"

        if resume.experience:
            formatted_resume += "Experience/Education:\n"
            for exp in resume.experience:
                formatted_resume += f"    Position: {exp.position or 'N/A'}\n"
                formatted_resume += f"    Duration: {exp.duration or 'N/A'}\n"
                formatted_resume += f"    Details: {exp.details or 'N/A'}\n\n"

        formatted_resume += f"Resume filling percentage: {resume.filling_percentage}%\n"

        return formatted_resume

    def __add_handlers(self):
        start_handler = CommandHandler("start", self.start)
        stop_handler = CommandHandler("stop", self.stop)
        clear_handler = CommandHandler("clear", self.clear)
        set_param_handler = CommandHandler(["keywords", "region"], self.set_parameter)

        experience_handler = CommandHandler("experience", self.experience)
        experience_callback_handler = CallbackQueryHandler(
            self.experience_callback, pattern="^experience_"
        )

        salary_handler = CommandHandler("salary", self.salary)
        salary_callback_handler = CallbackQueryHandler(
            self.salary_callback, pattern="^salary_(from|to):"
        )

        search_handler = CommandHandler("search", self.search_resumes)
        accept_parameter_handler = MessageHandler(
            filters.TEXT & (~filters.COMMAND), self.accept_parameter
        )

        handlers = [
            start_handler,
            stop_handler,
            clear_handler,
            set_param_handler,
            experience_handler,
            experience_callback_handler,
            salary_handler,
            salary_callback_handler,
            search_handler,
            accept_parameter_handler,
        ]

        for handler in handlers:
            self.__application.add_handler(handler)

    def run(self):
        """
        Starts the bot and sets up all the necessary command and callback handlers for user interactions.
        """
        self.__add_handlers()
        self.__application.run_polling()
