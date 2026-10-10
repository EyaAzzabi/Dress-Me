import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

export type TripType = "plage" | "business" | "tourisme";

export interface PackingList {
  id: string;
  destination: string;
  duration_days: number;
  trip_type: TripType;
  start_date?: string | null;
  season?: string | null;
  item_ids: string[];
  checked_item_ids: string[];
  items: ClothingItem[];
}

/** startDate (YYYY-MM-DD) is optional: when given it sets the season and pulls in outfits already planned for those days. */
export function createPackingList(destination: string, durationDays: number, tripType: TripType, startDate?: string) {
  return apiClient
    .post<PackingList>("/packing/", { destination, duration_days: durationDays, trip_type: tripType, start_date: startDate })
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
