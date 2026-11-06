"""TTS (Text-to-Speech) API endpoint for French audio generation."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.tts_service import TTSService

router = APIRouter(prefix="/tts", tags=["tts"])
_service = TTSService()


class TTSRequest(BaseModel):
    text: str


@router.post("/speak")
def speak_text(request: TTSRequest) -> StreamingResponse:
    """
    Convert text to speech and return MP3 audio.

    Accepts JSON with a 'text' field and returns audio/MP3.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        audio_bytes = _service.speak_text(request.text)
        return StreamingResponse(
            iter([audio_bytes]),
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")