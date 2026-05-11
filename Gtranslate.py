import time
import random
import requests
import certifi
from requests import Session
from requests.exceptions import SSLError, Timeout, ConnectionError, HTTPError

TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

session = Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
})


def translate_google(text: str, target="zh-CN", source="auto", retries=3) -> str:
    if not text or not text.strip():
        return text

    params = {
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    }

    last_error = None

    for attempt in range(retries):
        try:
            r = session.get(
                TRANSLATE_URL,
                params=params,
                timeout=(5, 30),
                verify=certifi.where(),
            )
            r.raise_for_status()

            data = r.json()
            if not data or not data[0]:
                return ""

            return "".join(seg[0] for seg in data[0] if seg and seg[0])

        except SSLError as e:
            raise RuntimeError(
                "HTTPS 证书校验失败。"
            ) from e

        except (Timeout, ConnectionError, HTTPError) as e:
            last_error = e
            sleep_seconds = 1.5 * (attempt + 1) + random.random()
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Google 翻译请求失败，已重试 {retries} 次: {last_error}") from last_error


def split_text(text: str, chunk_size=1200) -> list[str]:
    """
    尽量按段落切，避免把 Markdown/HTML/句子从中间切断。
    """
    chunks = []
    current = ""

    paragraphs = text.splitlines(keepends=True)

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""

            for i in range(0, len(paragraph), chunk_size):
                chunks.append(paragraph[i:i + chunk_size])

            continue

        if len(current) + len(paragraph) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current += paragraph

    if current:
        chunks.append(current)

    return chunks


def translate_large(text: str, chunk_size=1200) -> str:
    chunks = split_text(text, chunk_size=chunk_size)

    results = []
    for index, chunk in enumerate(chunks, start=1):
        translated = translate_google(chunk)
        results.append(translated)

        if index < len(chunks):
            time.sleep(0.8 + random.random() * 0.7)

    return "".join(results)