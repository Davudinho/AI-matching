"""
backend/app/services/gemini_service.py — Gemini AI Service

This is the CORE AI component. It wraps the Google Gen AI Python SDK
(the new `google-genai` package, which replaced the deprecated `google-generativeai`)
and provides two main capabilities:

1. generate_json()  — Send text to Gemini Flash and get structured JSON back.
   Used for: extracting fields from JDs/CVs, generating explanations.

2. embed_texts()    — Convert text into a 3072-dimensional vector (embedding).
   Used for: semantic similarity search between JDs and CVs.

Why a service class?
- Centralises all Gemini logic in one place
- Easy to swap to a different model or provider later
- Handles retries, errors, and rate limiting consistently

SDK docs: https://googleapis.github.io/python-genai/
"""

import json
import logging
import time
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

try:
    from app.core.config import settings  # when running inside backend/
except ModuleNotFoundError:
    from backend.app.core.config import settings  # when running from project root

logger = logging.getLogger(__name__)

# ---- Import the new google-genai SDK ----
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    logger.warning("google-genai package not installed. Run: pip install google-genai")
    _GENAI_AVAILABLE = False


def _create_client():
    """
    Create and return a configured Gemini client.
    Returns None if the API key is not set or SDK not available.
    """
    if not _GENAI_AVAILABLE:
        return None
    if not settings.GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/app/apikey"
        )
        return None
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    logger.info(f"Gemini client created — model: {settings.GEMINI_MODEL}")
    return client


