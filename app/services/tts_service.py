from __future__ import annotations

from functools import lru_cache
import base64
import logging
import os
import shutil
import subprocess
import tempfile

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class TTSServiceError(RuntimeError):
    pass


class OfflineTTSService:
    def __init__(self) -> None:
        settings = get_settings()
        self.backend = settings.tts_backend.lower().strip()
        self.model_name = settings.coqui_tts_model
        self.espeak_voice = settings.espeak_voice
        self.espeak_speed = settings.espeak_speed
        self.elevenlabs_api_key = settings.elevenlabs_api_key
        self.elevenlabs_voice_id = settings.elevenlabs_voice_id
        self.elevenlabs_model_id = settings.elevenlabs_model_id
        self.elevenlabs_timeout_seconds = settings.elevenlabs_timeout_seconds
        self.sarvam_api_key = settings.sarvam_api_key
        self.sarvam_tts_model = settings.sarvam_tts_model
        self.sarvam_tts_speaker = settings.sarvam_tts_speaker
        self.sarvam_tts_language_code = settings.sarvam_tts_language_code
        self.sarvam_tts_sample_rate = settings.sarvam_tts_sample_rate
        self.sarvam_tts_pace = settings.sarvam_tts_pace
        self.sarvam_tts_temperature = settings.sarvam_tts_temperature
        self.sarvam_tts_timeout_seconds = settings.sarvam_tts_timeout_seconds
        self._tts = None
        self._active_backend: str | None = None

    def load(self) -> None:
        if self._active_backend is not None:
            return

        if self.backend not in {"auto", "coqui", "espeak"}:
            raise TTSServiceError("TTS_BACKEND must be one of: auto, coqui, espeak")

        if self.backend in {"auto", "coqui"}:
            try:
                self._load_coqui()
                self._active_backend = "coqui"
                return
            except TTSServiceError as exc:
                if self.backend == "coqui":
                    raise
                logger.warning("Coqui TTS unavailable; falling back to espeak-ng: %s", exc)

        if shutil.which("espeak-ng") is None:
            raise TTSServiceError("espeak-ng is not installed")

        self._active_backend = "espeak"
        logger.info("Offline TTS ready: espeak-ng voice=%s speed=%s", self.espeak_voice, self.espeak_speed)

    def _load_coqui(self) -> None:
        if self._tts is not None:
            return

        try:
            from TTS.api import TTS
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError("Coqui TTS package is not installed") from exc

        logger.info("Loading Coqui TTS model: %s", self.model_name)
        try:
            self._tts = TTS(model_name=self.model_name, progress_bar=False, gpu=False)
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError(f"Failed to load Coqui TTS model: {exc}") from exc
        logger.info("Coqui TTS model ready: %s", self.model_name)

    def synthesize_to_file(self, text: str, output_path: str, provider: str | None = None) -> str:
        clean_text = text.strip()
        if not clean_text:
            raise TTSServiceError("Cannot synthesize empty text")

        requested_provider = (provider or "elevenlabs").strip().lower()
        if requested_provider != "elevenlabs":
            logger.info("Unsupported app-facing TTS provider '%s'; forcing elevenlabs", requested_provider)
        self._synthesize_elevenlabs(clean_text, output_path)
        return "elevenlabs"

    def _synthesize_default(self, clean_text: str, output_path: str) -> None:
        self.load()
        if self._active_backend == "coqui":
            try:
                self._tts.tts_to_file(text=clean_text, file_path=output_path)
                return
            except Exception as exc:  # noqa: BLE001
                raise TTSServiceError(f"TTS synthesis failed: {exc}") from exc

        try:
            subprocess.run(
                [
                    "espeak-ng",
                    "-v",
                    self.espeak_voice,
                    "-s",
                    str(self.espeak_speed),
                    "-w",
                    output_path,
                    clean_text,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=45,
            )
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError(f"espeak-ng synthesis failed: {exc}") from exc

    def _synthesize_elevenlabs(self, clean_text: str, output_path: str) -> None:
        if not self.elevenlabs_api_key:
            raise TTSServiceError("ELEVENLABS_API_KEY is not configured")
        if shutil.which("ffmpeg") is None:
            raise TTSServiceError("ffmpeg is required to convert ElevenLabs audio to WAV")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}"
        response = requests.post(
            url,
            headers={
                "xi-api-key": self.elevenlabs_api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json={
                "text": clean_text,
                "model_id": self.elevenlabs_model_id,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.75,
                },
            },
            timeout=self.elevenlabs_timeout_seconds,
        )
        if response.status_code >= 400:
            raise TTSServiceError(f"ElevenLabs returned HTTP {response.status_code}: {response.text[:240]}")
        if not response.content:
            raise TTSServiceError("ElevenLabs returned empty audio")

        temp_dir = os.path.dirname(output_path) or tempfile.gettempdir()
        fd, mp3_path = tempfile.mkstemp(prefix="elevenlabs_", suffix=".mp3", dir=temp_dir)
        try:
            with os.fdopen(fd, "wb") as mp3_file:
                mp3_file.write(response.content)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    mp3_path,
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    output_path,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError(f"ElevenLabs audio conversion failed: {exc}") from exc
        finally:
            try:
                os.remove(mp3_path)
            except FileNotFoundError:
                pass

    def _synthesize_sarvam(self, clean_text: str, output_path: str) -> None:
        if not self.sarvam_api_key:
            raise TTSServiceError("SARVAM_API_KEY is not configured")

        response = requests.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={
                "api-subscription-key": self.sarvam_api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": clean_text,
                "target_language_code": self.sarvam_tts_language_code,
                "speaker": self.sarvam_tts_speaker,
                "model": self.sarvam_tts_model,
                "speech_sample_rate": self.sarvam_tts_sample_rate,
                "pace": self.sarvam_tts_pace,
                "temperature": self.sarvam_tts_temperature,
                "output_audio_codec": "wav",
            },
            timeout=self.sarvam_tts_timeout_seconds,
        )
        if response.status_code >= 400:
            raise TTSServiceError(f"Sarvam returned HTTP {response.status_code}: {response.text[:240]}")

        data = response.json()
        audios = data.get("audios") or []
        if not audios:
            raise TTSServiceError("Sarvam returned no audio payload")

        try:
            audio_bytes = base64.b64decode(audios[0])
        except Exception as exc:  # noqa: BLE001
            raise TTSServiceError(f"Sarvam audio decode failed: {exc}") from exc
        if not audio_bytes:
            raise TTSServiceError("Sarvam returned empty decoded audio")

        with open(output_path, "wb") as wav_file:
            wav_file.write(audio_bytes)


@lru_cache(maxsize=1)
def get_tts_service() -> OfflineTTSService:
    return OfflineTTSService()


def preload_tts_model() -> None:
    try:
        get_tts_service().load()
    except TTSServiceError as exc:
        logger.warning("Offline TTS preload skipped: %s", exc)
