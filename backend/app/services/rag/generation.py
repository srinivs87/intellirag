"""
Generation Service — LLM answer generation via Groq or Ollama.
"""
import asyncio
from typing import List, Dict, AsyncGenerator

import ollama
from groq import Groq

from app.core.config import settings


import os

def _get_groq_client() -> Groq:
    """Return Groq client, rotating to backup key if primary is rate limited."""
    # Check if primary key is rate limited
    if getattr(_get_groq_client, '_use_backup', False):
        backup_key = settings.GROQ_API_KEY_2
        if backup_key:
            return Groq(api_key=backup_key)
    return Groq(api_key=settings.GROQ_API_KEY)


async def generate_answer(messages: List[Dict]) -> str:
    """Route to Groq or Ollama. Auto-rotates to backup key on rate limit."""
    try:
        if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
            _get_groq_client._use_backup = False
            return await _generate_groq(messages)
        return await _generate_ollama(messages)
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "rate_limit" in err_str.lower():
            # Try backup key if available
            backup_key = settings.GROQ_API_KEY_2
            if backup_key and not getattr(_get_groq_client, "_use_backup", False):
                import logging
                logging.getLogger("intellirag").warning("[Generation] Primary key rate limited, switching to backup key")
                _get_groq_client._use_backup = True
                try:
                    return await _generate_groq(messages)
                except Exception as e2:
                    if "429" in str(e2):
                        return "⚠️ Both API keys are rate limited. Please try again in a few minutes."
                    raise
            import re
            wait = re.search(r"try again in ([\d\w\s\.]+)\.", err_str)
            wait_msg = wait.group(1) if wait else "a few minutes"
            return f"⚠️ Rate limited. Please try again in {wait_msg}."
        raise


async def _generate_groq(messages: List[Dict]) -> str:
    """Call Groq API synchronously in a thread pool."""
    loop = asyncio.get_event_loop()

    def _call():
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
        )
        return response.choices[0].message.content

    return await loop.run_in_executor(None, _call)


async def _generate_ollama(messages: List[Dict]) -> str:
    """Call local Ollama synchronously in a thread pool."""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: ollama.chat(model=settings.OLLAMA_MODEL, messages=messages),
    )
    return response["message"]["content"]


async def stream_answer(messages: List[Dict]) -> AsyncGenerator[str, None]:
    """Stream tokens from Groq or Ollama."""
    if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
        async for token in _stream_groq(messages):
            yield token
    else:
        async for token in _stream_ollama(messages):
            yield token


async def _stream_groq(messages: List[Dict]) -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()

    def _stream():
        client = _get_groq_client()
        return client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            stream=True,
        )

    stream = await loop.run_in_executor(None, _stream)
    for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield token


async def _stream_ollama(messages: List[Dict]) -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()

    def _stream():
        return ollama.chat(model=settings.OLLAMA_MODEL, messages=messages, stream=True)

    stream = await loop.run_in_executor(None, _stream)
    for chunk in stream:
        token = chunk["message"]["content"]
        if token:
            yield token
