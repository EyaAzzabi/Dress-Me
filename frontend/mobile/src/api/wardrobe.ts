import { isAxiosError } from "axios";
import * as ImageManipulator from "expo-image-manipulator";
import { Platform } from "react-native";

import { apiClient } from "@/api/client";
import { ClothingItem, ItemUsage, Season } from "@/types/models";

export function listWardrobeItems() {
  return apiClient.get<ClothingItem[]>("/wardrobe/").then((r) => r.data);
}

/**
 * Uploads a local photo (e.g. a `file://...` URI from expo-image-picker) to the
 * backend's storage and returns a publicly reachable image_url. Call this BEFORE
 * addWardrobeItem/checkPurchase — the backend's Vision Agent fetches the URL itself
 * over HTTP, so a local device URI isn't usable directly.
 */
export async function uploadPhoto(localUri: string) {
  // Expo SDK 54+ can return original HEIC/AVIF assets from the picker. Convert the
  // bytes themselves to JPEG; changing only the filename/MIME type would leave an
  // unsupported image format for the backend's Pillow pipeline.
  const jpeg = await ImageManipulator.manipulateAsync(localUri, [], {
    compress: 0.85,
    format: ImageManipulator.SaveFormat.JPEG,
  });
  const filename = "photo.jpg";

  const formData = new FormData();
  if (Platform.OS === "web") {
    // On web, expo-image-picker hands back a blob: URL and react-native-web's
    // FormData delegates straight to the browser's — which needs a real
    // File/Blob, not the {uri, name, type} placeholder native RN's FormData
    // polyfill accepts.
    const blob = await (await fetch(jpeg.uri)).blob();
    formData.append("file", blob, filename);
  } else {
    formData.append("file", { uri: jpeg.uri, name: filename, type: "image/jpeg" } as unknown as Blob);
  }

  return apiClient
    .post<{ image_url: string }>("/wardrobe/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data.image_url);
}

/** What POST /wardrobe/ answers (422) when the model isn't sure of a photo's category — often a photo of several pieces. */
export interface LowCategoryConfidence {
  message: string;
  suggested_category: string;
  confidence: number;
}

export function parseLowCategoryConfidence(error: unknown): LowCategoryConfidence | null {
  if (!isAxiosError(error)) return null;
  const detail = error.response?.data?.detail;
  return detail && typeof detail === "object" && detail.code === "low_category_confidence" ? detail : null;
}

/** `category` is the owner's own answer when the model wasn't sure (see parseLowCategoryConfidence). */
export function addWardrobeItem(imageUrl: string, season?: string, category?: string) {
  return apiClient
    .post<ClothingItem>("/wardrobe/", { image_url: imageUrl, season, category })
    .then((r) => r.data);
}

export function updateWardrobeItem(
  itemId: string,
  changes: Partial<Pick<ClothingItem, "category" | "colors" | "style" | "pattern">> & { season?: Season }
) {
  return apiClient.patch<ClothingItem>(`/wardrobe/${itemId}`, changes).then((r) => r.data);
}

export function listWardrobeUsage() {
  return apiClient.get<ItemUsage[]>("/wardrobe/usage").then((r) => r.data);
}

/** "Je l'ai porté": records the item as worn today. */
export function markItemWorn(itemId: string) {
  return apiClient.post<ItemUsage>(`/wardrobe/${itemId}/worn`).then((r) => r.data);
}

export function removeWardrobeItem(itemId: string) {
  return apiClient.delete(`/wardrobe/${itemId}`);
}
