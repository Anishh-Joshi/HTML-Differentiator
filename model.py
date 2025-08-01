import time
from typing import Optional


class ChangeSummarizer:
    def __init__(self, logger, openai_client):
        """
        Initialize the summarizer with logger and OpenAI client.
        
        Args:
            logger: Logger instance for logging
            openai_client: OpenAI client instance (required)
        """
        self.logger = logger
        self.openai_client = openai_client

    def translate_text(self, text: str, target_language: str = "Chinese") -> str:
        """
        Translate text to target language while preserving formatting.
        """
        prompt = (
            f"Translate the following text to {target_language} while strictly preserving "
            "all original formatting including line breaks, spacing, punctuation, and special characters. "
            "Do not modify or rearrange the structure - only translate the textual content:\n\n"
            f"{text}"
        )
        return self._call_openai(prompt, "translation")

    def summarize_changes(self, diff_text: str) -> str:
        """
        Generate summary of changes focusing only on textual content differences.
        """
        prompt = (
            "You are an expert content analyst. Given the HTML content below, identify and summarize the top 5 visible textual updates "
            "that would be meaningful to a user reading the webpage. Ignore structural or formatting changes such as HTML tags, classes, or styles. "
            "Present the summary as bullet points starting with '-'. Here's the content:\n\n"
            f"{diff_text}"
        )
        return self._call_openai(prompt, "summary")

    def _call_openai(self, prompt: str, operation: str) -> str:
        """
        Call OpenAI API.
        """
        try:
            self.logger.info(f"Requesting {operation} from OpenAI...")
            completion = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                timeout=15
            )
            content = completion.choices[0].message.content
            self.logger.info(f"Successfully completed {operation}")
            return content
        except Exception as e:
            self.logger.error(f"OpenAI API failed during {operation}: {str(e)}")
            raise
