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
cp .env.example .env   # set EXPO_PUBLIC_API_URL to the backend URL
npm start
```

`EXPO_PUBLIC_API_URL` must point to the FastAPI server. A deployed phone build needs a
public HTTPS API URL. For local development on a physical device, use the computer's
LAN IP instead of `localhost`; the computer and Expo development server must remain on.
