# Implementation Plan: Text-to-Speech (TTS)

## Context
- Backend: FastAPI at `e:/Téléchargements/Dress-Me-main/backend`
- Frontend: React/Vite at `e:/ Téléchargements/Dress-Me-main/frontend/web`
- Language: French for outfit recommendations and explanations
- Existing patterns: Weather service and weather API route serve as reference for TTS implementation

---

- [ ] 1. Add gTTS dependency to backend/requirements.txt
      Add `gTTS>=2.4.0` to the requirements file for Google Text-to-Speech support.
      Files: backend/requirements.txt
      Verify: `pip install gTTS` succeeds in the venv

- [ ] 2. Add TTS configuration to backend/app/core/config.py
      Add `TTS_ENABLED: bool = True` and `TTS_LANGUAGE: str = "fr"` to the Settings class.
      Files: backend/app/core/config.py
      Verify: Settings().TTS_ENABLED returns True, Settings().TTS_LANGUAGE returns "fr"

- [ ] 3. Create TTS service in backend/app/services/tts_service.py
      Implement `speak_text(text: str) -> bytes` using gTTS for French audio generation, and `speak_and_cache(text: str, cache_dir: str) -> str` with hash-based caching. Handle errors gracefully.
      Files: backend/app/services/tts_service.py
      Verify: `python -c "from app.services.tts_service import TTSService; s = TTSService(); audio = s.speak_text('Bonjour'); print(len(audio))"` outputs audio byte length

- [ ] 4. Create TTS API route in backend/app/api/routes/tts.py
      Create POST /api/v1/tts/speak endpoint accepting JSON `{"text": "..."}` and returning audio/MP3 via StreamingResponse with proper content-type header. Include error handling for empty text and TTS failures.
      Files: backend/app/api/routes/tts.py
      Verify: Backend starts without import errors

- [ ] 5. Register TTS router in backend/app/api/routes/__init__.py
      Import and include the tts router in api_router, matching the pattern used for weather and other modules.
      Files: backend/app/api/routes/__init__.py
      Verify: `python -c "from app.api.routes import api_router; print([r.path for r in api_router.routes])"` includes "/tts"

- [ ] 6. Create frontend TTSSpeaker component in frontend/web/src/TTSSpeaker.tsx
      Build a React component with props: text (string), autoPlay (boolean). Include states: playing, paused, loading, error. Controls: play button with French label "Écouter", stop button. Use HTML5 Audio API to call backend at /api/v1/tts/speak.
      Files: frontend/web/src/TTSSpeaker.tsx
      Verify: Component compiles without TypeScript errors

- [ ] 7. Test TTS endpoint end-to-end
      Test with: `curl -X POST http://127.0.0.1:8000/api/v1/tts/speak -H "Content-Type: application/json" -d '{"text":"Bonjour, je recommande une robe bleue pour cet été."}'` — verify MP3 audio is returned (starts with ID3 or ffpag header bytes).
      Files: (none)
      Verify: curl returns audio content, status 200

- [ ] 8. Test frontend TTS component integration
      Verify the frontend can make requests to the TTS endpoint (check Vite proxy or CORS is configured).
      Files: frontend/web/vite.config.ts, backend/app/main.py
      Verify: API call from frontend reaches backend and returns audio