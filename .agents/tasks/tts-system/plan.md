# Implementation Plan: TTS System for DressMe

This plan adds Text-to-Speech functionality to read outfit recommendations aloud in French.

## FEAT-001: Backend TTS Infrastructure

- [ ] 1. Add gTTS dependency to requirements.txt
      Add `gTTS>=2.5` to e:\Téléchargements\Dress-Me-main\backend\requirements.txt
      Files: e:\Téléchargements\Dress-Me-main\backend\requirements.txt
      Verify: `pip install -r requirements.txt` succeeds

- [ ] 2. Add TTS configuration settings
      Add 4 new settings to Settings class in config.py: tts_enabled (bool, default True), tts_provider (str, default 'gtts'), tts_language (str, default 'fr'), tts_cache_dir (str, default './tts_cache')
      Files: e:\Téléchargements\Dress-Me-main\backend\app\core\config.py
      Verify: Backend starts without error: `uvicorn app.main:app --reload --port 8000`

- [ ] 3. Create TTSService class
      Create service following StorageService pattern: is_configured() method, speak(text: str) -> bytes, SHA-256 hash-based file caching in tts_cache_dir, gTTS with lang='fr'
      Files: e:\Téléchargements\Dress-Me-main\backend\app\services\tts_service.py
      Verify: Unit tests pass: `pytest tests/test_tts_service.py -v`

- [ ] 4. Create TTS API routes
      Create router with POST /speak (text input, returns MP3 StreamingResponse) and GET /recommendation/{outfit_id} (fetches Outfit.explanation, returns MP3). Follow recommendations.py authentication pattern.
      Files: e:\Téléchargements\Dress-Me-main\backend\app\api\routes\tts.py
      Verify: Check Swagger UI at http://localhost:8000/docs shows /api/v1/tts/* endpoints

- [ ] 5. Register TTS router
      Import tts in __init__.py and add api_router.include_router(tts.router)
      Files: e:\Téléchargements\Dress-Me-main\backend\app\api\routes\__init__.py
      Verify: Swagger UI shows tts tag with 2 endpoints

- [ ] 6. Create TTS cache directory at startup
      In main.py, add cache directory creation following local_storage_dir pattern
      Files: e:\Téléchargements\Dress-Me-main\backend\app\main.py
      Verify: Start backend, check tts_cache directory created

- [ ] 7. Add unit tests for TTS service
      Test is_configured(), speak() generation, caching behavior, hash consistency
      Files: e:\Téléchargements\Dress-Me-main\backend\tests\test_tts_service.py
      Verify: `pytest tests -q` — all tests pass including new TTS tests

## FEAT-002: Frontend TTS Components

- [ ] 8. Add TTS API client methods
      Add speakText(text) and speakRecommendation(outfitId) functions returning Promise<Blob>
      Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\api.ts
      Verify: `npx tsc --noEmit` passes

- [ ] 9. Create TTSContext provider
      React Context with state (currentAudio, isPlaying, isMuted, volume) and methods (playAudio, pauseAudio, stopAudio, toggleMute, setVolume)
      Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\TTSContext.tsx
      Verify: `npx tsc --noEmit` passes

- [ ] 10. Create TTSSpeaker component
       Reusable component accepting text or outfitId props, speaker icon button, loading/error states, uses useTTS hook
       Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\TTSSpeaker.tsx
       Verify: `npx tsc --noEmit` passes

- [ ] 11. Wrap App with TTSProvider
       In main.tsx, wrap <App /> with <TTSProvider>
       Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\main.tsx
       Verify: Dev server starts without errors: `npm run dev`

## FEAT-003: Outfits Screen Integration

- [ ] 12. Add TTSSpeaker to outfit cards
       Import TTSSpeaker in App.tsx, add component to each outfit card with outfitId prop
       Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\App.tsx
       Verify: `npx tsc --noEmit` passes

- [ ] 13. Add TTS button styling
       Add .outfit-tts-control CSS class for speaker button layout
       Files: e:\Téléchargements\Dress-Me-main\frontend\web\src\styles.css
       Verify: Visual check in browser — speaker button appears on outfit cards without breaking layout

## End-to-End Verification

- [ ] 14. Full integration test
       Start backend and frontend, log in, generate outfits, click speaker icon on outfit card, verify French audio plays, verify caching (second click is instant), verify pause/stop controls work
       Files: All modified files
       Verify: Manual testing checklist complete — audio plays, caching works, UI is responsive, no console errors
