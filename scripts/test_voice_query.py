#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from urllib.parse import unquote

import requests


DEFAULT_QUESTION = "What did I talk about yesterday?"


def _write_silence_wav(path: Path, seconds: int = 3) -> None:
    sample_rate = 16_000
    sample_count = sample_rate * seconds
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * sample_count)


def _generate_test_wav(path: Path, text: str) -> None:
    """
    Generate a real spoken test WAV on macOS. If the local tools are missing,
    fall back to silence so the request wiring can still be tested.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        aiff_path = Path(temp_dir) / "question.aiff"
        try:
            subprocess.run(["say", "-o", str(aiff_path), text], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff_path), str(path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            _write_silence_wav(path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test POST /v1/app/memories/ask-voice")
    parser.add_argument("--api-url", default=os.getenv("VOICE_QUERY_API_URL", "http://localhost:8000/v1"))
    parser.add_argument("--token", default=os.getenv("VOICE_QUERY_TOKEN"), help="App bearer token")
    parser.add_argument("--wav", type=Path, help="Existing 16kHz mono WAV question file")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Text used when generating a macOS test WAV")
    parser.add_argument("--output", type=Path, default=Path("/tmp/test_answer.wav"))
    parser.add_argument("--allow-json-fallback", action="store_true", help="Accept text-only JSON fallback when TTS fails")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.token:
        print("Missing token. Export VOICE_QUERY_TOKEN or pass --token.", file=sys.stderr)
        return 2

    if args.wav:
        wav_path = args.wav
    else:
        wav_path = Path("/tmp/secondmind_voice_query_test.wav")
        _generate_test_wav(wav_path, args.question)

    endpoint = args.api_url.rstrip("/") + "/app/memories/ask-voice"
    headers = {"Authorization": f"Bearer {args.token}"}

    with wav_path.open("rb") as wav_file:
        response = requests.post(
            endpoint,
            headers=headers,
            files={"audio": ("query.wav", wav_file, "audio/wav")},
            timeout=180,
        )

    content_type = response.headers.get("content-type", "")
    if response.status_code != 200:
        print(f"Request failed {response.status_code}: {response.text}", file=sys.stderr)
        return 1

    if "application/json" in content_type:
        if args.allow_json_fallback:
            print("JSON fallback response:")
            print(response.text)
            return 0
        print(f"Expected audio/wav, got JSON fallback: {response.text}", file=sys.stderr)
        return 1

    if "audio/wav" not in content_type:
        print(f"Expected audio/wav, got {content_type}", file=sys.stderr)
        return 1

    query_text = unquote(response.headers.get("x-query-text", ""))
    answer_text = unquote(response.headers.get("x-answer-text", ""))
    if not query_text or not answer_text:
        print("Missing X-Query-Text or X-Answer-Text headers.", file=sys.stderr)
        return 1

    args.output.write_bytes(response.content)
    print(f"Question: {query_text}")
    print(f"Answer: {answer_text}")
    print(f"Saved answer WAV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
