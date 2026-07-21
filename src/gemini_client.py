"""
Gemini API client with model failover and exponential backoff.

Tries multiple Gemini models in order, with retries and a per-attempt
timeout, to handle enterprise rate limits and transient failures.
"""

import concurrent.futures
import logging
import re
import time

from google import genai
from google.genai import types

from .models import ReviewReport

logger = logging.getLogger(__name__)

# Models to try in priority order
FAILOVER_MODELS = ['gemini-3.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash']

# Maximum retries per model
MAX_RETRIES = 3

# Timeout per individual API call (seconds)
API_TIMEOUT_SECONDS = 180

# Initial backoff delay (doubles on each retry)
INITIAL_BACKOFF_SECONDS = 15


def call_gemini_with_failover(
    client: genai.Client, prompt: str
) -> ReviewReport:
    """
    Send the review prompt to Gemini, trying multiple models with retries.

    Uses structured JSON output mode with the ReviewReport schema.
    Each attempt has a 180-second timeout enforced via a thread pool.

    Args:
        client: An initialized google.genai Client.
        prompt: The fully assembled review prompt.

    Returns:
        A parsed ReviewReport from the LLM.

    Raises:
        RuntimeError: If all models and retries are exhausted.
    """
    safety_settings = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ReviewReport,
        max_output_tokens=8192,
        safety_settings=safety_settings,
    )

    for model_name in FAILOVER_MODELS:
        retry_delay = INITIAL_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Sending diff to Gemini ({model_name}) for structured analysis "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})..."
                )
                # Executor is reused across retries for the same model
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    response = future.result(timeout=API_TIMEOUT_SECONDS)


                if not response.parsed:
                    error_msg = "Structured JSON parsing failed (likely truncated)."
                    if hasattr(response, 'text') and response.text:
                        # Log the first 200 chars and last 200 chars to help debug truncation
                        text = response.text
                        snippet = text if len(text) < 400 else f"{text[:200]}...{text[-200:]}"
                        error_msg += f" Raw response: {snippet}"
                    raise ValueError(error_msg)

                report: ReviewReport = response.parsed
                logger.info(
                    f"Received review from Gemini ({model_name}) "
                    f"with {len(report.issues)} issues."
                )
                return report

            except Exception as e:
                error_str = str(e)
                logger.warning(f"Request to {model_name} failed: {error_str}")
                if attempt < MAX_RETRIES - 1:
                    match = re.search(r'Please retry in ([0-9.]+)s', error_str)
                    if match:
                        requested_delay = float(match.group(1))
                        # Use the requested delay (plus a tiny buffer) if it's larger than our backoff
                        sleep_time = max(retry_delay, requested_delay + 1.0)
                    else:
                        sleep_time = retry_delay
                        
                    logger.info(f"Waiting {sleep_time:.2f} seconds before retry...")
                    time.sleep(sleep_time)
                    retry_delay *= 2

    raise RuntimeError(
        "Failed to generate review after trying all fallback models: "
        + ", ".join(FAILOVER_MODELS)
    )
