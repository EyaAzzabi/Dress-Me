export type Season = "ete" | "hiver" | "mi_saison" | "toutes_saisons";

export interface ClothingItem {
  id: string;
  image_url: string;
  category?: string | null;
  colors?: string[] | null;
  style?: string | null;
  season?: Season | null;
  /** "user" = chosen/confirmed by the owner, "vision" = the model's suggestion. */
  season_source?: "user" | "vision" | null;
  pattern?: string | null;
  attribute_confidence?: Record<string, number> | null;
  created_at: string;
}

export interface ItemUsage {
  item_id: string;
  wear_count: number;
  last_worn: string;
}

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
}
