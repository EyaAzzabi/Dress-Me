import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";

export const api = axios.create({ baseURL: API_URL });

/** What POST /wardrobe/ answers (422) when the model isn't sure of a photo's category — often a photo of several pieces. */
export interface LowCategoryConfidence {
  message: string;
  suggested_category: string;
  confidence: number;
}

export function parseLowCategoryConfidence(error: unknown): LowCategoryConfidence | null {
  if (!axios.isAxiosError(error)) return null;
  const detail = error.response?.data?.detail;
  return detail && typeof detail === "object" && detail.code === "low_category_confidence" ? detail : null;
}

export function getApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (error.response?.status === 0 || !error.response) {
      return "Impossible de joindre le serveur. Vérifie que l’API DressMe est démarrée.";
    }
  }
  return error instanceof Error ? error.message : "Une erreur est survenue. Réessaie.";
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("dressme_access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export interface ClothingItem {
  id: string;
  image_url: string;
  category?: string | null;
  colors?: string[] | null;
  style?: string | null;
  season?: string | null;
  season_source?: "user" | "vision" | null;
  pattern?: string | null;
  attribute_confidence?: Record<string, number> | null;
  created_at: string;
}

export interface Outfit {
  id: string;
  item_ids: string[];
  occasion: string | null;
  relevance_score: number | null;
  explanation: string | null;
  feedback: OutfitFeedback | null;
}

export type OutfitFeedback = "like" | "dislike" | "worn";

export async function submitOutfitFeedback(outfitId: string, rating: OutfitFeedback | null) {
  const { data } = await api.put<Outfit>(`/recommendations/outfits/${outfitId}/feedback`, { rating });
  return data;
}

export interface ScheduledOutfit {
  date: string;
  item_ids: string[];
  /** The user's avatar wearing the outfit, once rendered (POST /calendar/{day}/render). */
  render_image_url?: string | null;
  items: ClothingItem[];
}

export interface StyleProfile {
  wardrobe_size: number;
  category_counts: Record<string, number>;
  favorite_colors: string[];
  favorite_styles: string[];
  narrative: string | null;
}

export interface ItemUsage {
  item_id: string;
  wear_count: number;
  last_worn: string;
}

export interface PackingList {
  id: string;
  destination: string;
  duration_days: number;
  trip_type: "plage" | "business" | "tourisme";
  start_date?: string | null;
  season?: string | null;
  item_ids: string[];
  checked_item_ids: string[];
  items: ClothingItem[];
}

export interface CatalogAlternative {
  item_key?: string | null;
  name: string;
  price: string | number | null;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  similarity?: number | null;
  cheaper?: boolean | null;
  product_url?: string | null;
  store_url?: string | null;
  buyable?: boolean;
}

export interface BrandRecommendation {
  name: string;
  website: string | null;
  affinity: number;
  product_count: number;
  price_min: number | null;
  price_max: number | null;
  showcase: CatalogAlternative[];
}

export interface PurchaseResult {
  verdict: "recommended" | "think_twice" | "not_recommended";
  score?: number;
  compatibility_score: number;
  similar_item_ids: string[];
  catalog_alternatives: CatalogAlternative[];
  tunisian_brands?: BrandRecommendation[];
  explanation: string;
}

export interface PurchaseHistoryItem {
  id: string;
  image_url: string;
  category: string;
  color: string | null;
  price: number | null;
  verdict: PurchaseResult["verdict"];
  score: number;
  result: PurchaseResult;
  created_at: string;
}

export interface WishlistEntry {
  item_key: string;
  name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  saved_price: number | null;
  live_price: number | null;
  available: boolean | null;
  price_drop: number | null;
  product_url: string | null;
  store_url: string | null;
  buyable: boolean;
  created_at: string;
}

export function formatTnd(value: string | number | null | undefined): string | null {
  if (value == null) return null;
  const amount = typeof value === "number" ? value : parseFloat(String(value).replace(",", "."));
  if (!Number.isFinite(amount)) return String(value);
  return `${amount.toFixed(amount % 1 === 0 ? 0 : 2).replace(".", ",")} TND`;
}

export async function getPurchaseHistory() {
  const { data } = await api.get<PurchaseHistoryItem[]>("/purchase/history");
  return data;
}

export async function deleteHistoryEntry(id: string) {
  await api.delete(`/purchase/history/${id}`);
}

export async function clearPurchaseHistory() {
  await api.delete("/purchase/history");
}

export async function getWishlist() {
  const { data } = await api.get<WishlistEntry[]>("/purchase/wishlist");
  return data;
}

export async function addToWishlist(itemKey: string) {
  const { data } = await api.post<WishlistEntry>("/purchase/wishlist", { item_key: itemKey });
  return data;
}

export async function removeFromWishlist(itemKey: string) {
  await api.delete(`/purchase/wishlist/${encodeURIComponent(itemKey)}`);
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  avatar_photo_url: string | null;
}

export async function uploadPhoto(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<{ image_url: string }>("/wardrobe/upload", form);
  return data.image_url;
}

export interface WardrobeAnalysisResponse {
  category: string;
  colors: string[];
  pattern?: string | null;
  style?: string | null;
  season?: string | null;
  category_uncertain: boolean;
  confidence: Record<string, number>;
  cv_diagnostics: {
    dimensions: { width: number; height: number };
    quality: {
      laplacian_variance: number;
      sharpness: "blurry" | "acceptable" | "sharp";
      brightness: number;
      contrast: number;
      saturation: number;
      quality_score: number;
      warnings: string[];
    };
    bounding_box?: { x: number; y: number; w: number; h: number } | null;
  };
  kmeans_palette: {
    hex: string;
    rgb: [number, number, number];
    percentage: number;
    label: string;
  }[];
  rag_analysis: {
    duplicate_warning?: string | null;
    similar_items: {
      item_id: string;
      image_url: string;
      category: string;
      colors?: string[];
      style?: string;
      similarity: number;
    }[];
    recommended_pairings: {
      item_id: string;
      category: string;
      colors?: string[];
      style?: string;
      image_url: string;
      score: number;
    }[];
  };
  styling_insights: {
    editorial_advice: string;
    style_archetype?: string;
    recommended_occasions?: string[];
    care_tip?: string;
  };
  segmentation?: {
    person_detected: boolean;
    extracted_garments: {
      category: string;
      share: number;
      image_url: string;
    }[];
  } | null;
}

export async function analyzePhoto(imageUrl: string): Promise<WardrobeAnalysisResponse> {
  const { data } = await api.post<WardrobeAnalysisResponse>("/wardrobe/analyze", { image_url: imageUrl });
  return data;
}
