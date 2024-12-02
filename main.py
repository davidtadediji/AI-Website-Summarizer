import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "week1")))
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from openai import OpenAI
import ollama

import validators
from logger import configured_logger

import tkinter as tk
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from rich.console import Console
from rich.markdown import Markdown
from abc import ABC, abstractmethod

load_dotenv()


class Website:
    def __init__(self, url):
        """
        Create this Website object from the given url using the BeautifulSoup library
        """
        if not validate_url(url):
            raise ValueError("Invalid URL format")

        self.url = url

        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.content, "html.parser")
            self.title = soup.title.string if soup.title else "No title found"
            for irrelevant in soup.body(["script", "style", "img", "input"]):
                irrelevant.decompose()
            self.text = soup.body.get_text(separator="\n", strip=True)
        except Exception as e:
            raise RuntimeError(
                f"Error occurred while accessing/parsing url with bs4 --> {str(e)}"
            )


class SummarizationModel(ABC):

    @abstractmethod
    def generate_summary(self, model, website: Website):
        pass


class OllamaSummarizationModel(SummarizationModel):

    def generate_summary(self, model, website: Website):
        try:
            response = ollama.chat(model=model, messages=messages_for(website))
            return response["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"API call to OpenAI model failed --> {str(e)}")


class OpenAISummarizationModel(SummarizationModel):

    def __init__(self):
        self.openai = initialize_openai()

    def generate_summary(self, model, website: Website):
        try:
            response = openai_instance.chat.completions.create(
                model=model, messages=messages_for(website)
            )
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
            else:
                raise RuntimeError(
                    "API response did not contain a valid 'choices' field or it is empty."
                )
        except Exception as e:
            raise RuntimeError(f"API call to OpenAI model failed --> {str(e)}")


def summarization_model_factory(model_type: str) -> SummarizationModel:
    if model_type == "openai":
        return OpenAISummarizationModel()
    elif model_type == "ollama":
        return OllamaSummarizationModel()
    else:
        raise ValueError(f"Unknown model type {model_type}")


def log_display_summary(func):
    """
    Decorator to log API key validation process
    """

    def wrapper(*args, **kwargs):
        try:
            configured_logger.info("Attempting to display summary of website")
            result = func(*args, **kwargs)
            configured_logger.info("Successfully displayed summary for website")
            return result
        except Exception as e:
            # The file number and line number is traced to where the logger's error method is called
            configured_logger.error(
                f"Failed to generate & display summary --> {str(e)}"
            )

    return wrapper


def validate_api_key(api_key):
    """
    Validates the API key for proper format and authenticity.
    Returns None if valid, raises ValueError with specific error message if invalid.
    """
    if not api_key:
        raise ValueError(
            "No API key was found - please head over to the troubleshooting notebook."
        )

    if " " in api_key or "\t" in api_key:
        raise ValueError(
            "API key contains spaces or tab characters. Please check your key format."
        )

    return True  # If no exceptions, the API key is valid


def initialize_openai():
    """
    Initializes the OpenAI object with proper error handling for API key validation.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        validate_api_key(api_key)  # Validate the API key

        if not api_key.startswith("sk-proj"):
            configured_logger.warning(
                "An API key was found, but it doesn't start with 'sk-proj-'; please check you're using the correct key."
            )
        else:
            configured_logger.info("API key found and does not violate any standards!")

        # If the API key is valid, proceed to initialize OpenAI with the valid key
        return OpenAI(api_key=api_key)

    except ValueError as e:
        raise ValueError(f"Error occurred while validating API key --> {str(e)}")

    except Exception as e:
        raise RuntimeError(
            f"Unexpected error occurred during OpenAI initialization --> {str(e)}"
        )


def validate_url(url):
    """Validate URL format."""
    try:
        return validators.url(url)
    except:
        raise RuntimeError(f"Failed to validate website url --> {str(e)}")


system_prompt = "You are an assistant that analyzes the contents of a website \
and provides a short summary, ignoring text that might be navigation related. \
Respond in markdown."


def user_prompt_for(website):
    user_prompt = f"You are looking at a website titled {website.title}"
    user_prompt += (
        "\nThe contents of this website is as follows; \please provide a short summary of this website in"
        " markdown. If it includes news or announcements, then summarize these too.\n\n"
    )
    user_prompt += website.text
    return user_prompt


def messages_for(website):
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt_for(website)},
    ]


class Display(ABC):
    @abstractmethod
    def handle_result(self, summary: str):
        pass


class RichConsoleStrategy(Display):
    def handle_result(self, summary):
        console = Console()
        content = Markdown(summary)
        console.print(content)


class WriteToFileStrategy(Display):
    def __init__(self, file_path: str):
        """
        Initialize with a file path for storing the summary.
        """
        self.file_path = file_path

    def handle_result(self, summary):
        try:
            with open("week1/summary.md", "w") as f:
                f.write(summary)
            configured_logger.info("Summary written to week1/summary.md")
        except Exception as e:
            raise RuntimeError(
                f"Failed to write summary to file {self.file_path} --> {str(e)}"
            )


class PrintToConsoleStrategy(Display):
    def handle_result(self, summary):
        print(summary)


class DisplayInGUIWindowStrategy(Display):
    def handle_result(self, summary):
        try:
            window = tk.Tk()
            window.title("Summary Report")
            label = tk.Label(window, text=summary, padx=20, pady=20)
            label.pack()
            window.mainloop()
        except Exception as e:
            raise RuntimeError(f"Failed to display summary in GUI window --> {str(e)}")


class SendToEmailStrategy(Display):
    def __init__(
        self,
        recipient_email: str = "davidtadediji@gmail.com",
        sender_email: str = "davidadey000@gmail.com",
        smtp_server: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ):
        self.recipient_email = recipient_email
        self.sender_email = sender_email
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def handle_result(self, summary):
        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = self.recipient_email
            msg["Subject"] = "Summary Report"

            msg.attach(MIMEText(summary, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                # Start TLS (Transport Layer Security) to secure the connection
                server.starttls()

                # Login to the server with the sender's email and password
                server.login(
                    self.sender_email, "<Your_Email_Password>"
                )  # Replace with the correct password or app-specific password

                # Send the email
                server.sendmail(
                    self.sender_email, self.recipient_email, msg.as_string()
                )

            print(f"Summary sent to {self.recipient_email}")
        except Exception as e:
            raise RuntimeError(f"Failed to send summary email: {str(e)}")


@log_display_summary
def display_summary(url, model_type, model_name, strategy: Display = None):
    website = Website(url)
    summarization_model = summarization_model_factory(model_type)
    summary = summarization_model.generate_summary(model_name, website)
    if strategy:
        strategy.handle_result(summary)
    else:
        PrintToConsoleStrategy().handle_result(summary)


console_strategy = RichConsoleStrategy()
file_strategy = WriteToFileStrategy(file_path="week1/summary.md")
raw_print_strategy = PrintToConsoleStrategy()
gui_window_strategy = DisplayInGUIWindowStrategy()
mail_strategy = SendToEmailStrategy("recipient@gmail.com", "sender@gmail.com")

display_summary("https://edwarddonner.com", "ollama","llama3.2", console_strategy)
