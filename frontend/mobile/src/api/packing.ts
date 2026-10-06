import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

export type TripType = "plage" | "business" | "tourisme";

export interface PackingList {
  id: string;
  destination: string;
  duration_days: number;
  trip_type: TripType;
  item_ids: string[];
  checked_item_ids: string[];
  items: ClothingItem[];
}

export function createPackingList(destination: string, durationDays: number, tripType: TripType) {
  return apiClient
    .post<PackingList>("/packing/", { destination, duration_days: durationDays, trip_type: tripType })
    .then((r) => r.data);
}

export function listPackingLists() {
  return apiClient.get<PackingList[]>("/packing/").then((r) => r.data);
}

export function getPackingList(id: string) {
  return apiClient.get<PackingList>(`/packing/${id}`).then((r) => r.data);
}

export function checkPackingItem(id: string, itemId: string, checked: boolean) {
  return apiClient
    .patch<PackingList>(`/packing/${id}/check`, { item_id: itemId, checked })
    .then((r) => r.data);
}

export function deletePackingList(id: string) {
  return apiClient.delete(`/packing/${id}`);
}
