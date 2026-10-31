# DressMe — Mobile App

Expo / React Native client for DressMe, matching the "Mobile App (iOS/Android)" box in
the [global architecture](../../docs/801880877_1090756726785409_1212958715350036331_n.png).

## Structure

- `src/api/` — HTTP client (axios) and typed calls to the FastAPI backend
- `src/context/AuthContext.tsx` — JWT session state, persisted via AsyncStorage
- `src/navigation/` — tab navigation (Wardrobe, Outfits, Should I buy this?, Profile)
- `src/screens/` — one screen per core feature from the product brief
- `src/types/` — shared TypeScript models mirroring the backend Pydantic schemas

## Getting started

```bash
npm install
cp .env.example .env   # point API_URL at your backend, e.g. http://<lan-ip>:8000/api/v1
npm start
```

Requires the `backend/` service running (see `../../infra/docker-compose.yml`) and, on a
physical device, `API_URL` set to your machine's LAN IP rather than `localhost`.
