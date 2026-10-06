import { apiClient } from "@/api/client";

export interface StyleProfile {
  wardrobe_size: number;
  category_counts: Record<string, number>;
  favorite_colors: string[];
  favorite_styles: string[];
  // Only populated when the backend has an LLM provider configured
  // (LLM_PROVIDER != "none") — null otherwise, not an error.
  narrative: string | null;
}

export function getStyleProfile() {
  return apiClient.get<StyleProfile>("/style-profile/").then((r) => r.data);
}
