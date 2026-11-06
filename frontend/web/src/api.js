import axios from "axios";
const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";
export const api = axios.create({ baseURL: API_URL });
export function parseLowCategoryConfidence(error) {
    if (!axios.isAxiosError(error))
        return null;
    const detail = error.response?.data?.detail;
    return detail && typeof detail === "object" && detail.code === "low_category_confidence" ? detail : null;
}
export function getApiError(error) {
    if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string")
            return detail;
        if (detail && typeof detail.message === "string")
            return detail.message;
        if (error.response?.status === 0 || !error.response) {
            return "Impossible de joindre le serveur. Vérifie que l’API DressMe est démarrée.";
        }
    }
    return error instanceof Error ? error.message : "Une erreur est survenue. Réessaie.";
}
api.interceptors.request.use((config) => {
    const token = localStorage.getItem("dressme_access_token");
    if (token)
        config.headers.Authorization = `Bearer ${token}`;
    return config;
});
export async function submitOutfitFeedback(outfitId, rating) {
    const { data } = await api.put(`/recommendations/outfits/${outfitId}/feedback`, { rating });
    return data;
}
export function formatTnd(value) {
    if (value == null)
        return null;
    const amount = typeof value === "number" ? value : parseFloat(String(value).replace(",", "."));
    if (!Number.isFinite(amount))
        return String(value);
    return `${amount.toFixed(amount % 1 === 0 ? 0 : 2).replace(".", ",")} TND`;
}
export async function getPurchaseHistory() {
    const { data } = await api.get("/purchase/history");
    return data;
}
export async function deleteHistoryEntry(id) {
    await api.delete(`/purchase/history/${id}`);
}
export async function clearPurchaseHistory() {
    await api.delete("/purchase/history");
}
export async function getWishlist() {
    const { data } = await api.get("/purchase/wishlist");
    return data;
}
export async function addToWishlist(itemKey) {
    const { data } = await api.post("/purchase/wishlist", { item_key: itemKey });
    return data;
}
export async function removeFromWishlist(itemKey) {
    await api.delete(`/purchase/wishlist/${encodeURIComponent(itemKey)}`);
}
export async function uploadPhoto(file) {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post("/wardrobe/upload", form);
    return data.image_url;
}
export async function analyzePhoto(imageUrl) {
    const { data } = await api.post("/wardrobe/analyze", { image_url: imageUrl });
    return data;
}
export async function submitRLHFFeedback(payload) {
    const { data } = await api.post("/rlhf/feedback", payload);
    return data;
}
export async function getRLHFStats(days = 30, limit = 10) {
    const { data } = await api.get(`/rlhf/stats?days=${days}&limit=${limit}`);
    return data;
}
export async function downloadRLHFExport(days, format) {
    const response = await api.get(`/rlhf/stats?days=${days}&format=${format}`, {
        responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `retours_rlhf_${new Date().toISOString().slice(0, 10)}.${format}`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}
