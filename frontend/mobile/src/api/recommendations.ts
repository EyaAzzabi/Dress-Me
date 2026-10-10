import { apiClient } from "@/api/client";

export interface OutfitRequest {
  occasion?: string;
  weather?: string;
  season?: string;
  city?: string; // looked up via WeatherService server-side when weather isn't given directly
}

export interface Outfit {
  id: string;
  item_ids: string[];
  occasion: string | null;
  relevance_score: number | null;
  explanation: string | null;
}

export interface OutfitRecommendationResult {
  context: {
    occasion: string | null;
    weather: string | null;
    season: string | null;
  };
  outfits: Outfit[];
}

export function recommendOutfits(payload: OutfitRequest) {
  return apiClient
    .post<OutfitRecommendationResult>("/recommendations/outfits", payload)
    .then((r) => r.data);
}

export function listOutfits() {
  return apiClient.get<Outfit[]>("/recommendations/outfits").then((r) => r.data);
}