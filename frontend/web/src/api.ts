import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

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

export interface PurchaseResult {
  verdict: "recommended" | "think_twice" | "not_recommended";
  compatibility_score: number;
  similar_item_ids: string[];
  catalog_alternatives: {
    name: string;
    price: string | number | null;
    brand: string | null;
    category: string | null;
    image_url: string | null;
  }[];
  explanation: string;
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
