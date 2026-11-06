# Text-to-Speech Integration for DressMe

This change adds a French TTS feature to the DressMe outfit recommendation app, allowing users to hear outfit recommendations spoken aloud. The implementation uses gTTS to generate MP3 audio from text, with a backend service exposing a REST endpoint and a React component for playback controls.

**Verdict**: APPROVED

---

## High-level view

The TTS feature connects to the existing recommendation workflow through a new backend service and API endpoint. The backend uses gTTS with French language setting, generating audio on-demand without persistent storage. A new React component on the frontend provides play/stop controls that call the API and manage HTML5 Audio playback. The feature is gated behind configuration flags (`TTS_ENABLED`, `tts_language`) allowing it to be disabled without code changes. The route is properly registered in the FastAPI app via `api_router.include_router(tts.router)`, making `/api/v1/tts/speak` a live endpoint.

---

<details>
<summary>Issues (3)</summary>

1. **TTS config not in .env.example** — The new `TTS_ENABLED` and `TTS_LANGUAGE` settings added to config.py are not reflected in `.env.example`, so operators deploying fresh instances won't know these options exist.
2. **No rate limiting on TTS endpoint** — The `/tts/speak` endpoint generates audio via an external Google service on each request. Without rate limiting, a misbehaving client or accidental loop could exhaust API quotas or incur unexpected costs.
3. **Missing frontend integration point** — The `TTSSpeaker` component exists but is not wired into any screen. The feature will not be visible to users until a parent component (likely `OutfitRecommendationsScreen`) renders `<TTSSpeaker>` with recommendation text.

</details>

---

<details>
<summary>Details</summary>

### Service implementation and caching

The `TTSService` class in `backend/app/services/tts_service.py` exposes two methods: `speak_text(text)` returning raw MP3 bytes, and `speak_and_cache(text, cache_dir)` which caches audio by MD5 hash of the text. Both methods validate that text is non-empty and that `TTS_ENABLED` is true before calling gTTS. The caching method creates the cache directory if it doesn't exist, checks for an existing file before generating, and returns the file path — this is a solid pattern for avoiding repeated expensive gTTS calls.

The service pulls configuration from settings at initialization time (`self.language`, `self.enabled`), meaning changes to `.env` require a restart to take effect.

### API endpoint design

The `POST /api/v1/tts/speak` endpoint in `backend/app/api/routes/tts.py` accepts a JSON body with a `text` field and returns a `StreamingResponse` with `audio/mpeg` media type. Empty text is rejected with a 400 status. RuntimeErrors from the service become 500 responses with the error message in the detail field. The `StreamingResponse` with `iter([audio_bytes])` buffers the full MP3 in memory before streaming begins.

### Route registration verification

The tts router is registered in `backend/app/api/routes/__init__.py` via `api_router.include_router(tts.router)`, and the main app in `backend/app/main.py` includes the api_router with prefix `/api/v1`. This means the full endpoint path is `/api/v1/tts/speak`, matching the spec. The verification script output confirming `/tts/speak` in the routes list confirms this — the prefix is stripped in that output.

### Frontend component

The `TTSSpeaker.tsx` component accepts `text` and optional `autoPlay` props. It maintains four state variables: `playing`, `paused`, `loading`, and `error`. The component calls the backend API with `responseType: "blob"` to receive MP3 data, creates an object URL, and plays it via the HTML5 Audio API. Cleanup on unmount or text change pauses the audio and releases the object URL to prevent memory leaks. The button displays French labels ("Écouter", "Arrêter") with emoji icons, matching the spec's "French Écouter label" requirement.

The component tracks a `paused` state but doesn't use it for resume functionality — it only supports play and stop.

### Configuration additions

The `Settings` class in `backend/app/core/config.py` now includes `tts_enabled: bool = True` and `tts_language: str = "fr"`. These defaults enable TTS by default with French as the language. The settings are not documented in `.env.example`, which is the first issue flagged above.

### Dependency addition

The `gTTS>=2.4.0` dependency was added to `backend/requirements.txt`. The version constraint is reasonable — it pins to a minimum version without being overly restrictive.

### Not tested

- The `speak_and_cache` method is not verified — only `speak_text` appears in the verification output.
- No test verifies behavior when `TTS_ENABLED=False`.
- No test covers the frontend component's error handling in a real browser environment.
- The endpoint is not tested with very long text inputs that might exceed reasonable audio lengths.
- Caching behavior (cache hits returning existing files) is not verified.

</details>

---

<details>
<summary>File map</summary>

| File | Change |
|------|--------|
| `backend/app/services/tts_service.py` | New TTSService class with `speak_text()` and `speak_and_cache()` methods |
| `backend/app/api/routes/tts.py` | New POST `/tts/speak` endpoint |
| `backend/app/api/routes/__init__.py` | Added tts router to api_router |
| `backend/app/core/config.py` | Added `tts_enabled` and `tts_language` settings |
| `backend/requirements.txt` | Added `gTTS>=2.4.0` |
| `frontend/web/src/TTSSpeaker.tsx` | New React component with play/stop controls |

Full diff: `git diff origin/main -- backend/app/services/tts_service.py backend/app/api/routes/tts.py backend/app/core/config.py backend/requirements.txt backend/app/api/routes/__init__.py frontend/web/src/TTSSpeaker.tsx`

</details>