import { apiClient } from "@/api/client";
import { ClothingItem } from "@/types/models";

export interface ScheduledOutfit {
  date: string; // YYYY-MM-DD
  item_ids: string[];
  items: ClothingItem[];
  /** The user's avatar wearing the outfit, once rendered (see renderPlannedOutfit). */
  render_image_url?: string | null;
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

/**
 * Renders the user's avatar wearing the day's outfit (virtual try-on, one paid call per
 * garment — roughly a minute). Returns the stored render instantly if nothing changed.
 */
export function renderPlannedOutfit(day: string) {
  return apiClient
    .post<ScheduledOutfit>(`/calendar/${day}/render`, undefined, { timeout: 240000 })
    .then((r) => r.data);
}

export function unplanOutfit(day: string) {
  return apiClient.delete(`/calendar/${day}`);
}