class GeminiService:
    """
    Wrapper around the Google Gen AI SDK (google-genai).

    All AI calls in this project go through this class.
    """

    def __init__(self):
        self.model_name = settings.GEMINI_MODEL
        self.embedding_model = settings.GEMINI_EMBEDDING_MODEL
        self._client = None

    def _get_client(self):
        """Lazily initialise the client (only when first needed)."""
        if self._client is None:
            self._client = _create_client()
        return self._client

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        temperature: float = 0.0,
    ) -> Optional[dict]:
        """
        Send a prompt to Gemini and parse the JSON response.

        Args:
            prompt: The user message (e.g. the JD text + extraction instructions)
            system_instruction: Optional system-level instructions for the model
            temperature: 0.0 for deterministic extraction, 0.3+ for creative text

        Returns:
            Parsed Python dict, or None if the call fails.

        Example:
            result = gemini.generate_json(
                prompt="Extract fields from this JD: ...",
                system_instruction="You are an expert HR analyst..."
            )
            print(result["title"])  # -> "Delivery Manager"
        """
        client = self._get_client()
        if not client:
            logger.error("Gemini not configured. Set GEMINI_API_KEY in .env")
            return None

        try:
            logger.debug(f"Sending {len(prompt)} chars to Gemini ({self.model_name})...")

            # Build config with JSON response type
            config = genai_types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                system_instruction=system_instruction if system_instruction else None,
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            raw_text = response.text.strip()

            # Strip markdown code fences if model wraps JSON in ```json ... ```
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                if len(parts) >= 2:
                    raw_text = parts[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            parsed = json.loads(raw_text)
            logger.debug("Gemini JSON response parsed successfully")
            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error from Gemini response: {e}")
            raw_snippet = raw_text[:300] if "raw_text" in dir() else "N/A"
            logger.error(f"Raw response snippet: {raw_snippet}")
            return None
        except Exception as e:
            error_str = str(e).lower()
            if "quota" in error_str or "rate" in error_str or "429" in error_str:
                logger.warning(f"Rate limit hit: {e}. Retrying...")
                raise  # Let tenacity retry
            logger.error(f"Gemini generation error: {e}")
            raise

    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
        """
        Convert a single text into a 3072-dimensional embedding vector.

        Args:
            text: The text to embed (JD or CV content)
            task_type:
                - "RETRIEVAL_DOCUMENT" for documents being indexed (JDs/CVs)
                - "RETRIEVAL_QUERY" for search queries

        Returns:
            List of 3072 floats, or empty list on failure.

        What is an embedding vector?
        Think of it as GPS coordinates for meaning. Similar texts have
        coordinates that are close together. "Software Engineer" and
        "Python Developer" will have very close coordinates, while
        "Software Engineer" and "Pastry Chef" will be far apart.
        """
        client = self._get_client()
        if not client:
            return []
        if not text or not text.strip():
            logger.warning("embed_text: empty text provided")
            return []

        try:
            text_to_embed = text[:20000] if len(text) > 20000 else text

            result = client.models.embed_content(
                model=self.embedding_model,
                contents=text_to_embed,
                config=genai_types.EmbedContentConfig(task_type=task_type),
            )
            embedding = result.embeddings[0].values
            logger.debug(f"Embedded {len(text_to_embed)} chars -> {len(embedding)}-dim vector")
            return list(embedding)

        except Exception as e:
            logger.error(f"embed_text error: {e}")
            return []

    def embed_texts_batch(
        self,
        texts: list,
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 20,
    ) -> list:
        """
        Embed multiple texts efficiently, in batches.

        Why batch? The Gemini API charges per call. Batching reduces the
        number of API calls and also speeds up processing significantly.

        Args:
            texts: List of texts to embed
            task_type: As per embed_text()
            batch_size: How many texts to send per API call

        Returns:
            List of embeddings in the same order as input texts.
            Failed embeddings are returned as empty lists [].
        """
        client = self._get_client()
        if not client:
            return []
        if not texts:
            return []

        all_embeddings = []
        total = len(texts)
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(f"Embedding {total} texts in {total_batches} batch(es)...")

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            batch = texts[start: start + batch_size]

            try:
                result = client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch,
                    config=genai_types.EmbedContentConfig(task_type=task_type),
                )
                # Returns one embedding per input text
                batch_embeddings = [list(e.values) for e in result.embeddings]
                all_embeddings.extend(batch_embeddings)
                logger.info(
                    f"  Batch {batch_idx + 1}/{total_batches}: "
                    f"{len(batch_embeddings)} embeddings done"
                )

            except Exception as e:
                logger.warning(
                    f"  Batch {batch_idx + 1} failed: {e}. "
                    f"Falling back to one-by-one..."
                )
                time.sleep(5)
                for text in batch:
                    emb = self.embed_text(text, task_type)
                    all_embeddings.append(emb)
                    time.sleep(0.5)

            if batch_idx < total_batches - 1:
                time.sleep(1)

        logger.info(f"Embedding complete: {len(all_embeddings)}/{total} vectors generated")
        return all_embeddings

    def generate_match_explanation(
        self,
        jd_title: str,
        jd_skills: list,
        jd_requirements: list,
        cv_title: str,
        cv_skills: list,
        cv_experience: str,
        semantic_score: float,
    ) -> str:
        """
        Generate a human-readable explanation for why a candidate matches a JD.

        This is the "explainability" component of the AI system.
        Recruiters can read this to understand WHY the algorithm ranked
        a candidate highly, rather than just seeing a score.

        Returns:
            2-3 sentence explanation string.
        """
        prompt = (
            f"You are an expert recruitment assistant. Explain in 2-3 concise sentences "
            f"why this candidate is a good match (or not) for this job.\n\n"
            f"JOB: {jd_title}\n"
            f"Required skills: {', '.join(jd_skills[:10])}\n"
            f"Key requirements: {'; '.join(jd_requirements[:5])}\n\n"
            f"CANDIDATE: {cv_title}\n"
            f"Skills: {', '.join(cv_skills[:10])}\n"
            f"Experience: {cv_experience[:500]}\n\n"
            f"Semantic match score: {semantic_score:.2f} (0=no match, 1=perfect match)\n\n"
            f'Return JSON: {{"explanation": "Your 2-3 sentence explanation here"}}'
        )

        result = self.generate_json(prompt, temperature=0.3)
        if result and "explanation" in result:
            return result["explanation"]
        return f"Semantic similarity score: {semantic_score:.2f}"


# Module-level singleton — import this anywhere
gemini = GeminiService()
