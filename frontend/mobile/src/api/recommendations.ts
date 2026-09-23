import { apiClient } from "@/api/client";

export interface OutfitRequest {
  occasion?: string;
  weather?: string;
  season?: string;
}

export function recommendOutfits(payload: OutfitRequest) {
  return apiClient.post("/recommendations/outfits", payload).then((r) => r.data);
}

export interface PurchaseCheckResult {
  verdict: "recommended" | "think_twice" | "not_recommended";
  compatibility_score: number;
  similar_item_ids: string[];
  explanation: string;
}

export function checkPurchase(imageUrl: string) {
  return apiClient
    .post<PurchaseCheckResult>("/purchase/check", { image_url: imageUrl })
    .then((r) => r.data);
}
