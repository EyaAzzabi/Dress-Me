import { apiClient } from "@/api/client";

export interface OutfitRequest {
  occasion?: string;
  weather?: string;
  season?: string;
  city?: string; // looked up via WeatherService server-side when weather isn't given directly
  request_text?: string;
}

export type OutfitFeedback = "like" | "dislike" | "worn";

export interface ReActStep {
  thought: string;
  action: {
    tool: string;
    args: Record<string, unknown>;
  };
  observation: {
    tool: string;
    result: unknown;
  };
}

export interface CriticScores {
  meteo: number;        // 0-5
  occasion: number;     // 0-5
  couleurs: number;     // 0-5
  completude: number;   // 0-5
  fraicheur: number;    // 0-5
}

export interface Outfit {
  id: string;
  item_ids: string[];
  occasion: string | null;
  relevance_score: number | null;
  explanation: string | null;
  feedback: OutfitFeedback | null;
  // New agentic fields (optional — absent from DB-stored outfits fetched via GET /outfits)
  critic_score?: {
    scores: CriticScores;
    total: number;
    approved: boolean;
    feedback: string;
  };
  critic_feedback?: string | null;
  critic_iterations?: number;
  react_trace?: ReActStep[];
  style_guidelines_used?: string[];
}

export interface OutfitRecommendationResult {
  context: {
    occasion: string | null;
    weather: string | null;
    season: string | null;
  };
  outfits: Outfit[];
  evaluation?: Record<string, number>;
}

export function recommendOutfits(payload: OutfitRequest) {
  return apiClient
    .post<OutfitRecommendationResult>("/recommendations/outfits", payload)
    .then((r) => r.data);
}

export function listOutfits() {
  return apiClient.get<Outfit[]>("/recommendations/outfits").then((r) => r.data);
}

export function feedbackOutfit(outfitId: string, rating: OutfitFeedback | null) {
  return apiClient
    .put<Outfit>(`/recommendations/outfits/${outfitId}/feedback`, { rating })
    .then((r) => r.data);
}

export interface CatalogAlternative {
  name: string;
  price: string | number | null;
  brand: string | null;
  category: string | null;
  image_url: string | null;
}

export interface PurchaseCheckResult {
  verdict: "recommended" | "think_twice" | "not_recommended";
  compatibility_score: number;
  similar_item_ids: string[];
  catalog_alternatives: CatalogAlternative[];
  explanation: string;
}

export function checkPurchase(imageUrl: string) {
  return apiClient
    .post<PurchaseCheckResult>("/purchase/check", { image_url: imageUrl })
    .then((r) => r.data);
}
