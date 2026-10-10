import { apiClient } from "@/api/client";

export type Verdict = "recommended" | "think_twice" | "not_recommended";
export type FactorKey = "versatility" | "uniqueness" | "style_fit" | "price";
export type PriceLabel = "bon_prix" | "prix_marche" | "cher";

export interface PurchaseFactor {
  key: FactorKey;
  label: string;
  score: number; // 0-1
  weight: number; // 0-1, sums to 1 over the factors present
  detail: string;
}

export interface WardrobeItemRef {
  id: string;
  image_url: string;
  category: string | null;
}

export interface DuplicateItem extends WardrobeItemRef {
  similarity: number;
}

export interface UnlockedOutfit {
  items: WardrobeItemRef[];
  score: number;
}

export interface PriceInsight {
  price: number | null;
  market_median: number;
  market_min: number;
  market_max: number;
  sample_size: number;
  percentile: number | null;
  label: PriceLabel | null;
}

export interface CatalogAlternative {
  item_key: string | null;
  name: string;
  brand: string | null;
  category: string | null;
  price: number | string | null;
  image_url: string | null;
  similarity: number | null;
  cheaper: boolean | null;
  product_url: string | null; // the product's page on the brand's site
  store_url: string | null;
  buyable: boolean; // live sizes + checkout via getLiveProduct
}

export interface CostPerWear {
  wears_per_year: number;
  cost_per_wear: number; // TND
  label: "excellent" | "correct" | "eleve";
}

export interface BrandRecommendation {
  name: string;
  website: string | null;
  affinity: number; // mean FashionCLIP similarity of the brand's closest products
  product_count: number;
  price_min: number | null;
  price_max: number | null;
  showcase: CatalogAlternative[];
}

export interface ProductVariant {
  id: number;
  title: string | null; // size / colour, null for single-variant products
  available: boolean;
  price: number | null;
  checkout_url: string;
}

export interface LiveProduct {
  title: string;
  brand: string;
  product_url: string;
  store_url: string;
  image_url: string | null;
  price: number | null;
  compare_at_price: number | null; // pre-sale price when on sale
  available: boolean;
  variants: ProductVariant[];
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

export interface PurchaseCheckResult {
  verdict: Verdict;
  score: number; // 0-100
  compatibility_score: number;
  explanation: string;
  item: { category: string; color: string | null; pattern: string | null; style: string | null };
  factors: PurchaseFactor[];
  outfits_unlocked: number;
  outfit_examples: UnlockedOutfit[];
  duplicates: DuplicateItem[];
  similar_item_ids: string[];
  price_insight: PriceInsight | null;
  cost_per_wear: CostPerWear | null;
  catalog_alternatives: CatalogAlternative[];
  tunisian_brands: BrandRecommendation[];
}

export interface ExtractedGarment {
  category: string;
  color: string | null;
  image_url: string; // cut-out on a white background, or the photo itself if no one wears it
  share: number; // 0-1, share of the person covered by this garment
}

export interface GarmentExtractionResult {
  person_detected: boolean;
  garments: ExtractedGarment[];
}

export function extractGarments(imageUrl: string) {
  return apiClient
    .post<GarmentExtractionResult>("/purchase/extract", { image_url: imageUrl })
    .then((r) => r.data);
}

export function checkPurchase(imageUrl: string, price?: number, category?: string) {
  return apiClient
    .post<PurchaseCheckResult>("/purchase/check", { image_url: imageUrl, price, category })
    .then((r) => r.data);
}

export interface PurchaseHistoryItem {
  id: string;
  image_url: string;
  category: string;
  color: string | null;
  price: number | null;
  verdict: Verdict;
  score: number;
  result: PurchaseCheckResult; // the check exactly as it was shown
  created_at: string;
}

export function getPurchaseHistory() {
  return apiClient.get<PurchaseHistoryItem[]>("/purchase/history").then((r) => r.data);
}

export function deleteHistoryEntry(id: string) {
  return apiClient.delete(`/purchase/history/${id}`);
}

export function clearPurchaseHistory() {
  return apiClient.delete("/purchase/history");
}

export function getLiveProduct(itemKey: string) {
  return apiClient
    .get<LiveProduct>(`/purchase/products/${encodeURIComponent(itemKey)}/live`)
    .then((r) => r.data);
}

export function getWishlist() {
  return apiClient.get<WishlistEntry[]>("/purchase/wishlist").then((r) => r.data);
}

export function addToWishlist(itemKey: string) {
  return apiClient.post<WishlistEntry>("/purchase/wishlist", { item_key: itemKey }).then((r) => r.data);
}

export function removeFromWishlist(itemKey: string) {
  return apiClient.delete(`/purchase/wishlist/${encodeURIComponent(itemKey)}`);
}

export function formatTnd(value: number | string | null | undefined): string | null {
  if (value == null) return null;
  const amount = typeof value === "number" ? value : parseFloat(String(value).replace(",", "."));
  if (!Number.isFinite(amount)) return String(value);
  return `${amount.toFixed(amount % 1 === 0 ? 0 : 2).replace(".", ",")} TND`;
}
