import { Platform } from "react-native";

import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

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
  const filename = localUri.split("/").pop() ?? "photo.jpg";
  const extensionMatch = /\.(\w+)$/.exec(filename);
  const extension = extensionMatch ? extensionMatch[1].toLowerCase() : "jpg";
  const mimeType = extension === "png" ? "image/png" : "image/jpeg";

  const formData = new FormData();
  if (Platform.OS === "web") {
    // On web, expo-image-picker hands back a blob: URL and react-native-web's
    // FormData delegates straight to the browser's — which needs a real
    // File/Blob, not the {uri, name, type} placeholder native RN's FormData
    // polyfill accepts.
    const blob = await (await fetch(localUri)).blob();
    formData.append("file", blob, filename);
  } else {
    formData.append("file", { uri: localUri, name: filename, type: mimeType } as unknown as Blob);
  }

  return apiClient
    .post<{ image_url: string }>("/wardrobe/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data.image_url);
}

export function addWardrobeItem(imageUrl: string, season?: string) {
  return apiClient
    .post<ClothingItem>("/wardrobe/", { image_url: imageUrl, season })
    .then((r) => r.data);
}

export function removeWardrobeItem(itemId: string) {
  return apiClient.delete(`/wardrobe/${itemId}`);
}
