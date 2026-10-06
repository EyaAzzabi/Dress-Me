import { apiClient } from "@/api/client";

export function setAvatar(imageUrl: string) {
  return apiClient.put<{ image_url: string }>("/tryon/avatar", { image_url: imageUrl }).then((r) => r.data);
}

export function tryOnGarment(garmentItemId: string) {
  return apiClient
    .post<{ result_image_url: string }>("/tryon/", { garment_item_id: garmentItemId })
    .then((r) => r.data.result_image_url);
}
