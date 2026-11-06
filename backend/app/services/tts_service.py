"""Text-to-Speech service using gTTS for French audio generation."""
import hashlib
import logging
from pathlib import Path

from gtts import gTTS

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TTSService:
    """Service for converting text to speech using Google TTS."""

    def __init__(self) -> None:
        self.language = settings.tts_language or "fr"
        self.enabled = settings.tts_enabled

    def speak_text(self, text: str) -> bytes:
        """
        Convert text to speech and return MP3 audio bytes.

        Args:
            text: The text to convert to speech

        Returns:
            MP3 audio data as bytes
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if not self.enabled:
            raise RuntimeError("TTS is disabled")

        try:
            tts = gTTS(text=text, lang=self.language, slow=False)
            # gTTS doesn't directly support to_bytes, so we save to a temp buffer
            import io
            mp3_buffer = io.BytesIO()
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)
            return mp3_buffer.getvalue()
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            raise RuntimeError(f"Failed to generate TTS: {e}")

    def speak_and_cache(self, text: str, cache_dir: str) -> str:
        """
        Convert text to speech and cache the audio file.

        Uses a hash of the text as the filename to avoid regenerating
        audio for the same text.

        Args:
            text: The text to convert to speech
            cache_dir: Directory to store cached audio files

        Returns:
            Path to the generated audio file
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        if not self.enabled:
            raise RuntimeError("TTS is disabled")

        # Create a hash of the text for the filename
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)

        audio_file = cache_path / f"{text_hash}.mp3"

        # Return cached file if it exists
        if audio_file.exists():
            return str(audio_file)

        try:
            tts = gTTS(text=text, lang=self.language, slow=False)
            tts.save(str(audio_file))
            return str(audio_file)
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            raise RuntimeError(f"Failed to generate TTS: {e}")