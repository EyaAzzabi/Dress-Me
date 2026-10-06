import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

export interface ScheduledOutfit {
  date: string; // YYYY-MM-DD
  item_ids: string[];
  items: ClothingItem[];
}

export function planOutfit(day: string, itemIds: string[]) {
  return apiClient.put<ScheduledOutfit>(`/calendar/${day}`, { item_ids: itemIds }).then((r) => r.data);
}

export function getPlannedOutfit(day: string) {
  return apiClient.get<ScheduledOutfit>(`/calendar/${day}`).then((r) => r.data);
}

export function listPlannedOutfits(start: string, end: string) {
  return apiClient
    .get<ScheduledOutfit[]>("/calendar/", { params: { start, end } })
    .then((r) => r.data);
}

export function unplanOutfit(day: string) {
  return apiClient.delete(`/calendar/${day}`);
}
