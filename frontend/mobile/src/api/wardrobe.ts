import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

export function listWardrobeItems() {
  return apiClient.get<ClothingItem[]>("/wardrobe/").then((r) => r.data);
}

export function addWardrobeItem(imageUrl: string) {
  return apiClient
    .post<ClothingItem>("/wardrobe/", { image_url: imageUrl })
    .then((r) => r.data);
}

export function removeWardrobeItem(itemId: string) {
  return apiClient.delete(`/wardrobe/${itemId}`);
}
