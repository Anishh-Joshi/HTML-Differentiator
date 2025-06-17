import os
import requests
import time
from typing import Optional


class ChangeSummarizer:
    def __init__(self, logger, openai_client=None):
        """
        Initialize the summarizer with logger and optional OpenAI client.
        
        Args:
            logger: Logger instance for logging
            openai_client: Optional OpenAI client instance
        """
        self.logger = logger
        self.openai_client = openai_client
        self.api_preference = os.environ.get("GPT", "DEEPSEEK").upper()
        
        if self.api_preference == "DEEPSEEK":
            self.api_key = os.environ.get("API_DEEP_SEEK_KEY")
            if not self.api_key:
                self.logger.warning("DeepSeek API key not found, falling back to OpenAI")
                self.api_preference = "OPENAI"
                if not self.openai_client:
                    raise ValueError("Neither DeepSeek API key nor OpenAI client available")
        elif self.api_preference == "OPENAI":
            if not self.openai_client:
                raise ValueError("OpenAI client not provided but OPENAI is selected")

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
        
        return self._call_api_with_fallback(prompt, "translation")

    def summarize_changes(self, diff_text: str) -> str:
        """
        Generate summary of changes focusing only on textual content differences.
        """
        prompt = (
            "Summarize only the differences in the actual textual content (Immigration Related issues only), "
            "ignoring any changes in HTML structure, tags, divs, spans, classes, ids, styles, or UI components. "
            "Only focus on changes in visible text that a user would read on the webpage. "
            "Do not mention modifications to code, formatting, or layout. Present the summary in bullet points:\n\n"
            f"{diff_text}"
        )
        
        return self._call_api_with_fallback(prompt, "summary")

    def _call_api_with_fallback(self, prompt: str, operation: str, max_retries: int = 2) -> str:
        """
        Try DeepSeek first, fall back to OpenAI if fails, with retries for DeepSeek.
        """
        original_preference = self.api_preference
        
        for attempt in range(max_retries + 1):
            try:
                return self._call_api(prompt, operation)
            except Exception as e:
                if attempt < max_retries and self.api_preference == "DEEPSEEK":
                    wait_time = (attempt + 1) * 5  # Exponential backoff would be better
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed for DeepSeek {operation}. "
                        f"Retrying in {wait_time} seconds... Error: {str(e)}"
                    )
                    time.sleep(wait_time)
                    continue
                
                if self.api_preference == "DEEPSEEK" and self.openai_client:
                    self.logger.warning(
                        f"DeepSeek {operation} failed, falling back to OpenAI. Error: {str(e)}"
                    )
                    self.api_preference = "OPENAI"
                    try:
                        return self._call_api(prompt, operation)
                    finally:
                        self.api_preference = original_preference
                raise

    def _call_api(self, prompt: str, operation: str) -> str:
        """
        Internal method to call the appropriate API.
        """
        try:
            if self.api_preference == "DEEPSEEK":
                self.logger.info(f"Requesting {operation} from DeepSeek API...")
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                }
                
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=15  # Reduced timeout from 30 to 15 seconds
                )
                response.raise_for_status()
                result = response.json()
                content = result['choices'][0]['message']['content']
                
            else:  # OpenAI
                self.logger.info(f"Requesting {operation} from OpenAI...")
                completion = self.openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    timeout=15  # Added timeout for OpenAI
                )
                content = completion.choices[0].message.content
                
            self.logger.info(f"Successfully completed {operation}")
            return content
            
        except requests.exceptions.Timeout:
            self.logger.error(f"API timeout during {operation}")
            raise Exception(f"API request timed out during {operation}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed during {operation}: {str(e)}")
            raise Exception(f"API request failed during {operation}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error during {operation}: {str(e)}")
            raise

