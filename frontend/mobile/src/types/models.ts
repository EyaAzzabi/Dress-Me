export interface ClothingItem {
  id: string;
  image_url: string;
  category?: string | null;
  colors?: string[] | null;
  style?: string | null;
  season?: string | null;
  pattern?: string | null;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name?: string | null;
}
