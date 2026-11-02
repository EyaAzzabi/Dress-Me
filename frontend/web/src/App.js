import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, getApiError, formatTnd, getPurchaseHistory, deleteHistoryEntry, clearPurchaseHistory, getWishlist, addToWishlist, removeFromWishlist, uploadPhoto, analyzePhoto, parseLowCategoryConfidence, submitOutfitFeedback, getRLHFStats, submitRLHFFeedback, downloadRLHFExport, } from "./api";
import "./styles.css";
import LlmAssistant from "./LlmAssistant";
const NAV_ITEMS = [
    { id: "overview", label: "Accueil", icon: "⌂", group: "TON ESPACE" },
    { id: "wardrobe", label: "Mon dressing", icon: "◈", group: "TON ESPACE" },
    { id: "outfits", label: "Idées de looks", icon: "✧", group: "TON ESPACE" },
    { id: "calendar", label: "Calendrier", icon: "▦", group: "TON ESPACE" },
    { id: "profile", label: "Mon style", icon: "◎", group: "DÉCOUVRIR" },
    { id: "assistant", label: "Assistant IA", icon: "✦", group: "DÉCOUVRIR" },
    { id: "packing", label: "Ma valise", icon: "▣", group: "DÉCOUVRIR" },
    { id: "purchase", label: "J’achète ou pas ?", icon: "♡", group: "DÉCOUVRIR" },
    { id: "tryon", label: "Essayage virtuel", icon: "✦", group: "DÉCOUVRIR" },
    { id: "donation", label: "Dons & Seconde vie", icon: "🎁", group: "DÉCOUVRIR" },
    { id: "rlhf", label: "Suivi RLHF", icon: "◉", group: "DÉCOUVRIR" },
];
const SCREEN_COPY = {
    overview: { title: "Bonjour, bienvenue chez toi ✨", subtitle: "Ton style, tes pièces et tes inspirations au même endroit." },
    wardrobe: { title: "Mon dressing", subtitle: "Toutes tes pièces réunies, prêtes à composer de nouveaux looks." },
    outfits: { title: "Idées de looks", subtitle: "Des tenues pensées selon l’occasion, la saison et la météo." },
    calendar: { title: "Mon calendrier", subtitle: "Prépare tes tenues et retrouve-les au bon moment." },
    profile: { title: "Mon style", subtitle: "Découvre ce que ton dressing révèle de tes préférences." },
    assistant: { title: "Mon assistant style", subtitle: "Ton profil, tes tenues, tes envies : des explications qui te ressemblent." },
    packing: { title: "Ma valise", subtitle: "Prépare une sélection de pièces pour ton prochain voyage." },
    purchase: { title: "J’achète ou pas ?", subtitle: "Vérifie si une nouvelle pièce s’accorde à ton dressing." },
    tryon: { title: "Essayage virtuel", subtitle: "Visualise une pièce sur ta photo avant de l’ajouter à ton look." },
    donation: { title: "Dons & Seconde vie", subtitle: "Offre une seconde vie à tes vêtements et découvre où les donner en Tunisie." },
    rlhf: { title: "Tableau de bord RLHF", subtitle: "Suis les retours et l'évolution des recommandations." },
};
const OCCASIONS = [
    ["quotidien", "Quotidien"],
    ["travail", "Travail"],
    ["sortie", "Sortie"],
    ["soirée", "Soirée"],
    ["événement", "Événement"],
];
const CITIES = ["Tunis", "Sousse", "Sfax", "Djerba"];
const WARDROBE_CATEGORIES = [["haut", "Haut"], ["bas", "Bas"], ["robe", "Robe"], ["veste", "Veste"], ["chaussures", "Chaussures"], ["sac", "Sac"], ["accessoire", "Accessoire"]];
const SEASONS = ["printemps", "été", "automne", "hiver"];
// Wardrobe-item seasons: same vocabulary the backend validates (ClothingItem season).
const ITEM_SEASONS = [["ete", "☀️ Été"], ["hiver", "❄️ Hiver"], ["mi_saison", "🍂 Mi-saison"], ["toutes_saisons", "🌍 Toutes saisons"]];
const itemSeasonLabel = (value) => ITEM_SEASONS.find(([key]) => key === value)?.[1] ?? null;
const WARDROBE_FAVORITES_KEY = "dressme_wardrobe_favorites";
const OUTFIT_FAVORITES_KEY = "dressme_favorite_outfits";
const DONATIONS_STORAGE_KEY = "dressme_donations_list";
function todayLocal() {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}
function dayString(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function readIds(key) {
    try {
        const value = JSON.parse(localStorage.getItem(key) ?? "[]");
        return Array.isArray(value) && value.every((id) => typeof id === "string") ? value : [];
    }
    catch {
        return [];
    }
}
function categoryLabel(value) {
    if (!value)
        return "Autre";
    return value.charAt(0).toLocaleUpperCase("fr") + value.slice(1).replace(/_/g, " ");
}
function Avatar({ user, size = "normal" }) {
    const initials = (user?.full_name ?? user?.email ?? "DM").trim().slice(0, 1).toLocaleUpperCase("fr");
    return user?.avatar_photo_url
        ? _jsx("img", { className: `avatar avatar-${size}`, src: user.avatar_photo_url, alt: "Photo de profil" })
        : _jsx("span", { className: `avatar avatar-placeholder avatar-${size}`, "aria-label": "Profil", children: initials || "D" });
}
function AuthScreen({ onAuthenticated, initialError }) {
    const [mode, setMode] = useState("login");
    const [fullName, setFullName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(initialError);
    async function submit(event) {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
            if (mode === "register") {
                await api.post("/auth/register", {
                    email: email.trim(),
                    password,
                    full_name: fullName.trim() || undefined,
                });
            }
            const { data } = await api.post("/auth/login", {
                email: email.trim(),
                password,
            });
            onAuthenticated(data.access_token);
        }
        catch (cause) {
            setError(getApiError(cause));
        }
        finally {
            setBusy(false);
        }
    }
    return (_jsxs("main", { className: "auth-layout", children: [_jsxs("section", { className: "auth-story", children: [_jsx("a", { className: "auth-brand", href: "#connexion", "aria-label": "DressMe", children: _jsx("img", { src: "/dressme-logo.png", alt: "DressMe \u2014 A smarter wardrobe for a brighter you" }) }), _jsx("img", { className: "auth-story-photo", src: "/sidi-bou-style-inspiration.jpg", alt: "" }), _jsxs("div", { className: "auth-story-copy", children: [_jsx("span", { className: "eyebrow", children: "\u2726 TON STYLE, ENFIN \u00C0 TOI" }), _jsxs("h1", { children: ["Le plaisir de s\u2019habiller, ", _jsx("em", { children: "chaque jour." })] }), _jsx("p", { children: "Organise ton dressing, compose des looks qui te ressemblent et pr\u00E9pare tes prochaines aventures." }), _jsxs("div", { className: "auth-points", children: [_jsxs("span", { children: [_jsx("i", { children: "\u2713" }), " Ton dressing \u00E0 port\u00E9e de main"] }), _jsxs("span", { children: [_jsx("i", { children: "\u2713" }), " Des id\u00E9es selon tes envies"] }), _jsxs("span", { children: [_jsx("i", { children: "\u2713" }), " Une touche de Tunisie dans ton style"] })] })] }), _jsx("p", { className: "auth-footer", children: "DressMe \u00B7 Avec amour, depuis la Tunisie" })] }), _jsx("section", { className: "auth-panel", id: "connexion", children: _jsxs("form", { className: "auth-card", onSubmit: submit, children: [_jsx("span", { className: "auth-card-mark", children: "\u2727" }), _jsx("p", { className: "eyebrow", children: mode === "login" ? "RAVIE DE TE REVOIR" : "BIENVENUE DANS TON ESPACE" }), _jsx("h2", { children: mode === "login" ? "Connecte-toi" : "Crée ton compte" }), _jsx("p", { className: "auth-subtitle", children: mode === "login" ? "Retrouve ton dressing et tes inspirations." : "Quelques secondes pour commencer ton dressing." }), mode === "register" && (_jsxs("label", { className: "field", children: [_jsx("span", { children: "Ton nom" }), _jsx("input", { autoComplete: "name", value: fullName, onChange: (event) => setFullName(event.target.value), placeholder: "Ex. Amira Ben Ali" })] })), _jsxs("label", { className: "field", children: [_jsx("span", { children: "Adresse e-mail" }), _jsx("input", { required: true, type: "email", autoComplete: "email", value: email, onChange: (event) => setEmail(event.target.value), placeholder: "toi@exemple.com" })] }), _jsxs("label", { className: "field", children: [_jsx("span", { children: "Mot de passe" }), _jsx("input", { required: true, type: "password", minLength: 6, autoComplete: mode === "login" ? "current-password" : "new-password", value: password, onChange: (event) => setPassword(event.target.value), placeholder: "Au moins 6 caract\u00E8res" })] }), error && _jsx("p", { className: "form-error", role: "alert", children: error }), _jsxs("button", { className: "button button-primary auth-submit", type: "submit", disabled: busy, children: [busy ? "Un instant…" : mode === "login" ? "Entrer dans mon dressing" : "Créer mon compte", !busy && _jsx("span", { "aria-hidden": "true", children: "\u2192" })] }), _jsxs("p", { className: "auth-switch", children: [mode === "login" ? "Pas encore de compte ?" : "Tu as déjà un compte ?", _jsx("button", { type: "button", onClick: () => { setMode(mode === "login" ? "register" : "login"); setError(""); }, children: mode === "login" ? "Créer mon compte" : "Me connecter" })] }), _jsx("p", { className: "auth-privacy", children: "Tes donn\u00E9es restent priv\u00E9es et li\u00E9es \u00E0 ton compte." })] }) })] }));
}
export default function App() {
    const [token, setToken] = useState(() => localStorage.getItem("dressme_access_token") ?? "");
    const [user, setUser] = useState(null);
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem("dressme_theme") || "light";
    });
    const [screen, setScreen] = useState("overview");
    const [items, setItems] = useState([]);
    const [usage, setUsage] = useState({});
    const [categoryPrompt, setCategoryPrompt] = useState(null);
    const [ingestionReview, setIngestionReview] = useState(null);
    const [outfits, setOutfits] = useState([]);
    const [scheduled, setScheduled] = useState([]);
    const [profile, setProfile] = useState(null);
    const [packingLists, setPackingLists] = useState([]);
    const [wardrobeFavorites, setWardrobeFavorites] = useState(() => readIds(WARDROBE_FAVORITES_KEY));
    const [outfitFavorites, setOutfitFavorites] = useState(() => readIds(OUTFIT_FAVORITES_KEY));
    const [donations, setDonations] = useState(() => {
        try {
            const raw = localStorage.getItem(DONATIONS_STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        }
        catch {
            return [];
        }
    });
    const [donationModalItem, setDonationModalItem] = useState(null);
    const [loading, setLoading] = useState(Boolean(token));
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [menuOpen, setMenuOpen] = useState(false);
    const [monthAnchor, setMonthAnchor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
    const [rlhfStats, setRlhfStats] = useState(null);
    const [rlhfDays, setRlhfDays] = useState(30);
    useEffect(() => {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem("dressme_theme", theme);
    }, [theme]);
    const today = todayLocal();
    const selectedNav = NAV_ITEMS.find((item) => item.id === screen);
    const displayName = user?.full_name?.split(/\s+/)[0] || "toi";
    const itemsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
    useEffect(() => {
        if (!token || screen !== "wardrobe")
            return;
        let active = true;
        api.get("/wardrobe/usage")
            .then(({ data }) => { if (active)
            setUsage(Object.fromEntries(data.map((entry) => [entry.item_id, entry]))); })
            .catch(() => { });
        return () => { active = false; };
    }, [token, screen]);
    useEffect(() => {
        if (!token) {
            setLoading(false);
            return;
        }
        let active = true;
        setLoading(true);
        Promise.all([
            api.get("/auth/me"),
            api.get("/wardrobe/"),
        ])
            .then(([me, wardrobe]) => {
            if (!active)
                return;
            setUser(me.data);
            setItems(wardrobe.data);
            const ids = new Set(wardrobe.data.map((item) => item.id));
            const validFavorites = readIds(WARDROBE_FAVORITES_KEY).filter((id) => ids.has(id));
            setWardrobeFavorites(validFavorites);
            localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(validFavorites));
        })
            .catch((cause) => {
            if (!active)
                return;
            localStorage.removeItem("dressme_access_token");
            setToken("");
            setUser(null);
            setError(getApiError(cause));
        })
            .finally(() => active && setLoading(false));
        return () => { active = false; };
    }, [token]);
    useEffect(() => {
        if (!token || screen === "overview")
            return;
        let active = true;
        setError("");
        setLoading(true);
        const finish = () => { if (active)
            setLoading(false); };
        if (screen === "wardrobe") {
            api.get("/wardrobe/")
                .then(({ data }) => { if (active)
                setItems(data); })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else if (screen === "outfits") {
            api.get("/recommendations/outfits")
                .then(({ data }) => { if (active)
                setOutfits(data); })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else if (screen === "calendar") {
            const start = dayString(monthAnchor);
            const end = dayString(new Date(monthAnchor.getFullYear(), monthAnchor.getMonth() + 1, 0));
            api.get("/calendar/", { params: { start, end } })
                .then(({ data }) => { if (active)
                setScheduled(data); })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else if (screen === "profile") {
            Promise.all([api.get("/style-profile/"), api.get("/auth/me")])
                .then(([style, me]) => {
                if (!active)
                    return;
                setProfile(style.data);
                setUser(me.data);
            })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else if (screen === "packing") {
            api.get("/packing/")
                .then(({ data }) => { if (active)
                setPackingLists(data); })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else if (screen === "tryon") {
            Promise.all([api.get("/auth/me"), api.get("/wardrobe/")])
                .then(([me, wardrobe]) => {
                if (!active)
                    return;
                setUser(me.data);
                setItems(wardrobe.data);
            })
                .catch((cause) => { if (active)
                setError(getApiError(cause)); })
                .finally(finish);
        }
        else {
            finish();
        }
        return () => { active = false; };
    }, [monthAnchor, screen, token]);
    useEffect(() => {
        if (!token || screen !== "overview")
            return;
        let active = true;
        const start = dayString(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
        const end = dayString(new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0));
        Promise.allSettled([
            api.get("/style-profile/"),
            api.get("/recommendations/outfits"),
            api.get("/calendar/", { params: { start, end } }),
            api.get("/packing/"),
        ]).then(([style, looks, calendar, packing]) => {
            if (!active)
                return;
            if (style.status === "fulfilled")
                setProfile(style.value.data);
            if (looks.status === "fulfilled")
                setOutfits(looks.value.data);
            if (calendar.status === "fulfilled")
                setScheduled(calendar.value.data);
            if (packing.status === "fulfilled")
                setPackingLists(packing.value.data);
        });
        return () => { active = false; };
    }, [screen, token]);
    useEffect(() => {
        if (!token || screen !== "rlhf")
            return;
        let active = true;
        setLoading(true);
        getRLHFStats(rlhfDays)
            .then((data) => { if (active)
            setRlhfStats(data); })
            .catch((cause) => { if (active)
            reportError(cause); })
            .finally(() => { if (active)
            setLoading(false); });
        return () => { active = false; };
    }, [screen, token, rlhfDays]);
    function authenticate(accessToken) {
        localStorage.setItem("dressme_access_token", accessToken);
        setError("");
        setToken(accessToken);
        setScreen("overview");
    }
    function signOut() {
        localStorage.removeItem("dressme_access_token");
        setToken("");
        setUser(null);
        setItems([]);
        setOutfits([]);
        setScheduled([]);
        setProfile(null);
        setPackingLists([]);
        setNotice("");
        setError("");
    }
    function navigate(target) {
        setScreen(target);
        setMenuOpen(false);
        setError("");
        setNotice("");
    }
    function reportError(cause) {
        setError(getApiError(cause));
        setNotice("");
    }
    async function submitItem(imageUrl, season, category) {
        const { data } = await api.post("/wardrobe/", { image_url: imageUrl, season: season || undefined, category });
        setItems((current) => [data, ...current]);
        setNotice("La pièce a été analysée et ajoutée à ton dressing.");
    }
    const [uploadStage, setUploadStage] = useState("");
    const firstPhotoNoticeShown = useRef(sessionStorage.getItem("dressme_first_photo_notice") === "shown");
    async function addItem(file, season) {
        setBusy("wardrobe-upload");
        setUploadStage("Envoi de ta photo…");
        setError("");
        try {
            const imageUrl = await uploadPhoto(file);
            const firstPhotoNotice = firstPhotoNoticeShown.current ? "" : " Le premier ajout peut être plus long.";
            firstPhotoNoticeShown.current = true;
            sessionStorage.setItem("dressme_first_photo_notice", "shown");
            setUploadStage(`Photo reçue. Analyse du vêtement en cours…${firstPhotoNotice}`);
            try {
                const analysis = await analyzePhoto(imageUrl);
                const topExtracted = analysis.segmentation?.person_detected && analysis.segmentation.extracted_garments?.length
                    ? analysis.segmentation.extracted_garments[0]
                    : null;
                setIngestionReview({
                    imageUrl,
                    analysis,
                    selectedCategory: topExtracted?.category || analysis.category || "haut",
                    selectedSeason: season || analysis.season || "toutes_saisons",
                });
            }
            catch (analyzeErr) {
                // Fallback to direct submit if analyze endpoint wasn't available
                try {
                    await submitItem(imageUrl, season);
                }
                catch (cause) {
                    const unsure = parseLowCategoryConfidence(cause);
                    if (!unsure)
                        throw cause;
                    setCategoryPrompt({ ...unsure, imageUrl, season });
                }
            }
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function confirmIngestion(category, season, finalImageUrl) {
        if (!ingestionReview)
            return;
        setBusy("wardrobe-upload");
        try {
            await submitItem(finalImageUrl || ingestionReview.imageUrl, season, category);
            setIngestionReview(null);
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function confirmCategory(category) {
        if (!categoryPrompt)
            return;
        setBusy("wardrobe-upload");
        try {
            await submitItem(categoryPrompt.imageUrl, categoryPrompt.season, category);
            setCategoryPrompt(null);
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function markWorn(item) {
        try {
            const { data } = await api.post(`/wardrobe/${item.id}/worn`);
            setUsage((current) => ({ ...current, [data.item_id]: data }));
            setNotice("C'est noté : pièce portée aujourd'hui.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function changeSeason(item, season) {
        try {
            const { data } = await api.patch(`/wardrobe/${item.id}`, { season });
            setItems((current) => current.map((currentItem) => (currentItem.id === data.id ? data : currentItem)));
            setNotice("La saison de la pièce a été enregistrée.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    function saveDonations(next) {
        setDonations(next);
        localStorage.setItem(DONATIONS_STORAGE_KEY, JSON.stringify(next));
    }
    async function requestDeleteItem(item) {
        setDonationModalItem(item);
    }
    async function handleTransferToDonation(item) {
        setDonationModalItem(null);
        try {
            const newDonation = {
                id: "don_" + Date.now() + "_" + Math.random().toString(36).slice(2, 7),
                item,
                addedAt: new Date().toISOString(),
                status: "pending",
                condition: "bon_etat",
            };
            const nextDonations = [newDonation, ...donations];
            saveDonations(nextDonations);
            await api.delete(`/wardrobe/${item.id}`);
            setItems((current) => current.filter((currentItem) => currentItem.id !== item.id));
            const nextFavs = wardrobeFavorites.filter((id) => id !== item.id);
            setWardrobeFavorites(nextFavs);
            localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(nextFavs));
            setNotice("🎁 Pièce ajoutée à ta boîte de dons !");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function handlePermanentDelete(item) {
        setDonationModalItem(null);
        try {
            await api.delete(`/wardrobe/${item.id}`);
            setItems((current) => current.filter((currentItem) => currentItem.id !== item.id));
            const nextFavs = wardrobeFavorites.filter((id) => id !== item.id);
            setWardrobeFavorites(nextFavs);
            localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(nextFavs));
            setNotice("La pièce a été définitivement supprimée.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function restoreDonationToWardrobe(donation) {
        try {
            const { data } = await api.post("/wardrobe/", { image_url: donation.item.image_url });
            setItems((current) => [data, ...current]);
            const next = donations.filter((d) => d.id !== donation.id);
            saveDonations(next);
            setNotice("✨ La pièce est de retour dans ton dressing !");
        }
        catch {
            setItems((current) => [donation.item, ...current]);
            const next = donations.filter((d) => d.id !== donation.id);
            saveDonations(next);
            setNotice("✨ La pièce a été replacée dans ton dressing.");
        }
    }
    function markDonated(donationId, orgName) {
        const next = donations.map((d) => d.id === donationId
            ? { ...d, status: (d.status === "donated" ? "pending" : "donated"), targetOrg: orgName ?? d.targetOrg }
            : d);
        saveDonations(next);
        setNotice("🎉 Félicitations pour ce geste solidaire et éco-responsable !");
    }
    function updateDonationCondition(donationId, condition) {
        const next = donations.map((d) => (d.id === donationId ? { ...d, condition } : d));
        saveDonations(next);
    }
    function removeDonation(donationId) {
        const next = donations.filter((d) => d.id !== donationId);
        saveDonations(next);
        setNotice("La pièce a été retirée de la boîte de dons.");
    }
    function toggleFavorite(id, kind) {
        const current = kind === "wardrobe" ? wardrobeFavorites : outfitFavorites;
        const next = current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id];
        if (kind === "wardrobe") {
            setWardrobeFavorites(next);
            localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(next));
        }
        else {
            setOutfitFavorites(next);
            localStorage.setItem(OUTFIT_FAVORITES_KEY, JSON.stringify(next));
        }
    }
    async function generateLooks(event) {
        event.preventDefault();
        setBusy("looks");
        setError("");
        try {
            const form = new FormData(event.currentTarget);
            const { data } = await api.post("/recommendations/outfits", {
                occasion: String(form.get("occasion") || "") || undefined,
                request_text: String(form.get("request_text") || "").trim() || undefined,
                city: String(form.get("city") || "") || undefined,
                season: String(form.get("season") || "") || undefined,
            });
            setOutfits(data.outfits);
            const alignment = data.evaluation?.feedback_alignment_at_k;
            const evaluationText = alignment == null
                ? ""
                : ` Alignement avec tes retours précédents : ${alignment >= 0 ? "+" : ""}${alignment.toFixed(2)}.`;
            setNotice(`${data.outfits.length} idée${data.outfits.length === 1 ? "" : "s"} de tenue proposée${data.outfits.length === 1 ? "" : "s"}.${evaluationText}`);
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function saveOutfitFeedback(outfitId, rating) {
        setBusy(`outfit-feedback:${outfitId}`);
        setError("");
        try {
            const updated = await submitOutfitFeedback(outfitId, rating);
            setOutfits((current) => current.map((outfit) => outfit.id === updated.id ? updated : outfit));
            setNotice(rating === "worn"
                ? "Merci, cette tenue est notée comme portée et ton historique est actualisé."
                : rating === null ? "Ton avis sur cette tenue a été retiré." : "Merci, ton avis aidera à personnaliser les prochaines idées.");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function saveRLHFRating(outfitId, rating) {
        setBusy(`rlhf-rate:${outfitId}`);
        setError("");
        try {
            await submitRLHFFeedback({ outfit_id: outfitId, rating });
            setNotice("Merci\u00a0! Ton avis améliore les recommandations.");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function scheduleOutfit(outfit, date) {
        if (!date) {
            setError("Choisis une date pour planifier cette tenue.");
            return;
        }
        try {
            const { data } = await api.put(`/calendar/${date}`, { item_ids: outfit.item_ids });
            setScheduled((current) => [...current.filter((entry) => entry.date !== date), data].sort((a, b) => a.date.localeCompare(b.date)));
            setNotice(`Tenue planifiée pour le ${new Date(`${date}T12:00:00`).toLocaleDateString("fr-TN", { day: "numeric", month: "long" })}.`);
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function saveCalendarOutfit(date, selectedIds) {
        try {
            const { data } = await api.put(`/calendar/${date}`, { item_ids: selectedIds });
            setScheduled((current) => [...current.filter((entry) => entry.date !== date), data]);
            setNotice("Ta tenue est enregistrée dans le calendrier.");
            return data;
        }
        catch (cause) {
            reportError(cause);
            throw cause;
        }
    }
    async function renderCalendarOutfit(date) {
        setError("");
        try {
            // Slow on purpose: one paid try-on call per garment, so it only runs when asked.
            const { data } = await api.post(`/calendar/${date}/render`);
            setScheduled((current) => current.map((entry) => (entry.date === data.date ? data : entry)));
            setNotice("Ton avatar porte la tenue du jour.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function removeCalendarOutfit(date) {
        try {
            await api.delete(`/calendar/${date}`);
            setScheduled((current) => current.filter((entry) => entry.date !== date));
            setNotice("La tenue a été retirée du calendrier.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function createPacking(event) {
        event.preventDefault();
        setBusy("packing-create");
        setError("");
        try {
            const formElement = event.currentTarget;
            const form = new FormData(formElement);
            const { data } = await api.post("/packing/", {
                destination: String(form.get("destination")).trim(),
                duration_days: Number(form.get("duration")),
                trip_type: String(form.get("tripType")),
                start_date: String(form.get("startDate") || "") || undefined,
            });
            setPackingLists((current) => [data, ...current]);
            formElement.reset();
            setNotice("Ta liste de valise est prête.");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function togglePackedItem(list, itemId) {
        try {
            const { data } = await api.patch(`/packing/${list.id}/check`, {
                item_id: itemId,
                checked: !list.checked_item_ids.includes(itemId),
            });
            setPackingLists((current) => current.map((entry) => entry.id === list.id ? data : entry));
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function deletePackingList(id) {
        if (!window.confirm("Supprimer cette liste de voyage ?"))
            return;
        try {
            await api.delete(`/packing/${id}`);
            setPackingLists((current) => current.filter((entry) => entry.id !== id));
            setNotice("La liste de voyage a été supprimée.");
        }
        catch (cause) {
            reportError(cause);
        }
    }
    async function uploadAvatar(file) {
        setBusy("avatar");
        setError("");
        try {
            const imageUrl = await uploadPhoto(file);
            await api.put("/tryon/avatar", { image_url: imageUrl });
            setUser((current) => current ? { ...current, avatar_photo_url: imageUrl } : current);
            setNotice("Ta photo de référence est enregistrée.");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function runPurchaseCheck(file) {
        setBusy("purchase");
        setError("");
        try {
            const imageUrl = await uploadPhoto(file);
            const { data } = await api.post("/purchase/check", { image_url: imageUrl });
            setPurchaseResult(data);
            setNotice("");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    const [purchaseResult, setPurchaseResult] = useState(null);
    const [tryOnResult, setTryOnResult] = useState("");
    const [selectedTryOnItems, setSelectedTryOnItems] = useState([]);
    // Real-time weather for topbar only
    const [topbarWeather, setTopbarWeather] = useState({ temp: 22, icon: "🌤️" });
    useEffect(() => {
        api.get("/weather/Tunis").then(({ data }) => setTopbarWeather({ temp: data.temp, icon: data.icon })).catch(() => { });
    }, []);
    function toggleTryOnItem(id) {
        setSelectedTryOnItems((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
    }
    function clearTryOnSelection() {
        setSelectedTryOnItems([]);
    }
    async function selectPresetAvatar(imageUrl) {
        setBusy("avatar");
        setError("");
        try {
            await api.put("/tryon/avatar", { image_url: imageUrl });
            setUser((current) => current ? { ...current, avatar_photo_url: imageUrl } : current);
            setNotice("Mannequin sélectionné avec succès ! ✨");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    async function generateTryOn() {
        if (selectedTryOnItems.length === 0)
            return;
        setBusy("tryon");
        setError("");
        setTryOnResult("");
        try {
            const payload = selectedTryOnItems.length === 1
                ? { garment_item_id: selectedTryOnItems[0] }
                : { garment_item_ids: selectedTryOnItems };
            const { data } = await api.post("/tryon/", payload);
            setTryOnResult(data.result_image_url);
            setNotice("Rendu d’essayage virtuel réussi ! ✨");
        }
        catch (cause) {
            reportError(cause);
        }
        finally {
            setBusy("");
        }
    }
    if (!token)
        return _jsx(AuthScreen, { onAuthenticated: authenticate, initialError: error });
    if (loading && !user)
        return _jsxs("main", { className: "app-loading", children: [_jsx("span", { className: "loading-mark", children: "D" }), _jsx("p", { children: "Ton espace DressMe s\u2019ouvre\u2026" })] });
    return (_jsxs("div", { className: "workspace", children: [_jsxs("aside", { className: `sidebar${menuOpen ? " sidebar-open" : ""}`, children: [_jsx("a", { className: "sidebar-brand", href: "#accueil", onClick: (event) => { event.preventDefault(); navigate("overview"); }, children: _jsx("img", { src: "/dressme-logo.png", alt: "DressMe \u2014 A smarter wardrobe for a brighter you" }) }), _jsxs("div", { className: "sidebar-profile", children: [_jsx(Avatar, { user: user }), _jsxs("div", { children: [_jsx("strong", { children: displayName }), _jsx("span", { children: "Mon espace personnel" })] }), _jsx("span", { className: "online-dot", "aria-label": "Connect\u00E9e" })] }), _jsx("nav", { className: "sidebar-nav", "aria-label": "Navigation de l\u2019application", children: ["TON ESPACE", "DÉCOUVRIR"].map((group) => (_jsxs("div", { className: "nav-group", children: [_jsx("p", { children: group }), NAV_ITEMS.filter((entry) => entry.group === group).map((entry) => (_jsxs("button", { className: `nav-link${screen === entry.id ? " nav-link-active" : ""}`, type: "button", onClick: () => navigate(entry.id), children: [_jsx("span", { className: "nav-icon", children: entry.icon }), _jsx("span", { children: entry.label }), entry.id === "wardrobe" && items.length > 0 && _jsx("span", { className: "nav-count", children: items.length })] }, entry.id)))] }, group))) }), _jsxs("div", { className: "sidebar-bottom", children: [_jsxs("div", { className: "sidebar-note", children: [_jsx("span", { children: "\u2726" }), _jsxs("p", { children: ["Le chic d\u2019ici,", _jsx("br", {}), _jsx("b", { children: "le style qui va partout." })] })] }), _jsxs("button", { type: "button", className: "signout-button", onClick: signOut, children: ["\u21AA ", _jsx("span", { children: "Se d\u00E9connecter" })] })] })] }), menuOpen && _jsx("button", { className: "sidebar-backdrop", "aria-label": "Fermer le menu", type: "button", onClick: () => setMenuOpen(false) }), _jsxs("main", { className: "main-panel", children: [_jsxs("header", { className: "topbar", children: [_jsx("button", { type: "button", className: "mobile-menu-toggle", "aria-label": "Ouvrir le menu", onClick: () => setMenuOpen(true), children: "\u2630" }), _jsxs("div", { className: "breadcrumb", children: [_jsx("span", { className: "brand-dot", children: "\u2726" }), _jsx("span", { children: "DressMe" }), _jsx("b", { children: "/" }), _jsx("strong", { children: selectedNav?.label ?? "Accueil" })] }), _jsxs("div", { className: "topbar-right", children: [_jsxs("span", { className: "weather-chip", title: "M\u00E9t\u00E9o actuelle en Tunisie", children: [_jsx("span", { className: "weather-icon", children: topbarWeather.icon }), " ", topbarWeather.temp, "\u00B0C"] }), _jsx("button", { type: "button", className: "theme-toggle-btn", onClick: () => setTheme((t) => (t === "light" ? "dark" : "light")), title: theme === "light" ? "Passer en mode sombre" : "Passer en mode clair", "aria-label": "Basculer le th\u00E8me", children: theme === "light" ? "🌙" : "☀️" }), _jsxs("label", { className: `topbar-quick-add${busy === "wardrobe-upload" ? " is-disabled" : ""}`, title: "Ajouter une nouvelle pi\u00E8ce rapidement", children: [_jsx("span", { children: "\uFF0B Ajouter" }), _jsx("input", { type: "file", accept: "image/*", disabled: busy === "wardrobe-upload", onChange: (event) => {
                                                    const file = event.target.files?.[0];
                                                    if (file)
                                                        void addItem(file, "");
                                                    event.target.value = "";
                                                } })] }), _jsx("button", { className: "topbar-avatar-button", type: "button", onClick: () => navigate("profile"), "aria-label": "Ouvrir mon profil", children: _jsx(Avatar, { user: user }) })] })] }), screen === "overview" && (_jsxs("section", { className: "workspace-hero", "aria-label": "DressMe, avec amour depuis la Tunisie", children: [_jsx("img", { className: "workspace-hero-photo", src: "/sidi-bou-style-inspiration.jpg", alt: "" }), _jsx("div", { className: "workspace-hero-content", children: _jsxs("div", { children: [_jsx("span", { className: "hero-pill", children: "TUNIS \u00B7 SIDI BOU SA\u00CFD \u2726" }), _jsx("h2", { children: "Le chic d\u2019ici, le style qui va partout." }), _jsx("p", { children: "Ton assistant personnel aliment\u00E9 par l'IA pour sublimer chaque tenue au quotidien." })] }) })] })), _jsxs("div", { className: "page-content", children: [screen === "wardrobe" && busy === "wardrobe-upload" && _jsxs("div", { className: "content-card", role: "status", children: [_jsx("p", { children: uploadStage }), _jsx("button", { type: "button", className: "text-button", onClick: () => navigate("assistant"), children: "Tester l\u2019assistant IA pendant l\u2019attente \u2192" })] }), error && _jsxs("div", { className: "alert alert-error", role: "alert", children: [_jsx("span", { children: "!" }), _jsx("p", { children: error }), _jsx("button", { type: "button", "aria-label": "Fermer l\u2019erreur", onClick: () => setError(""), children: "\u00D7" })] }), notice && _jsxs("div", { className: "alert alert-success", role: "status", children: [_jsx("span", { children: "\u2713" }), _jsx("p", { children: notice }), _jsx("button", { type: "button", "aria-label": "Fermer le message", onClick: () => setNotice(""), children: "\u00D7" })] }), screen === "overview" && (_jsxs(_Fragment, { children: [_jsx(PageHeading, { title: `Bonjour ${displayName} ✨`, subtitle: "Ton style, tes pi\u00E8ces et tes inspirations au m\u00EAme endroit." }), _jsxs("section", { className: "welcome-banner", children: [_jsxs("div", { className: "welcome-copy", children: [_jsx("span", { className: "eyebrow", children: "UN DRESSING QUI TE RESSEMBLE" }), _jsxs("h2", { children: ["Pr\u00EAte \u00E0 composer ", _jsx("em", { children: "ton prochain look\u00A0?" })] }), _jsx("p", { children: "Explore tes pi\u00E8ces et laisse-toi inspirer par des associations faites pour toi." }), _jsxs("button", { className: "button button-primary", type: "button", onClick: () => navigate("outfits"), children: ["Trouver une tenue ", _jsx("span", { children: "\u2192" })] })] }), _jsx("img", { className: "welcome-photo", src: "/tunisian-wardrobe-inspiration.jpg", alt: "Un coin dressing inspir\u00E9 par Sidi Bou Sa\u00EFd" }), _jsx("span", { className: "welcome-stamp", children: "\u0635\u0646\u0639 \u0628\u062D\u0628 \u2726" })] }), _jsxs("div", { className: "stats-cards", children: [_jsxs("button", { type: "button", className: "summary-card", onClick: () => navigate("wardrobe"), children: [_jsx("span", { className: "summary-icon pink", children: "\u25C8" }), _jsx("span", { className: "summary-label", children: "Dans mon dressing" }), _jsx("strong", { children: items.length }), _jsxs("small", { children: ["pi\u00E8ce", items.length === 1 ? "" : "s", " au total ", _jsx("b", { children: "\u2192" })] })] }), _jsxs("button", { type: "button", className: "summary-card", onClick: () => navigate("outfits"), children: [_jsx("span", { className: "summary-icon gold", children: "\u2727" }), _jsx("span", { className: "summary-label", children: "Id\u00E9es de looks" }), _jsx("strong", { children: outfits.length }), _jsxs("small", { children: ["tenue", outfits.length === 1 ? "" : "s", " disponible", outfits.length === 1 ? "" : "s", " ", _jsx("b", { children: "\u2192" })] })] }), _jsxs("button", { type: "button", className: "summary-card", onClick: () => navigate("calendar"), children: [_jsx("span", { className: "summary-icon blue", children: "\u25A6" }), _jsx("span", { className: "summary-label", children: "Looks planifi\u00E9s" }), _jsx("strong", { children: scheduled.length }), _jsxs("small", { children: ["ce mois-ci ", _jsx("b", { children: "\u2192" })] })] }), _jsxs("button", { type: "button", className: "summary-card", onClick: () => navigate("packing"), children: [_jsx("span", { className: "summary-icon peach", children: "\u25A3" }), _jsx("span", { className: "summary-label", children: "Prochain voyage" }), _jsx("strong", { children: packingLists.length }), _jsxs("small", { children: ["liste", packingLists.length === 1 ? "" : "s", " de valise ", _jsx("b", { children: "\u2192" })] })] })] }), _jsxs("div", { className: "overview-grid", children: [_jsxs("section", { className: "content-card", children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "TES PROCHAINES TENUES" }), _jsx("h3", { children: "Au programme" })] }), _jsx("button", { type: "button", className: "text-button", onClick: () => navigate("calendar"), children: "Tout voir \u2192" })] }), scheduled.length === 0 ? _jsx(EmptyState, { icon: "\u25A6", title: "Ton calendrier est encore libre", text: "Planifie un look pour gagner du temps les matins press\u00E9s.", action: "Ouvrir le calendrier", onAction: () => navigate("calendar") }) : _jsx("div", { className: "upcoming-list", children: scheduled.slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 4).map((entry) => _jsxs("div", { className: "upcoming-row", children: [_jsxs("span", { className: "upcoming-date", children: [_jsx("b", { children: new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { day: "2-digit" }) }), _jsx("small", { children: new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { month: "short" }) })] }), _jsx("div", { className: "upcoming-images", children: entry.items.slice(0, 3).map((item) => _jsx("img", { src: item.image_url, alt: "" }, item.id)) }), _jsxs("div", { className: "upcoming-copy", children: [_jsxs("strong", { children: [entry.items.length, " pi\u00E8ces choisies"] }), _jsx("span", { children: new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { weekday: "long" }) })] }), _jsx("button", { className: "icon-button", type: "button", onClick: () => navigate("calendar"), "aria-label": "Voir dans le calendrier", children: "\u2192" })] }, entry.date)) })] }), _jsxs("section", { className: "content-card style-overview", children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "TA SIGNATURE" }), _jsx("h3", { children: "Mon style en bref" })] }), _jsx("span", { className: "style-badge", children: "\u2726" })] }), profile ? _jsxs(_Fragment, { children: [_jsxs("p", { className: "style-overview-count", children: [_jsx("strong", { children: profile.wardrobe_size }), " pi\u00E8ces analys\u00E9es"] }), _jsxs("div", { className: "style-chips", children: [profile.favorite_styles.slice(0, 3).map((style) => _jsxs("span", { children: ["\u2727 ", style] }, style)), profile.favorite_colors.slice(0, 3).map((color) => _jsxs("span", { children: ["\u25CF ", color] }, color))] }), _jsx("button", { type: "button", className: "text-button", onClick: () => navigate("profile"), children: "Explorer mon profil \u2192" })] }) : _jsx(EmptyState, { icon: "\u25CE", title: "Ton profil se dessine", text: "Ajoute des v\u00EAtements pour d\u00E9couvrir les couleurs et styles de ton dressing.", action: "Ajouter une pi\u00E8ce", onAction: () => navigate("wardrobe") })] })] }), _jsxs("section", { className: "quick-actions", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "\u00C0 D\u00C9COUVRIR" }), _jsx("h3", { children: "Et si on allait plus loin ?" })] }), _jsxs("button", { type: "button", onClick: () => navigate("purchase"), children: [_jsx("span", { children: "\u2661" }), _jsx("b", { children: "V\u00E9rifier un achat" }), _jsx("small", { children: "Fais le bon choix" }), _jsx("i", { children: "\u2192" })] }), _jsxs("button", { type: "button", onClick: () => navigate("donation"), children: [_jsx("span", { children: "\uD83C\uDF81" }), _jsx("b", { children: "Dons & Seconde vie" }), _jsxs("small", { children: [donations.filter((d) => d.status === "pending").length, " pi\u00E8ce(s) \u00E0 donner"] }), _jsx("i", { children: "\u2192" })] }), _jsxs("button", { type: "button", onClick: () => navigate("tryon"), children: [_jsx("span", { children: "\u2726" }), _jsx("b", { children: "Essayer une pi\u00E8ce" }), _jsx("small", { children: "Projette-toi dans ton look" }), _jsx("i", { children: "\u2192" })] }), _jsxs("button", { type: "button", onClick: () => navigate("packing"), children: [_jsx("span", { children: "\u25A3" }), _jsx("b", { children: "Pr\u00E9parer ma valise" }), _jsx("small", { children: "Voyage sans rien oublier" }), _jsx("i", { children: "\u2192" })] })] })] })), screen === "wardrobe" && _jsx(WardrobeView, { items: items, favorites: wardrobeFavorites, busy: busy, onAdd: addItem, onDelete: requestDeleteItem, usage: usage, categoryPrompt: categoryPrompt, onConfirmCategory: confirmCategory, onCancelCategory: () => setCategoryPrompt(null), onWorn: markWorn, onSeasonChange: changeSeason, onToggleFavorite: (id) => toggleFavorite(id, "wardrobe") }), donationModalItem && (_jsx(DonationPromptModal, { item: donationModalItem, onDonate: handleTransferToDonation, onDeletePermanent: handlePermanentDelete, onCancel: () => setDonationModalItem(null) })), ingestionReview && _jsx(WardrobeIngestionModal, { review: ingestionReview, busy: busy === "wardrobe-upload", onConfirm: confirmIngestion, onCancel: () => setIngestionReview(null) }), screen === "outfits" && _jsx(OutfitsView, { items: items, itemsById: itemsById, outfits: outfits, favorites: outfitFavorites, scheduled: scheduled, today: today, busy: busy, onGenerate: generateLooks, onToggleFavorite: (id) => toggleFavorite(id, "outfit"), onSchedule: scheduleOutfit, onFeedback: saveOutfitFeedback, onRLHFRating: saveRLHFRating }), screen === "calendar" && _jsx(CalendarView, { anchor: monthAnchor, onMonthChange: setMonthAnchor, scheduled: scheduled, items: items, loading: loading, onSave: saveCalendarOutfit, onRemove: removeCalendarOutfit, onRender: renderCalendarOutfit }), screen === "profile" && _jsx(ProfileView, { user: user, profile: profile, busy: busy, onAvatar: uploadAvatar, onNavigate: navigate }), screen === "assistant" && _jsx(LlmAssistant, { onNavigate: navigate }), screen === "packing" && _jsx(PackingView, { lists: packingLists, busy: busy, onCreate: createPacking, onToggle: togglePackedItem, onDelete: deletePackingList }), screen === "purchase" && (_jsx(PurchaseView, { result: purchaseResult, busy: busy, onCheck: runPurchaseCheck, onRestoreResult: setPurchaseResult })), screen === "donation" && (_jsx(DonationView, { donations: donations, onMarkDonated: markDonated, onRestoreToWardrobe: restoreDonationToWardrobe, onRemoveDonation: removeDonation, onUpdateCondition: updateDonationCondition, onNavigate: navigate })), screen === "tryon" && (_jsx(TryOnView, { user: user, items: items, selectedIds: selectedTryOnItems, result: tryOnResult, busy: busy, onToggleSelect: toggleTryOnItem, onClearSelect: clearTryOnSelection, onSelectPresetAvatar: selectPresetAvatar, onAvatar: uploadAvatar, onTryOn: generateTryOn })), screen === "rlhf" && (_jsx(RLHFDashboard, { stats: rlhfStats, days: rlhfDays, loading: loading, onSetDays: setRlhfDays, onExport: downloadRLHFExport })), _jsxs("footer", { className: "app-footer", children: [_jsx("span", { children: "DressMe" }), _jsx("span", { children: "Avec amour, depuis la Tunisie \u2726" }), _jsx("span", { children: "Ton dressing, en mieux." })] })] })] })] }));
}
function PageHeading({ title, subtitle, action }) {
    return _jsxs("div", { className: "page-heading", children: [_jsxs("div", { children: [_jsx("p", { className: "eyebrow", children: "TON STUDIO DE STYLE" }), _jsx("h1", { children: title }), _jsx("p", { className: "page-subtitle", children: subtitle })] }), action] });
}
function EmptyState({ icon, title, text, action, onAction }) {
    return _jsxs("div", { className: "empty-state", children: [_jsx("span", { children: icon }), _jsx("h3", { children: title }), _jsx("p", { children: text }), action && onAction && _jsxs("button", { type: "button", className: "button button-outline", onClick: onAction, children: [action, " \u2192"] })] });
}
function CategoryPrompt({ prompt, busy, onConfirm, onCancel }) {
    const [category, setCategory] = useState(prompt.suggested_category);
    return _jsxs("section", { className: "content-card category-prompt", role: "alert", children: [_jsx("img", { src: prompt.imageUrl, alt: "Photo \u00E0 classer" }), _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "ON A BESOIN DE TOI" }), _jsx("h3", { children: "Quelle est cette pi\u00E8ce ?" }), _jsxs("p", { children: [prompt.message, " (DressMe h\u00E9site : \u00AB ", categoryLabel(prompt.suggested_category), " \u00BB, s\u00FBr \u00E0 ", Math.round(prompt.confidence * 100), " %.)"] }), _jsxs("div", { className: "button-row", children: [_jsx("select", { value: category, onChange: (event) => setCategory(event.target.value), "aria-label": "Cat\u00E9gorie de la pi\u00E8ce", children: WARDROBE_CATEGORIES.map(([value, label]) => _jsx("option", { value: value, children: label }, value)) }), _jsx("button", { type: "button", className: "button button-primary", disabled: busy, onClick: () => void onConfirm(category), children: busy ? "Ajout…" : "Ajouter comme ça" }), _jsx("button", { type: "button", className: "button button-outline", disabled: busy, onClick: onCancel, children: "Annuler" })] })] })] });
}
function WardrobeIngestionModal({ review, busy, onConfirm, onCancel, }) {
    const { analysis, imageUrl } = review;
    const seg = analysis.segmentation;
    const hasExtracted = Boolean(seg?.person_detected && seg.extracted_garments && seg.extracted_garments.length > 0);
    const [selectedImage, setSelectedImage] = useState(hasExtracted && seg?.extracted_garments?.[0]?.image_url
        ? seg.extracted_garments[0].image_url
        : imageUrl);
    const [category, setCategory] = useState(hasExtracted && seg?.extracted_garments?.[0]?.category
        ? seg.extracted_garments[0].category
        : review.selectedCategory);
    const [season, setSeason] = useState(review.selectedSeason);
    const cv = analysis.cv_diagnostics;
    const quality = cv?.quality;
    const rag = analysis.rag_analysis;
    const styling = analysis.styling_insights;
    const palette = analysis.kmeans_palette;
    return (_jsx("div", { className: "modal-backdrop", onClick: onCancel, children: _jsxs("div", { className: "ingestion-modal", onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: "modal-header", children: [_jsxs("div", { className: "modal-header-titles", children: [_jsx("span", { className: "eyebrow", children: "AGENT D'INGESTION MULTIMODAL" }), _jsx("h2", { children: "Analyse IA du v\u00EAtement" }), _jsx("p", { className: "modal-sub", children: "SegFormer AI, Computer Vision, Deep Learning & RAG" })] }), _jsx("button", { type: "button", className: "modal-close", onClick: onCancel, "aria-label": "Fermer", children: "\u2715" })] }), hasExtracted && seg?.extracted_garments && (_jsxs("div", { className: "seg-banner-container", children: [_jsxs("div", { className: "seg-banner-header", children: [_jsx("span", { className: "seg-banner-icon", children: "\u2702\uFE0F" }), _jsxs("div", { className: "seg-banner-text", children: [_jsxs("div", { className: "seg-banner-title-row", children: [_jsx("strong", { children: "Mannequin / Personne d\u00E9tect\u00E9e sur la photo !" }), _jsx("span", { className: "seg-ai-tag", children: "SegFormer-B2 Vision AI" })] }), _jsx("p", { children: "L'intelligence artificielle a isol\u00E9 les v\u00EAtements port\u00E9s sur fond blanc \u00E9pur\u00E9 pour un rendu dressing professionnel. Choisis la pi\u00E8ce \u00E0 enregistrer :" })] })] }), _jsxs("div", { className: "seg-garments-selector", children: [seg.extracted_garments.map((g, idx) => {
                                    const isSelected = selectedImage === g.image_url;
                                    return (_jsxs("button", { type: "button", className: `seg-garment-card ${isSelected ? "active" : ""}`, onClick: () => {
                                            setSelectedImage(g.image_url);
                                            setCategory(g.category);
                                        }, children: [_jsxs("div", { className: "seg-img-container", children: [_jsx("img", { src: g.image_url, alt: g.category }), isSelected && _jsx("span", { className: "seg-checked-badge", children: "\u2713 Choisi" })] }), _jsxs("div", { className: "seg-garment-info", children: [_jsx("span", { className: "seg-category-label", children: categoryLabel(g.category) }), _jsx("span", { className: "seg-type-pill", children: "Sans mannequin (isol\u00E9)" }), _jsxs("small", { className: "seg-share-label", children: [(g.share * 100).toFixed(0), "% de la tenue"] })] })] }, idx));
                                }), _jsxs("button", { type: "button", className: `seg-garment-card ${selectedImage === imageUrl ? "active" : ""}`, onClick: () => {
                                        setSelectedImage(imageUrl);
                                        setCategory(review.selectedCategory);
                                    }, children: [_jsxs("div", { className: "seg-img-container", children: [_jsx("img", { src: imageUrl, alt: "Photo brute originale" }), selectedImage === imageUrl && _jsx("span", { className: "seg-checked-badge", children: "\u2713 Choisi" })] }), _jsxs("div", { className: "seg-garment-info", children: [_jsx("span", { className: "seg-category-label", children: "Photo brute" }), _jsx("span", { className: "seg-type-pill muted", children: "Avec personne / d\u00E9cor" }), _jsx("small", { className: "seg-share-label", children: "Image originale" })] })] })] })] })), _jsxs("div", { className: "ingestion-grid", children: [_jsxs("div", { className: "ingestion-col-left", children: [_jsxs("div", { className: "ingestion-preview-card", children: [_jsx("img", { src: selectedImage, alt: "V\u00EAtement analys\u00E9", className: "ingestion-photo" }), selectedImage !== imageUrl && (_jsx("div", { className: "cutout-indicator-badge", children: _jsx("span", { children: "\u2728 V\u00EAtement d\u00E9tour\u00E9 (mannequin retir\u00E9)" }) })), quality?.quality_score != null && (_jsxs("div", { className: `quality-badge ${quality.sharpness}`, children: [_jsx("span", { className: "quality-icon", children: "\u2726" }), _jsxs("span", { children: ["Qualit\u00E9 CV : ", _jsxs("b", { children: [quality.quality_score, "%"] }), " \u00B7 ", quality.sharpness === "sharp" ? "Photo nette" : quality.sharpness === "acceptable" ? "Acceptable" : "Floue"] })] }))] }), _jsxs("div", { className: "cv-metrics-card", children: [_jsx("h4", { children: "Diagnostics Computer Vision (OpenCV)" }), _jsxs("div", { className: "metrics-pills", children: [_jsxs("span", { title: "Variance du Laplacien pour d\u00E9tection de flou", children: ["Laplacian : ", _jsx("b", { children: quality?.laplacian_variance ?? "-" })] }), _jsxs("span", { children: ["Luminosit\u00E9 : ", _jsx("b", { children: quality?.brightness ?? "-" })] }), _jsxs("span", { children: ["Contraste : ", _jsx("b", { children: quality?.contrast ?? "-" })] }), _jsxs("span", { children: ["Dimensions : ", _jsxs("b", { children: [cv?.dimensions?.width, "\u00D7", cv?.dimensions?.height] })] })] }), quality?.warnings && quality.warnings.length > 0 && (_jsx("div", { className: "cv-warnings-list", children: quality.warnings.map((w, i) => (_jsxs("p", { className: "cv-warning-item", children: ["\u2139\uFE0F ", w] }, i))) }))] }), palette && palette.length > 0 && (_jsxs("div", { className: "kmeans-palette-card", children: [_jsx("h4", { children: "Palette extraite par K-Means" }), _jsx("div", { className: "kmeans-swatches-grid", children: palette.map((p, idx) => (_jsxs("div", { className: "kmeans-swatch-item", children: [_jsx("span", { className: "kmeans-swatch-circle", style: { backgroundColor: p.hex } }), _jsxs("div", { className: "kmeans-swatch-info", children: [_jsx("strong", { children: p.label }), _jsxs("small", { children: [p.hex, " \u00B7 ", p.percentage, "%"] })] })] }, idx))) })] }))] }), _jsxs("div", { className: "ingestion-col-right", children: [rag?.duplicate_warning && (_jsxs("div", { className: "rag-duplicate-alert", children: [_jsx("span", { className: "alert-icon", children: "\u26A0\uFE0F" }), _jsxs("div", { children: [_jsx("strong", { children: "Alerte Doublon RAG" }), _jsx("p", { children: rag.duplicate_warning }), rag.similar_items?.[0] && (_jsxs("div", { className: "duplicate-thumb-row", children: [_jsx("img", { src: rag.similar_items[0].image_url, alt: "Pi\u00E8ce similaire", className: "duplicate-thumb" }), _jsxs("span", { children: [rag.similar_items[0].similarity, "% similaire avec votre ", categoryLabel(rag.similar_items[0].category), " existant"] })] }))] })] })), _jsxs("div", { className: "attributes-config-card", children: [_jsx("h4", { children: "Classification & Confirmation" }), _jsxs("div", { className: "form-row", children: [_jsxs("label", { className: "field-group", children: [_jsxs("span", { children: ["Cat\u00E9gorie ", analysis.confidence?.category ? _jsxs("small", { className: "conf-pill", children: [(analysis.confidence.category * 100).toFixed(0), "% confiance"] }) : null] }), _jsx("select", { value: category, onChange: (e) => setCategory(e.target.value), children: WARDROBE_CATEGORIES.map(([val, label]) => (_jsx("option", { value: val, children: label }, val))) })] }), _jsxs("label", { className: "field-group", children: [_jsx("span", { children: "Saison de la pi\u00E8ce" }), _jsxs("select", { value: season, onChange: (e) => setSeason(e.target.value), children: [_jsx("option", { value: "toutes_saisons", children: "Toutes saisons" }), ITEM_SEASONS.map(([val, label]) => (_jsx("option", { value: val, children: label }, val)))] })] })] }), _jsxs("div", { className: "detected-tags-row", children: [analysis.style && _jsxs("span", { className: "style-pill", children: ["\u2727 Style : ", _jsx("b", { children: categoryLabel(analysis.style) })] }), analysis.pattern && _jsxs("span", { className: "style-pill", children: ["\u25A6 Motif : ", _jsx("b", { children: categoryLabel(analysis.pattern) })] }), analysis.colors && analysis.colors.length > 0 && (_jsxs("span", { className: "style-pill", children: ["\u25CF Couleurs : ", _jsx("b", { children: analysis.colors.map(categoryLabel).join(", ") })] }))] })] }), rag?.recommended_pairings && rag.recommended_pairings.length > 0 && (_jsxs("div", { className: "rag-pairings-card", children: [_jsx("h4", { children: "\u2726 Looks possibles avec ton dressing (RAG)" }), _jsx("div", { className: "pairings-scroll", children: rag.recommended_pairings.map((pair, i) => (_jsxs("div", { className: "pairing-card", children: [_jsx("img", { src: pair.image_url, alt: pair.category }), _jsxs("div", { className: "pairing-info", children: [_jsx("strong", { children: categoryLabel(pair.category) }), _jsx("small", { children: pair.colors?.map(categoryLabel).join(", ") || pair.style || "Dressing" }), _jsxs("span", { className: "harmony-badge", children: ["Harmonie : ", (pair.score * 100).toFixed(0), "%"] })] })] }, i))) })] })), styling?.editorial_advice && (_jsxs("div", { className: "styling-insights-card", children: [_jsx("h4", { children: "\u2728 Note du Styliste IA" }), _jsx("p", { className: "editorial-text", children: styling.editorial_advice }), styling.recommended_occasions && styling.recommended_occasions.length > 0 && (_jsx("div", { className: "occasions-chips", children: styling.recommended_occasions.map((occ, i) => (_jsxs("span", { className: "occasion-chip", children: ["\uD83D\uDCCD ", occ] }, i))) })), styling.care_tip && (_jsxs("p", { className: "care-tip-text", children: ["\uD83E\uDDFC ", _jsx("b", { children: "Conseil d'entretien :" }), " ", styling.care_tip] }))] }))] })] }), _jsxs("div", { className: "modal-footer", children: [_jsx("button", { type: "button", className: "button button-outline", onClick: onCancel, disabled: busy, children: "Annuler" }), _jsx("button", { type: "button", className: "button button-primary", onClick: () => void onConfirm(category, season, selectedImage), disabled: busy, children: busy ? "Enregistrement…" : "✓ Confirmer et ajouter au dressing" })] })] }) }));
}
function WardrobeView({ items, favorites, busy, usage, categoryPrompt, onConfirmCategory, onCancelCategory, onAdd, onDelete, onWorn, onSeasonChange, onToggleFavorite }) {
    const [query, setQuery] = useState("");
    const [category, setCategory] = useState("toutes");
    const [favoritesOnly, setFavoritesOnly] = useState(false);
    const [season, setSeason] = useState("");
    const [sortBy, setSortBy] = useState("recent");
    const [viewMode, setViewMode] = useState("grid");
    const [kpiFilter, setKpiFilter] = useState("all");
    const toConfirmCount = items.filter((item) => item.season_source === "vision" || !item.season).length;
    const wornCount = items.filter((item) => (usage[item.id]?.wear_count || 0) > 0).length;
    const filtered = items.filter((item) => {
        if (kpiFilter === "favorites" && !favorites.includes(item.id))
            return false;
        if (kpiFilter === "worn" && !(usage[item.id]?.wear_count > 0))
            return false;
        if (kpiFilter === "toConfirm" && !(item.season_source === "vision" || !item.season))
            return false;
        const matchesCategory = category === "toutes" || (item.category ?? "autre").toLocaleLowerCase() === category;
        const matchesFavorite = !favoritesOnly || favorites.includes(item.id);
        const matchesSeason = !season || item.season === season || (season !== "toutes_saisons" && item.season === "toutes_saisons");
        const searchable = [item.category, item.style, item.season, itemSeasonLabel(item.season), item.pattern, ...(item.colors ?? [])].join(" ").toLocaleLowerCase();
        return matchesCategory && matchesFavorite && matchesSeason && searchable.includes(query.trim().toLocaleLowerCase());
    });
    const sorted = [...filtered].sort((a, b) => {
        if (sortBy === "wear-desc")
            return (usage[b.id]?.wear_count || 0) - (usage[a.id]?.wear_count || 0);
        if (sortBy === "wear-asc")
            return (usage[a.id]?.wear_count || 0) - (usage[b.id]?.wear_count || 0);
        if (sortBy === "alpha")
            return (categoryLabel(a.category) || "").localeCompare(categoryLabel(b.category) || "");
        return 0;
    });
    const categories = Array.from(new Set(items.map((item) => (item.category ?? "autre").toLocaleLowerCase()))).sort();
    const hasActiveFilters = query.trim() !== "" || category !== "toutes" || season !== "" || favoritesOnly || kpiFilter !== "all" || sortBy !== "recent";
    const resetAllFilters = () => {
        setQuery("");
        setCategory("toutes");
        setSeason("");
        setFavoritesOnly(false);
        setKpiFilter("all");
        setSortBy("recent");
    };
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Mon dressing", subtitle: "Ajoute, retrouve et organise les pi\u00E8ces que tu aimes porter.", action: _jsxs("label", { className: `button button-primary file-button${busy === "wardrobe-upload" ? " is-disabled" : ""}`, children: ["\uFF0B ", busy === "wardrobe-upload" ? "Analyse en cours…" : "Ajouter une pièce", _jsx("input", { type: "file", accept: "image/*", disabled: busy === "wardrobe-upload", onChange: (event) => { const file = event.target.files?.[0]; if (file)
                                void onAdd(file, season); event.target.value = ""; } })] }) }), categoryPrompt && _jsx(CategoryPrompt, { prompt: categoryPrompt, busy: busy === "wardrobe-upload", onConfirm: onConfirmCategory, onCancel: onCancelCategory }), _jsxs("div", { className: "wardrobe-kpi-bar", children: [_jsxs("button", { type: "button", className: `kpi-chip ${kpiFilter === "all" && !favoritesOnly ? "is-active" : ""}`, onClick: () => { setKpiFilter("all"); setFavoritesOnly(false); }, children: [_jsx("span", { className: "kpi-icon", children: "\u25C8" }), _jsxs("div", { className: "kpi-meta", children: [_jsx("strong", { children: items.length }), _jsx("span", { children: "Toutes les pi\u00E8ces" })] })] }), _jsxs("button", { type: "button", className: `kpi-chip ${kpiFilter === "favorites" || favoritesOnly ? "is-active" : ""}`, onClick: () => { setKpiFilter("favorites"); setFavoritesOnly(true); }, children: [_jsx("span", { className: "kpi-icon pink", children: "\u2665" }), _jsxs("div", { className: "kpi-meta", children: [_jsx("strong", { children: favorites.length }), _jsx("span", { children: "Favoris" })] })] }), _jsxs("button", { type: "button", className: `kpi-chip ${kpiFilter === "worn" ? "is-active" : ""}`, onClick: () => { setKpiFilter("worn"); setFavoritesOnly(false); }, children: [_jsx("span", { className: "kpi-icon gold", children: "\u26A1" }), _jsxs("div", { className: "kpi-meta", children: [_jsx("strong", { children: wornCount }), _jsx("span", { children: "D\u00E9j\u00E0 port\u00E9es" })] })] }), toConfirmCount > 0 && (_jsxs("button", { type: "button", className: `kpi-chip warn ${kpiFilter === "toConfirm" ? "is-active" : ""}`, onClick: () => { setKpiFilter("toConfirm"); setFavoritesOnly(false); }, children: [_jsx("span", { className: "kpi-icon warn", children: "\u26A0\uFE0F" }), _jsxs("div", { className: "kpi-meta", children: [_jsx("strong", { children: toConfirmCount }), _jsx("span", { children: "\u00C0 confirmer" })] })] }))] }), categories.length > 0 && (_jsxs("div", { className: "category-chips-bar", children: [_jsxs("button", { type: "button", className: `cat-chip ${category === "toutes" ? "active" : ""}`, onClick: () => setCategory("toutes"), children: ["Toutes ", _jsxs("small", { children: ["(", items.length, ")"] })] }), categories.map((cat) => {
                        const count = items.filter((i) => (i.category ?? "autre").toLowerCase() === cat).length;
                        return (_jsxs("button", { type: "button", className: `cat-chip ${category === cat ? "active" : ""}`, onClick: () => setCategory(cat), children: [categoryLabel(cat), " ", _jsxs("small", { children: ["(", count, ")"] })] }, cat));
                    })] })), _jsxs("div", { className: "wardrobe-toolbar", children: [_jsxs("label", { className: "search-field", children: [_jsx("span", { children: "\u2315" }), _jsx("input", { value: query, onChange: (event) => setQuery(event.target.value), placeholder: "Chercher une couleur, un style, un mot-cl\u00E9\u2026" }), query && (_jsx("button", { type: "button", className: "clear-search-btn", onClick: () => setQuery(""), title: "Effacer la recherche", children: "\u2715" }))] }), _jsxs("label", { className: "filter-select", children: [_jsx("span", { children: "Saison" }), _jsxs("select", { value: season, onChange: (event) => setSeason(event.target.value), children: [_jsx("option", { value: "", children: "Toutes saisons" }), ITEM_SEASONS.map(([value, label]) => _jsx("option", { value: value, children: label }, value))] })] }), _jsxs("label", { className: "filter-select", children: [_jsx("span", { children: "Trier par" }), _jsxs("select", { value: sortBy, onChange: (event) => setSortBy(event.target.value), children: [_jsx("option", { value: "recent", children: "Plus r\u00E9cents" }), _jsx("option", { value: "wear-desc", children: "Plus souvent port\u00E9s" }), _jsx("option", { value: "wear-asc", children: "Moins port\u00E9s" }), _jsx("option", { value: "alpha", children: "Cat\u00E9gorie (A-Z)" })] })] }), _jsxs("div", { className: "view-mode-toggle", role: "group", "aria-label": "Mode d'affichage", children: [_jsx("button", { type: "button", className: viewMode === "grid" ? "active" : "", onClick: () => setViewMode("grid"), title: "Grille standard", children: "\u229E" }), _jsx("button", { type: "button", className: viewMode === "compact" ? "active" : "", onClick: () => setViewMode("compact"), title: "Grille compacte", children: "\u229F" })] }), hasActiveFilters && (_jsx("button", { type: "button", className: "reset-filters-btn", onClick: resetAllFilters, title: "R\u00E9initialiser tous les filtres", children: "\u2715 R\u00E9initialiser" }))] }), _jsxs("div", { className: "results-line", children: [_jsxs("span", { children: [_jsx("b", { children: sorted.length }), " pi\u00E8ce", sorted.length > 1 ? "s" : "", " trouv\u00E9e", sorted.length > 1 ? "s" : "", hasActiveFilters && _jsx("span", { className: "active-filter-badge", children: " \u00B7 Filtres actifs" })] }), _jsx("span", { className: "photo-tip", children: "\uD83D\uDCA1 Photos nettes sur fond uni = reconnaissance IA optimale" })] }), sorted.length === 0 ? (_jsx(EmptyState, { icon: items.length === 0 ? "◈" : "⌕", title: items.length === 0 ? "Ton dressing commence ici" : "Aucune pièce trouvée", text: items.length === 0 ? "Ajoute une photo de vêtement : DressMe identifiera sa catégorie, ses couleurs et son style." : "Essaie d’ajuster ta recherche ou de réinitialiser tes filtres." })) : (_jsx("div", { className: `clothing-grid ${viewMode === "compact" ? "is-compact" : ""}`, children: sorted.map((item) => {
                    const palette = item.attribute_confidence?.kmeans_palette;
                    const cvDiag = item.attribute_confidence?.cv_diagnostics;
                    const ragAnalysis = item.attribute_confidence?.rag_analysis;
                    const styling = item.attribute_confidence?.styling_insights;
                    const wearInfo = usage[item.id];
                    return (_jsxs("article", { className: "clothing-card", children: [_jsxs("div", { className: "clothing-photo", children: [_jsx("img", { src: item.image_url, alt: categoryLabel(item.category), loading: "lazy" }), _jsx("span", { className: "photo-category-tag", children: categoryLabel(item.category) }), _jsx("button", { type: "button", className: `favorite-toggle${favorites.includes(item.id) ? " is-favorite" : ""}`, "aria-label": favorites.includes(item.id) ? "Retirer des favoris" : "Ajouter aux favoris", "aria-pressed": favorites.includes(item.id), onClick: () => onToggleFavorite(item.id), children: favorites.includes(item.id) ? "♥" : "♡" })] }), _jsxs("div", { className: "clothing-info", children: [_jsxs("div", { className: "clothing-title-row", children: [_jsx("h3", { children: item.style ? categoryLabel(item.style) : "Pièce de mon dressing" }), item.season && _jsx("span", { className: "season-badge", children: itemSeasonLabel(item.season) })] }), _jsx("p", { className: "clothing-attributes-desc", children: [...(item.colors ?? []), item.pattern].filter(Boolean).map(categoryLabel).join(" · ") || "Style à découvrir" }), Array.isArray(palette) && palette.length > 0 && (_jsxs("div", { className: "kmeans-palette-row", children: [palette.map((p, i) => (_jsx("span", { title: `${p.label} (${p.percentage}%)`, className: "palette-dot", style: { backgroundColor: p.hex } }, i))), _jsx("small", { className: "palette-tag", children: "K-Means IA" })] })), styling?.editorial_advice && (_jsxs("details", { className: "outfit-explanation", children: [_jsx("summary", { children: "\u2726 Note du Styliste & RAG" }), _jsxs("div", { className: "explanation-drawer", children: [cvDiag?.quality?.sharpness && (_jsxs("p", { className: "diag-tag", children: ["\u2713 OpenCV : nettet\u00E9 ", cvDiag.quality.sharpness] })), ragAnalysis?.duplicate_warning && (_jsxs("p", { className: "dup-warning", children: ["\u26A0\uFE0F ", ragAnalysis.duplicate_warning] })), _jsx("p", { className: "editorial-content", children: styling.editorial_advice }), styling.care_tip && (_jsxs("p", { className: "care-tip-line", children: ["\uD83E\uDDFC ", styling.care_tip] }))] })] })), _jsxs("div", { className: "card-actions-row", children: [_jsxs("label", { className: "season-picker", children: [_jsxs("select", { "aria-label": "Saison de la pi\u00E8ce", value: item.season ?? "", onChange: (event) => { if (event.target.value)
                                                            void onSeasonChange(item, event.target.value); }, children: [_jsx("option", { value: "", disabled: true, children: "Saison ?" }), ITEM_SEASONS.map(([value, label]) => _jsx("option", { value: value, children: label }, value))] }), (item.season_source === "vision" || !item.season) && _jsx("span", { className: "confirm-badge", children: "\u00C0 confirmer" })] }), _jsxs("div", { className: "wear-log-container", children: [_jsx("span", { className: "wear-count-badge", children: wearInfo ? `Porté ${wearInfo.wear_count}×` : "Neuf (0×)" }), _jsx("button", { type: "button", className: "worn-button", onClick: () => void onWorn(item), title: "Enregistrer comme port\u00E9 aujourd'hui", children: "\uFF0B Port\u00E9" })] })] }), _jsx("button", { type: "button", className: "remove-link", onClick: () => void onDelete(item), children: "Retirer du dressing" })] })] }, item.id));
                }) }))] });
}
function OutfitsView({ items, itemsById, outfits, favorites, scheduled, today, busy, onGenerate, onToggleFavorite, onSchedule, onFeedback, onRLHFRating }) {
    const [showFavorites, setShowFavorites] = useState(false);
    const [selectedOccasion, setSelectedOccasion] = useState("");
    const [selectedCity, setSelectedCity] = useState("Tunis");
    const [planDates, setPlanDates] = useState({});
    const [cityWeathers, setCityWeathers] = useState({
        Tunis: { temp: 22, icon: "🌤️" },
        Sousse: { temp: 24, icon: "☀️" },
        Sfax: { temp: 21, icon: "⛅" },
        Djerba: { temp: 25, icon: "🌴" },
    });
    useEffect(() => {
        ["Tunis", "Sousse", "Sfax", "Djerba"].forEach((city) => {
            api.get(`/weather/${city}`)
                .then(({ data }) => setCityWeathers((prev) => ({ ...prev, [city]: { temp: data.temp, icon: data.icon } })))
                .catch(() => { });
        });
    }, []);
    const OCCASION_DATA = [
        { id: "", label: "Toutes", icon: "✨" },
        { id: "quotidien", label: "Quotidien", icon: "☕" },
        { id: "travail", label: "Travail & Bureau", icon: "💼" },
        { id: "sortie", label: "Sortie & Ville", icon: "🍸" },
        { id: "soirée", label: "Soirée & Dîner", icon: "🌙" },
        { id: "événement", label: "Événement & Fête", icon: "🎉" },
    ];
    const CITY_DATA = [
        { name: "Tunis", temp: `${cityWeathers["Tunis"]?.temp ?? 22}°C`, icon: cityWeathers["Tunis"]?.icon ?? "🌤️" },
        { name: "Sousse", temp: `${cityWeathers["Sousse"]?.temp ?? 24}°C`, icon: cityWeathers["Sousse"]?.icon ?? "☀️" },
        { name: "Sfax", temp: `${cityWeathers["Sfax"]?.temp ?? 21}°C`, icon: cityWeathers["Sfax"]?.icon ?? "⛅" },
        { name: "Djerba", temp: `${cityWeathers["Djerba"]?.temp ?? 25}°C`, icon: cityWeathers["Djerba"]?.icon ?? "🌴" },
    ];
    const tomorrow = new Date(Date.now() + 86400000).toISOString().split("T")[0];
    const KNOWN_OCCASIONS = ["quotidien", "travail", "sortie", "soirée", "événement"];
    const filtered = outfits.filter((outfit) => {
        if (showFavorites && !favorites.includes(outfit.id))
            return false;
        if (selectedOccasion && outfit.occasion) {
            // Normalize: check if the outfit occasion starts with or contains the selected occasion
            const occ = outfit.occasion.toLowerCase();
            const sel = selectedOccasion.toLowerCase();
            if (occ !== sel && !occ.startsWith(sel) && !occ.includes(sel))
                return false;
        }
        // If selectedOccasion is set but outfit.occasion is not in known list, still show it
        return true;
    });
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Des looks faits pour toi", subtitle: "Recommandations intelligentes g\u00E9n\u00E9r\u00E9es \u00E0 partir de ta garde-robe, de la m\u00E9t\u00E9o et de tes envies." }), _jsxs("form", { className: "content-card recommendation-form modern-generator-card", onSubmit: (event) => void onGenerate(event), children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "STUDIO DE COMPOSITION IA" }), _jsx("h3", { children: "G\u00E9n\u00E8re une tenue sur-mesure" })] }), _jsx("span", { className: "form-sparkle", children: "\u2726" })] }), _jsxs("div", { className: "form-section-group", children: [_jsx("label", { className: "section-mini-label", children: "1. Choisis ton occasion :" }), _jsx("input", { type: "hidden", name: "occasion", value: selectedOccasion }), _jsx("div", { className: "interactive-chips-row", children: OCCASION_DATA.map((occ) => (_jsxs("button", { type: "button", className: `generator-chip ${selectedOccasion === occ.id ? "active" : ""}`, onClick: () => setSelectedOccasion(occ.id), children: [_jsx("span", { className: "chip-icon", children: occ.icon }), _jsx("span", { children: occ.label })] }, occ.id))) })] }), _jsxs("div", { className: "form-section-group", children: [_jsx("label", { className: "section-mini-label", htmlFor: "outfit-request-text", children: "Une envie pr\u00E9cise ? (facultatif)" }), _jsx("textarea", { id: "outfit-request-text", name: "request_text", className: "request-textarea", maxLength: 500, placeholder: "Ex. Je vais d\u00EEner au restaurant apr\u00E8s le travail" }), _jsx("p", { className: "inline-hint", children: "D\u00E9cris le contexte en langage courant. Les pi\u00E8ces propos\u00E9es restent limit\u00E9es \u00E0 ton dressing." })] }), _jsxs("div", { className: "form-section-group", children: [_jsx("label", { className: "section-mini-label", children: "2. Destination & M\u00E9t\u00E9o :" }), _jsx("input", { type: "hidden", name: "city", value: selectedCity }), _jsx("div", { className: "interactive-chips-row", children: CITY_DATA.map((city) => (_jsxs("button", { type: "button", className: `generator-chip city-chip ${selectedCity === city.name ? "active" : ""}`, onClick: () => setSelectedCity(city.name), children: [_jsx("span", { children: city.icon }), _jsx("span", { children: city.name }), _jsx("small", { className: "temp-badge", children: city.temp })] }, city.name))) })] }), _jsxs("div", { className: "form-submit-row", children: [_jsxs("p", { className: "generator-hint", children: [items.length, " pi\u00E8ces dans ton dressing pr\u00EAtes \u00E0 \u00EAtre associ\u00E9es par l'algorithme Polyvore IA."] }), _jsx("button", { className: "button button-primary generator-btn", disabled: busy === "looks" || items.length === 0, children: busy === "looks" ? "Composition du look par l'IA…" : "✨ Trouver mes tenues" })] }), items.length === 0 && _jsx("p", { className: "inline-hint error-hint", children: "Ajoute d\u2019abord quelques v\u00EAtements dans ton dressing pour recevoir des propositions." })] }), _jsxs("div", { className: "section-toolbar", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "PROPOSITIONS DU STYLISTE" }), _jsxs("h2", { children: [filtered.length, " look", filtered.length > 1 ? "s" : "", " disponible", filtered.length > 1 ? "s" : ""] })] }), _jsxs("div", { className: "segmented-control", children: [_jsxs("button", { className: !showFavorites ? "active" : "", type: "button", onClick: () => setShowFavorites(false), children: ["Tous les looks (", outfits.length, ")"] }), _jsxs("button", { className: showFavorites ? "active" : "", type: "button", onClick: () => setShowFavorites(true), children: ["\u2665 Coups de c\u0153ur ", favorites.length > 0 && `(${favorites.length})`] })] })] }), filtered.length === 0 ? (_jsx(EmptyState, { icon: showFavorites ? "♡" : "✧", title: showFavorites ? "Aucun look favori pour le moment" : "Prête pour de nouvelles inspirations ?", text: showFavorites ? "Appuie sur le cœur d'un look pour le retrouver dans tes favoris." : "Clique sur 'Trouver mes tenues' ci-dessus pour que l'IA compose tes tenues idéales." })) : (_jsx("div", { className: "outfit-grid", children: filtered.map((outfit) => {
                    const outfitItems = outfit.item_ids.map((id) => itemsById.get(id)).filter((item) => Boolean(item));
                    const isPlanned = scheduled.some((entry) => entry.item_ids.length === outfit.item_ids.length && entry.item_ids.every((id) => outfit.item_ids.includes(id)));
                    const matchPercent = outfit.relevance_score != null ? Math.round(outfit.relevance_score * 100) : 88;
                    return (_jsxs("article", { className: "outfit-card modern-outfit-card", children: [_jsxs("div", { className: "outfit-card-top", children: [_jsxs("div", { children: [_jsx("span", { className: "category-pill", children: outfit.occasion ? categoryLabel(outfit.occasion) : "Suggestion Styliste" }), _jsxs("h3", { children: ["Un look pour ", outfit.occasion ? categoryLabel(outfit.occasion) : "toi"] })] }), _jsx("button", { type: "button", className: `favorite-toggle outfit-heart${favorites.includes(outfit.id) ? " is-favorite" : ""}`, "aria-label": favorites.includes(outfit.id) ? "Retirer des favoris" : "Ajouter aux favoris", onClick: () => onToggleFavorite(outfit.id), children: favorites.includes(outfit.id) ? "♥" : "♡" })] }), _jsx("div", { className: "outfit-items modern-outfit-items", children: outfitItems.map((item) => (_jsxs("div", { className: "outfit-piece", children: [_jsx("img", { src: item.image_url, alt: categoryLabel(item.category), loading: "lazy" }), _jsx("span", { className: "piece-category-tag", children: categoryLabel(item.category) })] }, item.id))) }), _jsxs("div", { className: "outfit-meta modern-outfit-meta", children: [_jsxs("span", { className: `match-score-pill ${matchPercent >= 85 ? "high-match" : ""}`, children: ["\u2726 ", matchPercent, "% Harmonie Stylistique"] }), _jsxs("span", { className: "pieces-count-tag", children: [outfit.item_ids.length, " pi\u00E8ces associ\u00E9es"] })] }), outfit.explanation && (_jsxs("details", { className: "outfit-explanation", children: [_jsx("summary", { children: "\u2726 Conseil \u00E9ditorial de style" }), _jsx("p", { children: outfit.explanation })] })), _jsx("div", { className: "outfit-feedback-actions", "aria-label": "Donner ton avis sur cette tenue", children: [
                                    ["like", "👍 J’aime"],
                                    ["dislike", "👎 Pas pour moi"],
                                    ["worn", "✓ Déjà portée"],
                                ].map(([rating, label]) => {
                                    const isBusy = busy === `outfit-feedback:${outfit.id}`;
                                    const active = outfit.feedback === rating;
                                    return (_jsx("button", { type: "button", className: `outfit-feedback-button${active ? " is-selected" : ""}`, disabled: isBusy, "aria-pressed": active, onClick: () => void onFeedback(outfit.id, active ? null : rating), children: isBusy ? "Enregistrement…" : label }, rating));
                                }) }), _jsxs("div", { className: "rlhf-star-row", "aria-label": "Note de 1 \u00E0 5 \u00E9toiles pour am\u00E9liorer les recommandations", children: [_jsx("span", { className: "rlhf-star-label", children: "Am\u00E9liore l'IA :" }), [1, 2, 3, 4, 5].map((star) => {
                                        const isRateBusy = busy === `rlhf-rate:${outfit.id}`;
                                        return (_jsx("button", { type: "button", className: "rlhf-star-btn", "aria-label": `${star} étoile${star > 1 ? "s" : ""}`, disabled: isRateBusy, onClick: () => void onRLHFRating(outfit.id, star), children: "\u2605" }, star));
                                    })] }), _jsxs("div", { className: "schedule-quick-container", children: [_jsxs("div", { className: "quick-plan-buttons", children: [_jsx("button", { type: "button", className: "plan-shortcut-btn", onClick: () => void onSchedule(outfit, today), title: "Planifier pour aujourd'hui", children: "\u26A1 Aujourd'hui" }), _jsx("button", { type: "button", className: "plan-shortcut-btn", onClick: () => void onSchedule(outfit, tomorrow), title: "Planifier pour demain", children: "Demain" })] }), _jsxs("div", { className: "schedule-row", children: [_jsx("input", { "aria-label": "Date de planification", type: "date", min: today, value: planDates[outfit.id] ?? today, onChange: (event) => setPlanDates((current) => ({ ...current, [outfit.id]: event.target.value })) }), _jsx("button", { type: "button", className: "button button-outline", onClick: () => void onSchedule(outfit, planDates[outfit.id] ?? today), children: isPlanned ? "✓ Déjà prévu" : "📅 Planifier" })] })] })] }, outfit.id));
                }) }))] });
}
function DayThumb({ plan }) {
    if (plan.render_image_url)
        return _jsx("img", { className: "day-thumb", src: plan.render_image_url, alt: "", loading: "lazy" });
    return _jsx("span", { className: "day-collage", "aria-hidden": "true", children: plan.items.slice(0, 4).map((item) => _jsx("img", { src: item.image_url, alt: "", loading: "lazy" }, item.id)) });
}
function CalendarView({ anchor, onMonthChange, scheduled, items, loading, onSave, onRemove, onRender }) {
    const [rendering, setRendering] = useState(false);
    const [selectedDate, setSelectedDate] = useState(todayLocal());
    const [editing, setEditing] = useState(false);
    const [selectedIds, setSelectedIds] = useState([]);
    const [saving, setSaving] = useState(false);
    const monthName = anchor.toLocaleDateString("fr-TN", { month: "long", year: "numeric" });
    const firstWeekday = (new Date(anchor.getFullYear(), anchor.getMonth(), 1).getDay() + 6) % 7;
    const dayCount = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate();
    const days = [...Array(firstWeekday).fill(null), ...Array.from({ length: dayCount }, (_, index) => index + 1)];
    while (days.length % 7)
        days.push(null);
    const plan = scheduled.find((entry) => entry.date === selectedDate);
    const currentMonthPlansCount = scheduled.filter((entry) => {
        const entryDate = new Date(entry.date);
        return entryDate.getMonth() === anchor.getMonth() && entryDate.getFullYear() === anchor.getFullYear();
    }).length;
    function changeMonth(delta) {
        const next = new Date(anchor.getFullYear(), anchor.getMonth() + delta, 1);
        onMonthChange(next);
        setSelectedDate(dayString(next));
        setEditing(false);
    }
    function jumpToToday() {
        const now = new Date();
        onMonthChange(new Date(now.getFullYear(), now.getMonth(), 1));
        setSelectedDate(todayLocal());
        setEditing(false);
    }
    async function renderOnAvatar() {
        setRendering(true);
        try {
            await onRender(selectedDate);
        }
        finally {
            setRendering(false);
        }
    }
    function startEdit() {
        setSelectedIds(plan?.item_ids ?? []);
        setEditing(true);
    }
    async function save() {
        setSaving(true);
        try {
            await onSave(selectedDate, selectedIds);
            setEditing(false);
        }
        catch {
            return;
        }
        finally {
            setSaving(false);
        }
    }
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Mon calendrier de style", subtitle: "Visualise tes tenues quotidiennes, pr\u00E9pare tes matins \u00E0 l'avance et habille ton avatar." }), _jsxs("div", { className: "calendar-layout modern-calendar-layout", children: [_jsxs("section", { className: "content-card calendar-card", children: [_jsxs("div", { className: "calendar-month-header", children: [_jsxs("div", { className: "month-nav-group", children: [_jsx("button", { type: "button", className: "month-arrow", "aria-label": "Mois pr\u00E9c\u00E9dent", onClick: () => changeMonth(-1), children: "\u2039" }), _jsx("button", { type: "button", className: "today-jump-btn", onClick: jumpToToday, children: "Aujourd'hui" }), _jsx("button", { type: "button", className: "month-arrow", "aria-label": "Mois suivant", onClick: () => changeMonth(1), children: "\u203A" })] }), _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "AGENDA DE MODE" }), _jsx("h2", { children: monthName }), _jsxs("small", { className: "month-stat-sub", children: [currentMonthPlansCount, " tenue", currentMonthPlansCount > 1 ? "s" : "", " programm\u00E9e", currentMonthPlansCount > 1 ? "s" : ""] })] })] }), _jsxs("div", { className: "calendar-grid", children: [["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((day) => (_jsx("span", { className: "weekday", children: day }, day))), days.map((day, index) => {
                                        if (!day)
                                            return _jsx("span", { className: "calendar-blank" }, `blank-${index}`);
                                        const date = `${anchor.getFullYear()}-${String(anchor.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                                        const dayPlan = scheduled.find((entry) => entry.date === date);
                                        const hasOutfit = Boolean(dayPlan);
                                        return (_jsxs("button", { type: "button", className: `calendar-day${hasOutfit ? " has-outfit" : ""}${selectedDate === date ? " selected" : ""}${date === todayLocal() ? " is-today" : ""}`, "aria-label": `${day}${hasOutfit ? ", tenue planifiée" : ""}`, "aria-pressed": selectedDate === date, onClick: () => { setSelectedDate(date); setEditing(false); }, children: [dayPlan && _jsx(DayThumb, { plan: dayPlan }), _jsx("span", { className: "day-number", children: day }), hasOutfit && _jsx("span", { className: "day-outfit-dot", title: "Tenue planifi\u00E9e" })] }, date));
                                    })] }), loading && _jsx("p", { className: "inline-hint", children: "Synchronisation du calendrier\u2026" })] }), _jsxs("section", { className: "content-card day-details modern-day-details", children: [_jsxs("div", { className: "day-details-header", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: selectedDate === todayLocal() ? "AUJOURD'HUI" : "JOUR SÉLECTIONNÉ" }), _jsx("h2", { children: new Date(`${selectedDate}T12:00:00`).toLocaleDateString("fr-TN", { weekday: "long", day: "numeric", month: "long" }) })] }), _jsx("span", { className: `day-status-pill ${plan ? "status-planned" : "status-free"}`, children: plan ? "✦ Tenue prévue" : "Jour libre" })] }), plan && !editing ? (_jsxs(_Fragment, { children: [plan.render_image_url && (_jsxs("div", { className: "avatar-render-wrap", children: [_jsx("img", { className: "avatar-render", src: plan.render_image_url, alt: "Toi avec la tenue de ce jour" }), _jsx("span", { className: "avatar-render-badge", children: "\u2728 Rendu Avatar IA" })] })), _jsx("div", { className: "day-plan-images modern-day-plan-images", children: plan.items.map((item) => (_jsxs("div", { className: "day-plan-item-card", children: [_jsx("img", { src: item.image_url, alt: categoryLabel(item.category) }), _jsx("span", { children: categoryLabel(item.category) })] }, item.id))) }), _jsxs("p", { className: "day-plan-summary", children: [_jsx("b", { children: plan.items.length }), " pi\u00E8ce", plan.items.length > 1 ? "s" : "", " s\u00E9lectionn\u00E9e", plan.items.length > 1 ? "s" : "", " pour cette journ\u00E9e."] }), _jsxs("div", { className: "button-row", children: [!plan.render_image_url && (_jsx("button", { type: "button", className: "button button-outline", disabled: rendering, onClick: () => void renderOnAvatar(), children: rendering ? "Création du rendu… (≈ 1 min)" : "✦ Voir sur mon avatar" })), _jsx("button", { type: "button", className: "button button-primary", onClick: startEdit, children: "Modifier" }), _jsx("button", { type: "button", className: "button button-danger-light", onClick: () => void onRemove(selectedDate), children: "Retirer" })] })] })) : !editing ? (_jsxs("div", { className: "day-empty-state-wrap", children: [_jsx("div", { className: "day-empty-icon", children: "\u2727" }), _jsx("h3", { children: "Aucune tenue pour ce jour" }), _jsx("p", { className: "inline-hint", children: "S\u00E9lectionne les pi\u00E8ces de ton dressing pour composer ton look en toute s\u00E9r\u00E9nit\u00E9." }), _jsx("button", { type: "button", className: "button button-primary", onClick: startEdit, children: "\uFF0B Planifier un look" })] })) : (_jsxs(_Fragment, { children: [_jsx("p", { className: "inline-hint", children: "Clique sur les pi\u00E8ces de ton dressing \u00E0 associer pour cette date :" }), _jsx("div", { className: "calendar-pick-grid", children: items.map((item) => (_jsxs("button", { type: "button", className: `calendar-pick-item${selectedIds.includes(item.id) ? " picked" : ""}`, "aria-pressed": selectedIds.includes(item.id), onClick: () => setSelectedIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]), children: [_jsx("img", { src: item.image_url, alt: categoryLabel(item.category) }), _jsx("span", { children: categoryLabel(item.category) }), selectedIds.includes(item.id) && _jsx("span", { className: "picked-check", children: "\u2713" })] }, item.id))) }), items.length === 0 && _jsx("p", { className: "inline-hint", children: "Ajoute des pi\u00E8ces dans ton dressing avant de planifier." }), _jsxs("div", { className: "button-row", children: [_jsx("button", { type: "button", className: "button button-primary", disabled: saving || selectedIds.length === 0, onClick: () => void save(), children: saving ? "Enregistrement…" : `Valider la tenue (${selectedIds.length})` }), _jsx("button", { type: "button", className: "button button-ghost", onClick: () => setEditing(false), children: "Annuler" })] })] }))] })] })] });
}
function ProfileView({ user, profile, busy, onAvatar, onNavigate }) {
    const maxCount = profile ? Math.max(1, ...Object.values(profile.category_counts)) : 1;
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Mon profil de style", subtitle: "D\u00E9couvre ce que ton dressing r\u00E9v\u00E8le de tes pr\u00E9f\u00E9rences, tes couleurs signature et ton arch\u00E9type vestimentaire." }), _jsxs("div", { className: "profile-layout modern-profile-layout", children: [_jsxs("section", { className: "content-card profile-card", children: [_jsxs("div", { className: "profile-cover", children: [_jsx("span", { className: "profile-sun", children: "\u2600" }), _jsx("span", { className: "profile-flower", children: "\u273F" }), _jsx("span", { className: "profile-arch" })] }), _jsxs("div", { className: "profile-person", children: [_jsx(Avatar, { user: user, size: "large" }), _jsxs("div", { children: [_jsx("h2", { children: user?.full_name || "Mon espace DressMe" }), _jsx("p", { children: user?.email })] }), _jsxs("label", { className: `button button-outline file-button${busy === "avatar" ? " is-disabled" : ""}`, children: [busy === "avatar" ? "Envoi…" : user?.avatar_photo_url ? "Changer ma photo" : "Ajouter une photo", _jsx("input", { type: "file", accept: "image/*", disabled: busy === "avatar", onChange: (event) => { const file = event.target.files?.[0]; if (file)
                                                    void onAvatar(file); event.target.value = ""; } })] })] }), _jsxs("div", { className: "profile-stat-line", children: [_jsx("strong", { children: profile?.wardrobe_size ?? 0 }), _jsx("span", { children: "pi\u00E8ces enregistr\u00E9es au total" })] }), profile?.narrative && _jsxs("blockquote", { className: "style-narrative", children: ["\u201C", profile.narrative, "\u201D"] })] }), _jsxs("section", { className: "content-card profile-analysis-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "ADN & SIGNATURE VESTIMENTAIRE" }), _jsx("h3", { children: "R\u00E9partition de ta garde-robe" })] }) }), profile && Object.entries(profile.category_counts).length > 0 ? (_jsx("div", { className: "category-bars", children: Object.entries(profile.category_counts).sort((a, b) => b[1] - a[1]).map(([name, count]) => (_jsxs("div", { className: "category-bar-row", children: [_jsx("span", { children: categoryLabel(name) }), _jsx("div", { children: _jsx("i", { style: { width: `${(count / maxCount) * 100}%` } }) }), _jsxs("b", { children: [count, " (", Math.round((count / (profile.wardrobe_size || 1)) * 100), "%)"] })] }, name))) })) : (_jsx(EmptyState, { icon: "\u25C8", title: "Ton profil se construit", text: "Ajoute des v\u00EAtements dans ton dressing pour r\u00E9v\u00E9ler tes statistiques.", onAction: () => onNavigate("wardrobe"), action: "Ouvrir le dressing" })), _jsxs("div", { className: "preference-block", children: [_jsx("h4", { children: "Couleurs dominantes" }), _jsx("div", { className: "style-chips", children: profile?.favorite_colors.length ? profile.favorite_colors.map((color) => (_jsxs("span", { className: "color-chip-pill", children: ["\u25CF ", color] }, color))) : _jsx("small", { children: "Ajoute des pi\u00E8ces pour d\u00E9couvrir ta palette signature." }) }), _jsx("h4", { style: { marginTop: "16px" }, children: "Styles favoris" }), _jsx("div", { className: "style-chips", children: profile?.favorite_styles.length ? profile.favorite_styles.map((style) => (_jsxs("span", { className: "style-chip-pill", children: ["\u2727 ", style] }, style))) : _jsx("small", { children: "Ton style se d\u00E9couvrira au fil de tes ajouts." }) })] })] })] }), _jsxs("section", { className: "quick-actions profile-quick", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "CONTINUER L'EXP\u00C9RIENCE" }), _jsx("h3", { children: "Tes outils style" })] }), _jsxs("button", { type: "button", onClick: () => onNavigate("calendar"), children: [_jsx("span", { children: "\u25A6" }), _jsx("b", { children: "Calendrier" }), _jsx("small", { children: "Planifier un look" }), _jsx("i", { children: "\u2192" })] }), _jsxs("button", { type: "button", onClick: () => onNavigate("packing"), children: [_jsx("span", { children: "\u25A3" }), _jsx("b", { children: "Ma valise" }), _jsx("small", { children: "Pr\u00E9parer un voyage" }), _jsx("i", { children: "\u2192" })] }), _jsxs("button", { type: "button", onClick: () => onNavigate("tryon"), children: [_jsx("span", { children: "\u2726" }), _jsx("b", { children: "Essayage virtuel" }), _jsx("small", { children: "Tester une pi\u00E8ce" }), _jsx("i", { children: "\u2192" })] })] })] });
}
function PackingView({ lists, busy, onCreate, onToggle, onDelete }) {
    const [filterState, setFilterState] = useState({});
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Ma valise intelligente", subtitle: "Une s\u00E9lection optimis\u00E9e selon ta destination, la m\u00E9t\u00E9o et la dur\u00E9e de ton escapade." }), _jsxs("form", { className: "content-card packing-form modern-packing-form", onSubmit: (event) => void onCreate(event), children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "NOUVEAU VOYAGE" }), _jsx("h3", { children: "O\u00F9 pars-tu prochainement ?" })] }), _jsx("span", { className: "form-sparkle", children: "\u2708" })] }), _jsxs("div", { className: "form-grid", children: [_jsxs("label", { className: "field", children: [_jsx("span", { children: "Destination" }), _jsx("input", { name: "destination", required: true, placeholder: "Ex. Djerba, Paris, Rome..." })] }), _jsxs("label", { className: "field", children: [_jsx("span", { children: "Dur\u00E9e (jours)" }), _jsx("input", { name: "duration", type: "number", min: "1", max: "90", defaultValue: "4", required: true })] }), _jsxs("label", { className: "field", children: [_jsx("span", { children: "Type de s\u00E9jour" }), _jsxs("select", { name: "tripType", defaultValue: "plage", children: [_jsx("option", { value: "plage", children: "\uD83C\uDFD6\uFE0F Plage & D\u00E9tente" }), _jsx("option", { value: "business", children: "\uD83D\uDCBC Professionnel & Conf\u00E9rence" }), _jsx("option", { value: "tourisme", children: "\uD83C\uDFDB\uFE0F Tourisme & D\u00E9couverte" }), _jsx("option", { value: "f\u00EAte", children: "\uD83C\uDF89 F\u00EAte & \u00C9v\u00E9nement" })] })] }), _jsxs("label", { className: "field", children: [_jsx("span", { children: "Date de d\u00E9part (facultatif)" }), _jsx("input", { name: "startDate", type: "date" })] })] }), _jsxs("div", { className: "form-submit-row", children: [_jsx("p", { children: "L'IA s\u00E9lectionnera les pi\u00E8ces les plus polyvalentes et adapt\u00E9es de ton dressing." }), _jsx("button", { className: "button button-primary", disabled: busy === "packing-create", children: busy === "packing-create" ? "Préparation de la valise…" : "🎒 Générer ma valise →" })] })] }), lists.length === 0 ? (_jsx(EmptyState, { icon: "\u25A3", title: "Aucun voyage pr\u00E9vu pour l'instant", text: "Cr\u00E9e une liste de valise pour pr\u00E9parer ta prochaine escapade en quelques secondes." })) : (_jsx("div", { className: "packing-list-grid", children: lists.map((list) => {
                    const currentFilter = filterState[list.id] ?? "all";
                    const totalCount = list.items.length;
                    const packedCount = list.checked_item_ids.length;
                    const percent = totalCount ? Math.round((packedCount / totalCount) * 100) : 0;
                    const isComplete = totalCount > 0 && packedCount === totalCount;
                    const displayItems = list.items.filter((item) => {
                        const isPacked = list.checked_item_ids.includes(item.id);
                        if (currentFilter === "remaining")
                            return !isPacked;
                        if (currentFilter === "packed")
                            return isPacked;
                        return true;
                    });
                    return (_jsxs("article", { className: "content-card packing-list-card modern-packing-card", children: [_jsxs("div", { className: "packing-list-heading", children: [_jsxs("div", { children: [_jsxs("span", { className: "category-pill", children: [list.duration_days, " jours \u00B7 ", categoryLabel(list.trip_type), list.season && ` · ${itemSeasonLabel(list.season)}`] }), _jsx("h3", { children: list.destination })] }), _jsx("button", { className: "remove-link", type: "button", onClick: () => void onDelete(list.id), children: "Supprimer la liste" })] }), _jsxs("div", { className: "packing-progress", children: [_jsxs("div", { className: "packing-progress-labels", children: [_jsxs("span", { children: [_jsx("b", { children: packedCount }), " / ", totalCount, " pi\u00E8ces pr\u00EAtes"] }), _jsxs("span", { className: "packing-percent-tag", children: [percent, "%"] })] }), _jsx("i", { children: _jsx("b", { style: { width: `${percent}%` } }) }), isComplete && _jsx("span", { className: "packing-complete-badge", children: "\u2728 Valise 100% pr\u00EAte, bon voyage !" })] }), _jsxs("div", { className: "packing-filter-tabs", children: [_jsxs("button", { type: "button", className: currentFilter === "all" ? "active" : "", onClick: () => setFilterState((prev) => ({ ...prev, [list.id]: "all" })), children: ["Toutes (", totalCount, ")"] }), _jsxs("button", { type: "button", className: currentFilter === "remaining" ? "active" : "", onClick: () => setFilterState((prev) => ({ ...prev, [list.id]: "remaining" })), children: ["\u00C0 mettre (", totalCount - packedCount, ")"] }), _jsxs("button", { type: "button", className: currentFilter === "packed" ? "active" : "", onClick: () => setFilterState((prev) => ({ ...prev, [list.id]: "packed" })), children: ["Emball\u00E9es (", packedCount, ")"] })] }), _jsx("div", { className: "packing-items", children: displayItems.map((item) => {
                                    const checked = list.checked_item_ids.includes(item.id);
                                    return (_jsxs("label", { className: `packing-item${checked ? " packed" : ""}`, children: [_jsx("input", { type: "checkbox", checked: checked, onChange: () => void onToggle(list, item.id) }), _jsx("img", { src: item.image_url, alt: "" }), _jsx("span", { children: categoryLabel(item.category) }), checked && _jsx("small", { className: "item-packed-tag", children: "Pr\u00EAt \u2713" })] }, item.id));
                                }) }), list.items.length === 0 && _jsx("p", { className: "inline-hint", children: "Ajoute plus de pi\u00E8ces \u00E0 ton dressing pour enrichir cette liste." })] }, list.id));
                }) }))] });
}
const PURCHASE_CATEGORY_LABELS = {
    haut: "Haut", bas: "Bas", robe: "Robe", veste: "Veste",
    chaussures: "Chaussures", sac: "Sac", accessoire: "Accessoire",
};
const PURCHASE_VERDICTS = {
    recommended: "Recommandé",
    think_twice: "À réfléchir",
    not_recommended: "Déconseillé",
};
function openStorePage(url) {
    if (url)
        window.open(url, "_blank", "noopener,noreferrer");
}
function PurchaseView({ result, busy, onCheck, onRestoreResult }) {
    const [history, setHistory] = useState([]);
    const [wishlist, setWishlist] = useState([]);
    const [shopTab, setShopTab] = useState("history");
    const [activeHistoryId, setActiveHistoryId] = useState(null);
    const brands = result?.tunisian_brands ?? [];
    const savedKeys = useMemo(() => new Set(wishlist.map((item) => item.item_key)), [wishlist]);
    const refreshHistory = () => { getPurchaseHistory().then(setHistory).catch(() => { }); };
    const refreshWishlist = () => { getWishlist().then(setWishlist).catch(() => { }); };
    useEffect(() => { refreshHistory(); refreshWishlist(); }, []);
    useEffect(() => { refreshHistory(); }, [result]);
    const verdictText = result?.verdict === "recommended"
        ? "Coup de cœur : Cette pièce s’accorde à merveille avec ton dressing !"
        : result?.verdict === "think_twice"
            ? "À réfléchir : Tu possèdes déjà des pièces très similaires."
            : "Achat risqué : Cette pièce sera difficile à associer avec ton style actuel.";
    async function toggleSave(product) {
        if (!product.item_key)
            return;
        const key = product.item_key;
        if (savedKeys.has(key)) {
            setWishlist((current) => current.filter((item) => item.item_key !== key));
            await removeFromWishlist(key).catch(refreshWishlist);
        }
        else {
            await addToWishlist(key).then((entry) => {
                setWishlist((current) => [entry, ...current.filter((item) => item.item_key !== key)]);
            }).catch(refreshWishlist);
        }
    }
    function openHistory(item) {
        setActiveHistoryId(item.id);
        onRestoreResult(item.result);
    }
    function removeHistory(item) {
        setHistory((current) => current.filter((entry) => entry.id !== item.id));
        if (item.id === activeHistoryId)
            setActiveHistoryId(null);
        deleteHistoryEntry(item.id).catch(refreshHistory);
    }
    function ProductCard({ product }) {
        const saved = product.item_key != null && savedKeys.has(product.item_key);
        const href = product.product_url || product.store_url;
        return (_jsxs("article", { className: "alternative-card", children: [product.image_url ? _jsx("img", { src: product.image_url, alt: product.name }) : _jsx("span", { className: "alternative-placeholder", children: "\u2727" }), _jsxs("div", { children: [_jsx("b", { children: product.name }), _jsx("small", { children: [product.brand, product.category].filter(Boolean).join(" · ") }), _jsx("strong", { children: formatTnd(product.price) ?? "Prix n.c." })] }), _jsxs("div", { className: "purchase-card-actions", children: [product.item_key && (_jsx("button", { type: "button", className: `wish-heart${saved ? " is-saved" : ""}`, onClick: () => void toggleSave(product), title: saved ? "Retirer de la wishlist" : "Ajouter à la wishlist", children: saved ? "♥" : "♡" })), href && (_jsxs("a", { className: "store-link", href: href, target: "_blank", rel: "noreferrer", children: [product.buyable ? "Acheter" : "Voir", " \u2197"] }))] })] }));
    }
    return _jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "J\u2019ach\u00E8te ou pas ?", subtitle: "Un doute en boutique ou en ligne ? T\u00E9l\u00E9verse la photo d'un v\u00EAtement pour v\u00E9rifier sa compatibilit\u00E9 avant d'acheter." }), _jsxs("div", { className: "purchase-layout modern-purchase-layout", children: [_jsxs("section", { className: "content-card purchase-card", children: [_jsx("span", { className: "eyebrow", children: "CONSEILLER D'ACHAT IA" }), _jsx("h2", { children: "Une pi\u00E8ce te fait envie ?" }), _jsx("p", { children: "Prends une photo ou fais une capture d'\u00E9cran de l'article convoit\u00E9. DressMe analyse instantan\u00E9ment sa couleur, sa coupe et v\u00E9rifie son harmonie avec l'ensemble de ton dressing." }), _jsxs("label", { className: `upload-drop${busy === "purchase" ? " is-loading" : ""}`, children: [_jsx("input", { type: "file", accept: "image/*", disabled: busy === "purchase", onChange: (event) => {
                                            const file = event.target.files?.[0];
                                            if (file)
                                                void onCheck(file);
                                            event.target.value = "";
                                        } }), _jsx("span", { className: "upload-icon", children: busy === "purchase" ? "◌" : "📷" }), _jsx("strong", { children: busy === "purchase" ? "Analyse FashionCLIP & RAG en cours…" : "Choisir ou déposer la photo du vêtement" }), _jsx("small", { children: "JPG, PNG, WebP \u00B7 Analyse instantan\u00E9e et priv\u00E9e" })] }), _jsx("p", { className: "privacy-note", children: "\uD83D\uDD12 Analyse 100% confidentielle li\u00E9e \u00E0 ton dressing." })] }), _jsx("section", { className: "content-card purchase-result modern-purchase-result", children: result ? (_jsxs(_Fragment, { children: [_jsxs("div", { className: `verdict-banner verdict-${result.verdict}`, children: [_jsx("span", { className: "verdict-icon", children: result.verdict === "recommended" ? "✓" : result.verdict === "think_twice" ? "⚠️" : "×" }), _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "VERDICT DU STYLISTE" }), _jsx("h2", { children: verdictText })] })] }), _jsxs("div", { className: "compatibility-meter modern-compat-meter", children: [_jsxs("div", { className: "meter-header", children: [_jsx("span", { children: "Score d\u2019harmonie avec ton dressing" }), _jsx("b", { children: result.score ?? Math.round(result.compatibility_score * 100) })] }), _jsx("i", { className: "meter-track", children: _jsx("b", { className: `meter-bar ${result.verdict}`, style: { width: `${Math.min(100, Math.max(0, result.compatibility_score * 100))}%` } }) })] }), _jsxs("div", { className: "verdict-explanation-box", children: [_jsx("h4", { children: "\u2726 Analyse du styliste :" }), _jsx("p", { className: "verdict-explanation", children: result.explanation })] }), result.catalog_alternatives.length > 0 && (_jsxs("div", { className: "alternatives-section", children: [_jsx("h3", { children: "Alternatives en Tunisie" }), _jsx("p", { className: "section-hint", children: "Trouv\u00E9es par ressemblance visuelle (FashionCLIP) \u2014 ouvre la page produit de la marque." }), _jsx("div", { className: "alternatives", children: result.catalog_alternatives.map((alternative, index) => (_jsx(ProductCard, { product: alternative }, alternative.item_key ?? `${alternative.name}-${index}`))) })] })), brands.length > 0 && (_jsxs("div", { className: "brands-section", children: [_jsx("h3", { children: "Marques tunisiennes pour toi" }), _jsx("p", { className: "section-hint", children: "Class\u00E9es par affinit\u00E9 visuelle avec cet article et ton style." }), brands.map((brand, rank) => {
                                            const best = brands[0].affinity || 1;
                                            const match = Math.round((brand.affinity / best) * 100);
                                            return (_jsxs("article", { className: "brand-card", children: [_jsxs("div", { className: "brand-card-top", children: [_jsx("span", { className: `brand-rank${rank === 0 ? " is-first" : ""}`, children: rank + 1 }), _jsxs("div", { children: [_jsx("b", { children: brand.name }), _jsxs("small", { children: [brand.product_count, " articles similaires", brand.price_min != null && brand.price_max != null
                                                                                ? ` · ${formatTnd(brand.price_min)} – ${formatTnd(brand.price_max)}`
                                                                                : ""] }), _jsx("i", { className: "brand-affinity", children: _jsx("b", { style: { width: `${match}%` } }) })] }), brand.website && (_jsx("a", { className: "store-link", href: brand.website, target: "_blank", rel: "noreferrer", children: "Site \u2197" }))] }), brand.showcase.length > 0 && (_jsx("div", { className: "brand-showcase", children: brand.showcase.map((product, index) => (_jsxs("button", { type: "button", className: "showcase-item", onClick: () => openStorePage(product.product_url || product.store_url || brand.website), children: [product.image_url ? _jsx("img", { src: product.image_url, alt: "" }) : _jsx("span", { children: "\u2727" }), _jsx("b", { children: product.name }), _jsx("small", { children: formatTnd(product.price) ?? "Prix n.c." })] }, product.item_key ?? `${product.name}-${index}`))) }))] }, brand.name));
                                        })] }))] })) : (_jsx(EmptyState, { icon: "\u2661", title: "En attente d'une pi\u00E8ce \u00E0 analyser", text: "T\u00E9l\u00E9verse la photo d'un v\u00EAtement \u00E0 gauche pour d\u00E9couvrir le score de compatibilit\u00E9, les alternatives tunisiennes et nos conseils d'achat." })) })] }), _jsxs("section", { className: "content-card shopping-space", children: [_jsxs("div", { className: "shopping-space-head", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "MON ESPACE SHOPPING" }), _jsx("h2", { children: "Historique et wishlist" }), _jsx("p", { children: "Tes analyses et tes coups de c\u0153ur, suivis en direct." })] }), _jsxs("div", { className: "shopping-stats", children: [_jsxs("span", { children: [_jsx("b", { children: history.length }), " analyses"] }), _jsxs("span", { children: [_jsx("b", { children: wishlist.length }), " wishlist"] })] })] }), _jsxs("div", { className: "shopping-tabs", children: [_jsxs("button", { type: "button", className: shopTab === "history" ? "active" : "", onClick: () => setShopTab("history"), children: ["Historique (", history.length, ")"] }), _jsxs("button", { type: "button", className: shopTab === "wishlist" ? "active" : "", onClick: () => setShopTab("wishlist"), children: ["Wishlist (", wishlist.length, ")"] })] }), shopTab === "history" ? (history.length === 0 ? (_jsx("p", { className: "inline-hint", children: "Chaque article analys\u00E9 est enregistr\u00E9 ici, pour le revoir en un geste." })) : (_jsxs("div", { className: "shopping-list", children: [history.map((item) => (_jsxs("article", { className: `shopping-row${item.id === activeHistoryId ? " is-active" : ""}`, children: [_jsxs("button", { type: "button", className: "shopping-row-main", onClick: () => openHistory(item), children: [_jsx("img", { src: item.image_url, alt: "" }), _jsxs("div", { children: [_jsxs("b", { children: [PURCHASE_CATEGORY_LABELS[item.category] ?? item.category, item.color ? ` · ${item.color}` : ""] }), _jsxs("small", { className: `verdict-tag verdict-${item.verdict}`, children: [PURCHASE_VERDICTS[item.verdict], " \u00B7 ", item.score] })] })] }), _jsx("button", { type: "button", className: "text-button", onClick: () => removeHistory(item), children: "Supprimer" })] }, item.id))), _jsx("button", { type: "button", className: "text-button danger", onClick: () => { setHistory([]); setActiveHistoryId(null); clearPurchaseHistory().catch(refreshHistory); }, children: "Effacer tout l'historique" })] }))) : wishlist.length === 0 ? (_jsx("p", { className: "inline-hint", children: "Touche \u2661 sur une alternative : on suit son prix et on ouvre la page de la marque." })) : (_jsx("div", { className: "shopping-list", children: wishlist.map((item) => (_jsxs("article", { className: "shopping-row", children: [_jsxs("button", { type: "button", className: "shopping-row-main", onClick: () => openStorePage(item.product_url || item.store_url), children: [item.image_url ? _jsx("img", { src: item.image_url, alt: "" }) : _jsx("span", { className: "alternative-placeholder", children: "\u2661" }), _jsxs("div", { children: [_jsx("b", { children: item.name }), _jsx("small", { children: [item.brand, formatTnd(item.live_price ?? item.saved_price)].filter(Boolean).join(" · ") })] })] }), _jsx("button", { type: "button", className: "text-button", onClick: () => { setWishlist((current) => current.filter((entry) => entry.item_key !== item.item_key)); removeFromWishlist(item.item_key).catch(refreshWishlist); }, children: "Retirer" })] }, item.item_key))) }))] })] });
}
const PRESET_AVATARS = [
    {
        id: "model-female-1",
        name: "Modèle Femme 1",
        gender: "Femme",
        url: "/models/model-female-1.jpg",
        tag: "Athlétique",
    },
    {
        id: "model-female-2",
        name: "Modèle Femme 2",
        gender: "Femme",
        url: "/models/model-female-2.jpg",
        tag: "Élancée",
    },
    {
        id: "model-male-1",
        name: "Modèle Homme 1",
        gender: "Homme",
        url: "/models/model-male-1.jpg",
        tag: "Classique",
    },
];
function TryOnView({ user, items, selectedIds, result, busy, onToggleSelect, onClearSelect, onSelectPresetAvatar, onAvatar, onTryOn, }) {
    const [categoryFilter, setCategoryFilter] = useState("all");
    const categories = [
        { id: "all", label: "Toutes les pièces" },
        { id: "haut", label: "Hauts" },
        { id: "bas", label: "Bas" },
        { id: "robe", label: "Robes" },
        { id: "veste", label: "Vestes" },
    ];
    const filteredItems = categoryFilter === "all"
        ? items
        : items.filter((it) => it.category === categoryFilter);
    const selectedPieces = items.filter((it) => selectedIds.includes(it.id));
    // Determine active preset (if any)
    const activePreset = PRESET_AVATARS.find((preset) => {
        if (!user?.avatar_photo_url)
            return false;
        return (user.avatar_photo_url.includes(preset.url) ||
            user.avatar_photo_url.includes(preset.id));
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Studio d\u2019Essayage Virtuel \u2728", subtitle: "Choisis un mannequin de r\u00E9f\u00E9rence ou ta photo, s\u00E9lectionne une ou plusieurs pi\u00E8ces et visualise ta tenue en haute d\u00E9finition." }), _jsxs("div", { className: "tryon-studio-layout", children: [_jsxs("section", { className: "tryon-card-premium", children: [_jsx("span", { className: "tryon-step-badge", children: "\u00C9tape 01 \u00B7 Mannequin" }), _jsx("h3", { className: "tryon-step-title", children: "Ton Mannequin de R\u00E9f\u00E9rence" }), _jsx("p", { className: "tryon-step-desc", children: "S\u00E9lectionne l\u2019un des 3 mannequins ci-dessous en un clic, ou t\u00E9l\u00E9verse ta propre photo en pied." }), _jsxs("div", { className: "tryon-presets-title", children: [_jsx("span", { children: "Mannequins d\u2019Exemple" }), _jsx("span", { style: { fontSize: "11px", color: "var(--rose)", fontWeight: 700 }, children: "3 mod\u00E8les pr\u00EAts" })] }), _jsx("div", { className: "tryon-presets-grid", children: PRESET_AVATARS.map((preset) => {
                                    const isSelected = activePreset?.id === preset.id ||
                                        user?.avatar_photo_url?.includes(preset.url);
                                    return (_jsxs("button", { type: "button", className: `tryon-preset-card${isSelected ? " is-active" : ""}`, onClick: () => void onSelectPresetAvatar(preset.url), disabled: busy === "avatar", title: `Choisir ${preset.name}`, children: [_jsx("div", { className: "tryon-preset-img-wrap", children: _jsx("img", { src: preset.url, alt: preset.name }) }), _jsx("span", { className: "tryon-preset-name", children: preset.name }), _jsx("span", { className: "tryon-preset-tag", children: preset.tag }), isSelected && _jsx("span", { className: "tryon-preset-check", children: "\u2713" })] }, preset.id));
                                }) }), _jsx("div", { className: "tryon-active-preview", children: user?.avatar_photo_url ? (_jsxs(_Fragment, { children: [_jsx("img", { src: user.avatar_photo_url, alt: "Photo du mod\u00E8le actif" }), _jsx("span", { className: "tryon-active-badge", children: activePreset
                                                ? `✦ ${activePreset.name} sélectionné`
                                                : "✦ Photo personnelle active" })] })) : (_jsxs("div", { style: { padding: "30px 15px", textAlign: "center", color: "#64748b" }, children: [_jsx("span", { style: { fontSize: "32px", display: "block", marginBottom: "6px" }, children: "\uD83D\uDC64" }), _jsx("strong", { style: { fontSize: "13px", color: "var(--navy)" }, children: "Aucun mannequin s\u00E9lectionn\u00E9" }), _jsx("p", { style: { fontSize: "11px", margin: "4px 0 0" }, children: "Clique sur un mod\u00E8le ci-dessus pour l\u2019activer." })] })) }), _jsxs("label", { className: "tryon-upload-btn", children: [_jsx("span", { children: busy === "avatar" ? "⏳ Envoi en cours…" : "📷 Importer ma propre photo en pied" }), _jsx("input", { type: "file", accept: "image/*", disabled: busy === "avatar", onChange: (event) => {
                                            const file = event.target.files?.[0];
                                            if (file)
                                                void onAvatar(file);
                                            event.target.value = "";
                                        } })] })] }), _jsxs("section", { className: "tryon-card-premium", children: [_jsxs("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px" }, children: [_jsxs("div", { children: [_jsx("span", { className: "tryon-step-badge", children: "\u00C9tape 02 \u00B7 Dressing" }), _jsx("h3", { className: "tryon-step-title", children: "Compose ta Tenue" }), _jsxs("p", { className: "tryon-step-desc", children: ["Tu peux choisir ", _jsx("strong", { children: "plus d\u2019un v\u00EAtement" }), " (ex: Haut + Bas, ou Veste + Robe) pour un look complet."] })] }), selectedIds.length > 0 && (_jsxs("button", { type: "button", className: "text-button", style: { fontSize: "12px", color: "var(--rose)", fontWeight: 700, padding: "4px 8px" }, onClick: onClearSelect, children: ["Tout d\u00E9s\u00E9lectionner (", selectedIds.length, ")"] }))] }), _jsx("div", { className: "tryon-cat-filter", children: categories.map((cat) => (_jsx("button", { type: "button", className: `tryon-pill${categoryFilter === cat.id ? " is-active" : ""}`, onClick: () => setCategoryFilter(cat.id), children: cat.label }, cat.id))) }), filteredItems.length > 0 ? (_jsx("div", { className: "tryon-garments-grid", children: filteredItems.map((item) => {
                                    const isSelected = selectedIds.includes(item.id);
                                    return (_jsxs("button", { type: "button", className: `tryon-garment-card${isSelected ? " is-selected" : ""}`, "aria-pressed": isSelected, onClick: () => onToggleSelect(item.id), children: [_jsx("img", { className: "tryon-garment-img", src: item.image_url, alt: categoryLabel(item.category) }), _jsxs("div", { className: "tryon-garment-footer", children: [_jsx("span", { className: "tryon-garment-cat", children: categoryLabel(item.category) }), item.colors && item.colors[0] && (_jsx("span", { style: { fontSize: "9px", color: "#94a3b8" }, children: item.colors[0] }))] }), isSelected && _jsx("span", { className: "tryon-garment-check", children: "\u2713" })] }, item.id));
                                }) })) : (_jsx(EmptyState, { icon: "\u25C8", title: "Aucune pi\u00E8ce trouv\u00E9e", text: "Ajoute des pi\u00E8ces dans ton dressing pour pouvoir les essayer." })), selectedPieces.length > 0 && (_jsx("div", { className: "tryon-selection-dock", children: _jsxs("div", { style: { width: "100%" }, children: [_jsxs("span", { style: { fontSize: "11px", fontWeight: 700, color: "var(--navy)", textTransform: "uppercase", letterSpacing: "0.5px" }, children: ["Tenue s\u00E9lectionn\u00E9e (", selectedPieces.length, " ", selectedPieces.length === 1 ? "pièce" : "pièces", ") :"] }), _jsx("div", { className: "tryon-selected-pieces", style: { marginTop: "6px" }, children: selectedPieces.map((piece) => (_jsxs("div", { className: "tryon-piece-chip", children: [_jsx("img", { src: piece.image_url, alt: "" }), _jsx("span", { children: categoryLabel(piece.category) }), _jsx("button", { type: "button", "aria-label": "Retirer cette pi\u00E8ce", onClick: (e) => {
                                                            e.stopPropagation();
                                                            onToggleSelect(piece.id);
                                                        }, children: "\u00D7" })] }, piece.id))) })] }) })), _jsx("button", { type: "button", className: "tryon-cta-btn", disabled: !user?.avatar_photo_url || selectedIds.length === 0 || busy === "tryon", onClick: () => void onTryOn(), children: busy === "tryon" ? (_jsxs(_Fragment, { children: [_jsx("span", { className: "tryon-spinner" }), _jsx("span", { children: "G\u00E9n\u00E9ration du look en cours\u2026" })] })) : selectedIds.length > 1 ? (_jsxs(_Fragment, { children: [_jsx("span", { children: "\u2728" }), _jsxs("span", { children: ["Essayer la tenue compl\u00E8te (", selectedIds.length, " pi\u00E8ces)"] })] })) : selectedIds.length === 1 ? (_jsxs(_Fragment, { children: [_jsx("span", { children: "\u2728" }), _jsx("span", { children: "Essayer cette pi\u00E8ce" })] })) : (_jsx("span", { children: "S\u00E9lectionne au moins une pi\u00E8ce" })) }), !user?.avatar_photo_url && (_jsx("p", { className: "inline-hint", style: { marginTop: "10px", textAlign: "center" }, children: "\uD83D\uDC48 Choisis d\u2019abord un mannequin \u00E0 gauche pour d\u00E9marrer." })), busy === "tryon" && (_jsxs("div", { className: "tryon-generating-state", children: [_jsx("span", { className: "tryon-spinner" }), _jsxs("div", { children: [_jsx("strong", { style: { fontSize: "13px", color: "var(--rose)" }, children: "L\u2019IA habille ton mannequin\u2026" }), _jsx("p", { style: { margin: "2px 0 0", fontSize: "11px", color: "#64748b" }, children: "G\u00E9n\u00E9ration haute d\u00E9finition en cours. Cela prend g\u00E9n\u00E9ralement entre 30 et 60 secondes." })] })] }))] })] }), result && (_jsxs("section", { className: "tryon-showcase", id: "tryon-result-section", children: [_jsx("span", { className: "tryon-step-badge", children: "\u00C9tape 03 \u00B7 Rendu Haute Couture" }), _jsx("h2", { style: { fontFamily: '"Playfair Display", Georgia, serif', fontSize: "28px", color: "var(--navy)", margin: "8px 0 6px" }, children: "Voil\u00E0 ton look g\u00E9n\u00E9r\u00E9 \u2728" }), _jsx("p", { style: { fontSize: "14px", color: "#64748b", margin: "0 auto 16px", maxWidth: "540px" }, children: "Voici le r\u00E9sultat de l\u2019essayage virtuel combinant ton mod\u00E8le et les pi\u00E8ces s\u00E9lectionn\u00E9es." }), _jsx("img", { className: "tryon-showcase-img", src: result, alt: "R\u00E9sultat de l\u2019essayage virtuel" }), _jsx("div", { className: "tryon-showcase-actions", children: _jsx("a", { href: result, target: "_blank", rel: "noopener noreferrer", className: "button button-primary", style: { padding: "11px 22px", textDecoration: "none" }, download: "mon-look-dressme.jpg", children: "\uD83D\uDCE5 Enregistrer / Ouvrir l\u2019image" }) })] }))] }));
}
/* ========================================================
   MODAL CONFIRMATION : DONNER OU SUPPRIMER ?
   ======================================================== */
function DonationPromptModal({ item, onDonate, onDeletePermanent, onCancel, }) {
    return (_jsx("div", { className: "modal-backdrop", onClick: onCancel, children: _jsxs("div", { className: "donation-prompt-modal", onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: "donation-prompt-header", children: [_jsx("div", { className: "donation-prompt-icon", children: "\uD83C\uDF81" }), _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "SECONDE VIE & SOLIDARIT\u00C9" }), _jsx("h2", { children: "Que souhaites-tu faire de cette pi\u00E8ce\u00A0?" })] }), _jsx("button", { type: "button", className: "modal-close", onClick: onCancel, "aria-label": "Fermer", children: "\u2715" })] }), _jsxs("div", { className: "donation-prompt-body", children: [_jsxs("div", { className: "donation-prompt-item-preview", children: [_jsx("img", { src: item.image_url, alt: categoryLabel(item.category) }), _jsxs("div", { children: [_jsx("strong", { children: categoryLabel(item.category) }), _jsx("small", { children: itemSeasonLabel(item.season) ?? "Toutes saisons" })] })] }), _jsx("p", { className: "donation-prompt-intro", children: "Plut\u00F4t que de simplement l\u2019effacer, tu peux offrir une seconde vie utile \u00E0 ce v\u00EAtement en le mettant en donation pour des associations caritatives en Tunisie." }), _jsxs("div", { className: "donation-prompt-choices", children: [_jsxs("div", { className: "donation-choice-box recommended", children: [_jsx("div", { className: "donation-choice-badge", children: "\u2726 RECOMMAND\u00C9 & \u00C9CO-RESPONSABLE" }), _jsxs("div", { className: "donation-choice-header", children: [_jsx("span", { className: "choice-icon", children: "\uD83C\uDF81" }), _jsxs("div", { children: [_jsx("h4", { children: "Transf\u00E9rer vers mes dons" }), _jsxs("p", { children: ["Cette pi\u00E8ce sera retir\u00E9e de ton dressing et archiv\u00E9e dans ta page ", _jsx("b", { children: "\u00AB Dons & Seconde vie \u00BB" }), ". Tu pourras y trouver des associations partenaires proches pour la d\u00E9poser."] })] })] }), _jsxs("button", { type: "button", className: "button button-primary donation-action-btn", onClick: () => void onDonate(item), children: [_jsx("span", { children: "\uD83C\uDF81" }), " Mettre en donation"] })] }), _jsxs("div", { className: "donation-choice-box secondary", children: [_jsxs("div", { className: "donation-choice-header", children: [_jsx("span", { className: "choice-icon", children: "\uD83D\uDDD1\uFE0F" }), _jsxs("div", { children: [_jsx("h4", { children: "Supprimer d\u00E9finitivement" }), _jsx("p", { children: "Efface irr\u00E9vocablement ce v\u00EAtement de ton dressing et de la base de donn\u00E9es." })] })] }), _jsx("button", { type: "button", className: "button button-ghost danger-ghost-btn", onClick: () => void onDeletePermanent(item), children: "Supprimer sans donner" })] })] })] }), _jsx("div", { className: "donation-prompt-footer", children: _jsx("button", { type: "button", className: "button button-outline", onClick: onCancel, children: "Annuler et conserver dans mon dressing" }) })] }) }));
}
/* ========================================================
   VUE DONS & SECONDE VIE
   ======================================================== */
const TUNISIAN_DONATION_ORGS = [
    {
        id: "croissant_rouge",
        name: "Croissant-Rouge Tunisien",
        subtitle: "Comités locaux & Banques vestimentaires nationales",
        badge: "Collecte permanente & Maraudes",
        cities: ["Tunis", "Sousse", "Sfax", "Nabeul", "Bizerte", "Ariana"],
        address: "Avenue de la Gare / Lafayette, Tunis (et comités régionaux)",
        phone: "+216 71 320 088",
        email: "contact@croissant-rouge.tn",
        accepted: ["Hommes", "Femmes", "Enfants", "Manteaux chauds", "Couvertures", "Chaussures"],
        description: "Le Croissant-Rouge redistribue directement les vêtements aux familles nécessiteuses, organise des caravanes solidaires grand froid et des maraudes auprès des sans-abri.",
        hours: "Du lundi au samedi : 08h30 - 16h30",
    },
    {
        id: "darna",
        name: "Association DARNA",
        subtitle: "Pour les enfants privés de soutien familial",
        badge: "Spécial Bébés & Enfants",
        cities: ["Tunis", "La Marsa", "Carthage"],
        address: "La Marsa & El Menzah, Grand Tunis",
        phone: "+216 71 740 500",
        email: "contact@darna.org.tn",
        accepted: ["Bébés (0-3 ans)", "Enfants (4-12 ans)", "Adolescents", "Pyjamas", "Baskets"],
        description: "DARNA crée des foyers de vie chaleureux pour les enfants sans soutien familial et prend en charge l'ensemble de leurs besoins éducatifs et vestimentaires.",
        hours: "Du lundi au vendredi : 09h00 - 17h00",
    },
    {
        id: "sos_villages",
        name: "SOS Villages d’Enfants Tunisie",
        subtitle: "Prise en charge fraternelle d'orphelins et enfants vulnérables",
        badge: "Villages d'enfants",
        cities: ["Tunis", "Sousse", "Mahdia", "Siliana"],
        address: "Villages de Gammarth, Akouda (Sousse), Mahdia et Siliana",
        phone: "+216 71 919 600",
        email: "contact@sosve.tn",
        accepted: ["Vêtements enfants", "Sportswear", "Tenues scolaires", "Baskets", "Pulls"],
        description: "Accompagne des centaines d'enfants orphelins ou abandonnés au sein de maisons familiales. Vos dons habillent directement les enfants pour leur rentrée et leur quotidien.",
        hours: "Du lundi au samedi : 09h00 - 17h00",
    },
    {
        id: "bourse_etudiante",
        name: "Banque Solidaire du Vêtement Étudiant",
        subtitle: "Soutien aux étudiants universitaires en situation précaire",
        badge: "Insertion & Entretiens",
        cities: ["Tunis", "La Manouba"],
        address: "Campus Universitaire Tunis El Manar & La Manouba",
        phone: "+216 71 872 600",
        email: "solidarite@bse-tunisie.org",
        accepted: ["Chemises", "Blazers / Costumes", "Tailleurs", "Manteaux", "Chaussures de ville"],
        description: "Permet aux étudiants boursiers d'accéder gratuitement à des tenues soignées pour leurs entretiens de stage, soutenances de mémoire et premiers emplois.",
        hours: "Mardi et Jeudi : 10h00 - 15h00",
    },
    {
        id: "caravanes_hiver",
        name: "Caravanes Hiver Chaud (Lions & Rotary Clubs)",
        subtitle: "Campagnes de lutte contre le grand froid dans les zones intérieures",
        badge: "Caravanes saisonnières",
        cities: ["Tunis", "Nabeul", "Sousse", "Sfax", "Bizerte", "Monastir"],
        address: "Points de collecte éphémères et sièges de clubs partenaires",
        phone: "+216 98 421 550",
        email: "caravanes.hiver@solidarite.tn",
        accepted: ["Pulls en laine", "Anoraks", "Bonnets & Écharpes", "Bottes", "Plaids chauds"],
        description: "Convois humanitaires acheminant chaque hiver des milliers de pièces chaudes dans les écoles rurales et villages des gouvernorats de Jendouba, Kasserine, Le Kef et Siliana.",
        hours: "Campagnes d’hiver : Octobre à Février",
    },
    {
        id: "friperies_circulaires",
        name: "Collecteurs Textiles Circulaires & Éco-Recyclage",
        subtitle: "Bornes textiles et valorisation de fibres pour zéro déchet",
        badge: "Recyclage & Upcycling",
        cities: ["Tunis", "Sousse", "Sfax", "Djerba"],
        address: "Bornes partenaires en centres commerciaux et friperies solidaires",
        phone: "+216 70 855 200",
        email: "eco@textile-circulaire.tn",
        accepted: ["Tous textiles", "Même usés ou déchirés", "Chutes de tissus", "Rideaux"],
        description: "Les vêtements trop abîmés pour être portés sont effilochés pour fabriquer de l'isolant écologique pour bâtiments et de nouveaux fils upcyclés en Tunisie.",
        hours: "Bornes extérieures accessibles 24h/24, 7j/7",
    },
];
function DonationView({ donations, onMarkDonated, onRestoreToWardrobe, onRemoveDonation, onUpdateCondition, onNavigate, }) {
    const [activeTab, setActiveTab] = useState("all");
    const [selectedCity, setSelectedCity] = useState("Toutes");
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedDonationForOrg, setSelectedDonationForOrg] = useState(null);
    const pendingCount = donations.filter((d) => d.status === "pending").length;
    const donatedCount = donations.filter((d) => d.status === "donated").length;
    const totalCount = donations.length;
    // Ecological impact metrics
    const waterSavedLiters = totalCount * 2700;
    const co2SavedKg = Math.round(totalCount * 12);
    const filteredDonations = donations.filter((d) => {
        if (activeTab === "pending")
            return d.status === "pending";
        if (activeTab === "donated")
            return d.status === "donated";
        return true;
    });
    const CITIES_LIST = ["Toutes", "Tunis", "Sousse", "Sfax", "Nabeul", "Bizerte", "Djerba"];
    const filteredOrgs = TUNISIAN_DONATION_ORGS.filter((org) => {
        if (selectedCity !== "Toutes" && !org.cities.includes(selectedCity))
            return false;
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            const matchName = org.name.toLowerCase().includes(q);
            const matchSub = org.subtitle.toLowerCase().includes(q);
            const matchAccepted = org.accepted.some((a) => a.toLowerCase().includes(q));
            const matchCities = org.cities.some((c) => c.toLowerCase().includes(q));
            if (!matchName && !matchSub && !matchAccepted && !matchCities)
                return false;
        }
        return true;
    });
    return (_jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Dons & Seconde vie", subtitle: "Donne une deuxi\u00E8me vie \u00E0 tes v\u00EAtements oubli\u00E9s, r\u00E9duis ton empreinte textile et soutiens des associations caritatives en Tunisie." }), _jsxs("section", { className: "donation-impact-banner", children: [_jsxs("div", { className: "donation-impact-copy", children: [_jsx("span", { className: "eyebrow", children: "MODE CIRCULAIRE & SOLIDARIT\u00C9" }), _jsx("h2", { children: "Ton impact positif pour la plan\u00E8te et les autres" }), _jsx("p", { children: "Chaque v\u00EAtement r\u00E9employ\u00E9 \u00E9vite des milliers de litres d'eau de fabrication et apporte chaleur et dignit\u00E9 \u00E0 une personne dans le besoin." })] }), _jsxs("div", { className: "donation-impact-grid", children: [_jsxs("div", { className: "donation-stat-card", children: [_jsx("span", { className: "stat-icon", children: "\uD83C\uDF81" }), _jsx("strong", { children: pendingCount }), _jsxs("small", { children: ["Pi\u00E8ce", pendingCount > 1 ? "s" : "", " pr\u00EAte", pendingCount > 1 ? "s" : "", " \u00E0 donner"] })] }), _jsxs("div", { className: "donation-stat-card", children: [_jsx("span", { className: "stat-icon gold", children: "\u2728" }), _jsx("strong", { children: donatedCount }), _jsxs("small", { children: ["Pi\u00E8ce", donatedCount > 1 ? "s" : "", " d\u00E9j\u00E0 donn\u00E9e", donatedCount > 1 ? "s" : ""] })] }), _jsxs("div", { className: "donation-stat-card", children: [_jsx("span", { className: "stat-icon blue", children: "\uD83D\uDCA7" }), _jsxs("strong", { children: [waterSavedLiters.toLocaleString("fr-FR"), " L"] }), _jsx("small", { children: "Eau douce pr\u00E9serv\u00E9e" })] }), _jsxs("div", { className: "donation-stat-card", children: [_jsx("span", { className: "stat-icon green", children: "\uD83C\uDF0D" }), _jsxs("strong", { children: [co2SavedKg, " kg"] }), _jsx("small", { children: "\u00C9missions CO\u2082 \u00E9vit\u00E9es" })] })] })] }), _jsxs("section", { className: "content-card modern-packing-card", style: { marginBottom: "26px" }, children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "MON TROUSSEAU SOLIDAIRE" }), _jsxs("h3", { children: ["Mes v\u00EAtements en attente de don (", donations.length, ")"] })] }), _jsx("button", { type: "button", className: "button button-outline", onClick: () => onNavigate("wardrobe"), children: "\uFF0B Ajouter depuis mon dressing" })] }), _jsxs("div", { className: "packing-filter-tabs", children: [_jsxs("button", { type: "button", className: activeTab === "all" ? "active" : "", onClick: () => setActiveTab("all"), children: ["Toutes (", totalCount, ")"] }), _jsxs("button", { type: "button", className: activeTab === "pending" ? "active" : "", onClick: () => setActiveTab("pending"), children: ["En attente (", pendingCount, ")"] }), _jsxs("button", { type: "button", className: activeTab === "donated" ? "active" : "", onClick: () => setActiveTab("donated"), children: ["Donn\u00E9es avec succ\u00E8s (", donatedCount, ")"] })] }), filteredDonations.length === 0 ? (_jsx(EmptyState, { icon: "\uD83C\uDF81", title: activeTab === "donated" ? "Aucune pièce marquée comme donnée" : "Ta boîte de dons est vide", text: activeTab === "donated"
                            ? "Marque tes pièces comme 'Données' une fois déposées à l'association de ton choix !"
                            : "Lorsque tu retires une pièce de ton dressing, sélectionne 'Mettre en donation' pour la retrouver ici et lui trouver une destination solidaire.", action: activeTab !== "donated" ? "Explorer mon dressing" : undefined, onAction: activeTab !== "donated" ? () => onNavigate("wardrobe") : undefined })) : (_jsx("div", { className: "donations-grid", children: filteredDonations.map((d) => {
                            const isDonated = d.status === "donated";
                            return (_jsxs("article", { className: `donation-card ${isDonated ? "is-donated" : ""}`, children: [_jsxs("div", { className: "donation-card-photo-wrap", children: [_jsx("img", { src: d.item.image_url, alt: categoryLabel(d.item.category) }), _jsx("span", { className: "piece-category-tag", children: categoryLabel(d.item.category) }), isDonated && _jsx("span", { className: "donation-badge-overlay", children: "\u2713 Donn\u00E9 !" })] }), _jsxs("div", { className: "donation-card-content", children: [_jsxs("div", { className: "donation-card-title-row", children: [_jsx("h4", { children: categoryLabel(d.item.category) }), _jsxs("small", { className: "donation-date-tag", children: ["Ajout\u00E9 le ", new Date(d.addedAt).toLocaleDateString("fr-TN", { day: "numeric", month: "short" })] })] }), _jsxs("div", { className: "donation-condition-row", children: [_jsx("label", { children: "\u00C9tat du v\u00EAtement :" }), _jsxs("select", { value: d.condition, disabled: isDonated, onChange: (e) => onUpdateCondition(d.id, e.target.value), children: [_jsx("option", { value: "comme_neuf", children: "\u2728 Tr\u00E8s bon \u00E9tat / Comme neuf" }), _jsx("option", { value: "bon_etat", children: "\uD83D\uDC4C Bon \u00E9tat g\u00E9n\u00E9ral" }), _jsx("option", { value: "a_recycler", children: "\u267B\uFE0F \u00C0 recycler (fibres/upcycling)" })] })] }), d.targetOrg && (_jsxs("p", { className: "donation-target-tag", children: ["\uD83D\uDCCD Destination : ", _jsx("b", { children: d.targetOrg })] })), _jsxs("div", { className: "donation-actions-row", children: [_jsx("button", { type: "button", className: `button ${isDonated ? "button-ghost" : "button-primary"} mark-donated-btn`, onClick: () => onMarkDonated(d.id), children: isDonated ? "↩ Remettre en attente" : "✓ Marquer comme donné" }), _jsx("button", { type: "button", className: "button button-outline restore-btn", onClick: () => void onRestoreToWardrobe(d), title: "Replacer ce v\u00EAtement dans mon dressing principal", children: "Remettre au dressing" }), _jsx("button", { type: "button", className: "remove-link delete-don-btn", onClick: () => onRemoveDonation(d.id), title: "Retirer de la liste", children: "\u2715" })] })] })] }, d.id));
                        }) }))] }), _jsxs("section", { className: "content-card", style: { marginBottom: "26px" }, children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "POINTS DE COLLECTE & SOLIDARIT\u00C9 EN TUNISIE" }), _jsxs("h3", { children: ["O\u00F9 donner tes v\u00EAtements\u00A0? (", filteredOrgs.length, " organismes)"] })] }), _jsx("span", { className: "form-sparkle", children: "\uD83D\uDCCD" })] }), _jsx("p", { style: { fontSize: "12.5px", color: "var(--muted)", margin: "0 0 16px" }, children: "Voici notre s\u00E9lection d'organismes v\u00E9rifi\u00E9s et de banques vestimentaires en Tunisie. Choisis l'association la plus proche de chez toi pour y d\u00E9poser tes v\u00EAtements propres." }), _jsxs("div", { className: "orgs-toolbar", children: [_jsx("div", { className: "interactive-chips-row", children: CITIES_LIST.map((cityName) => (_jsxs("button", { type: "button", className: `generator-chip ${selectedCity === cityName ? "active" : ""}`, onClick: () => setSelectedCity(cityName), children: [_jsx("span", { children: cityName === "Toutes" ? "🌍" : "📍" }), _jsx("span", { children: cityName })] }, cityName))) }), _jsxs("div", { className: "search-field", style: { maxWidth: "340px", marginTop: "10px" }, children: [_jsx("span", { className: "search-icon", children: "\uD83D\uDD0D" }), _jsx("input", { placeholder: "Rechercher une association, quartier, mot-cl\u00E9\u2026", value: searchQuery, onChange: (e) => setSearchQuery(e.target.value) }), searchQuery && (_jsx("button", { type: "button", className: "search-clear-btn", onClick: () => setSearchQuery(""), children: "\u2715" }))] })] }), _jsx("div", { className: "orgs-grid", children: filteredOrgs.map((org) => (_jsxs("article", { className: "org-card", children: [_jsx("div", { className: "org-card-top", children: _jsxs("div", { children: [_jsx("span", { className: "org-badge", children: org.badge }), _jsx("h4", { children: org.name }), _jsx("small", { className: "org-subtitle", children: org.subtitle })] }) }), _jsx("p", { className: "org-description", children: org.description }), _jsxs("div", { className: "org-accepted-section", children: [_jsx("span", { className: "org-accepted-label", children: "Articles accept\u00E9s :" }), _jsx("div", { className: "org-accepted-chips", children: org.accepted.map((itemType) => (_jsx("span", { className: "org-accepted-pill", children: itemType }, itemType))) })] }), _jsxs("div", { className: "org-contact-box", children: [_jsxs("div", { className: "contact-line", children: [_jsx("span", { children: "\uD83D\uDCCD" }), _jsx("strong", { children: org.address })] }), _jsxs("div", { className: "contact-line", children: [_jsx("span", { children: "\uD83D\uDCDE" }), _jsx("a", { href: `tel:${org.phone}`, children: org.phone }), _jsx("span", { style: { margin: "0 6px", opacity: 0.5 }, children: "\u00B7" }), _jsx("span", { children: "\u2709\uFE0F" }), _jsx("a", { href: `mailto:${org.email}`, children: org.email })] }), _jsxs("div", { className: "contact-line hours-line", children: [_jsx("span", { children: "\u23F0" }), _jsx("small", { children: org.hours })] })] }), _jsx("div", { className: "org-action-row", children: _jsx("button", { type: "button", className: "button button-primary org-choose-btn", onClick: () => {
                                            const pendingFirst = donations.find((d) => d.status === "pending");
                                            if (pendingFirst) {
                                                onMarkDonated(pendingFirst.id, org.name);
                                            }
                                            else {
                                                alert(`Pour faire un don à ${org.name}, contacte-les au ${org.phone} ou rends-toi à : ${org.address}.`);
                                            }
                                        }, children: pendingCount > 0 ? `🎁 Attribuer un don à ${org.name}` : "📞 Contacter cette association" }) })] }, org.id))) })] }), _jsxs("section", { className: "donation-tips-box", children: [_jsxs("div", { className: "card-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "CONSEILS DU STYLISTE DRESSME" }), _jsx("h3", { children: "Comment bien pr\u00E9parer ses dons en 3 gestes simples\u00A0?" })] }), _jsx("span", { className: "form-sparkle", children: "\u2728" })] }), _jsxs("div", { className: "donation-tips-grid", children: [_jsxs("div", { className: "donation-tip-item", children: [_jsx("span", { className: "tip-number", children: "1" }), _jsx("h4", { children: "Laver et plier soigneusement" }), _jsx("p", { children: "M\u00EAme s'ils sont d'occasion, des v\u00EAtements lav\u00E9s et propres permettent aux b\u00E9n\u00E9voles de les distribuer directement sans frais de pressing." })] }), _jsxs("div", { className: "donation-tip-item", children: [_jsx("span", { className: "tip-number", children: "2" }), _jsx("h4", { children: "V\u00E9rifier fermetures & boutons" }), _jsx("p", { children: "Assure-toi que les zips glissent bien et que les boutons sont attach\u00E9s. Un v\u00EAtement pr\u00EAt \u00E0 \u00EAtre port\u00E9 imm\u00E9diatement est un vrai cadeau de dignit\u00E9." })] }), _jsxs("div", { className: "donation-tip-item", children: [_jsx("span", { className: "tip-number", children: "3" }), _jsx("h4", { children: "S\u00E9parer par sacs et saisons" }), _jsx("p", { children: "Emballe tes v\u00EAtements dans des sacs \u00E9tanches et \u00E9tiquette-les si possible (*\u00AB Hiver Homme \u00BB*, *\u00AB \u00C9t\u00E9 Enfant \u00BB*). Cela facilite grandement le tri des maraudes." })] })] })] })] }));
}
function RLHFDashboard({ stats, days, loading, onSetDays, onExport, }) {
    const [exportBusy, setExportBusy] = useState("");
    async function handleExport(format) {
        setExportBusy(format);
        try {
            await onExport(days, format);
        }
        finally {
            setExportBusy("");
        }
    }
    return (_jsxs(_Fragment, { children: [_jsx(PageHeading, { title: "Tableau de bord RLHF", subtitle: "Suis les retours et l'\u00E9volution des recommandations." }), _jsxs("div", { className: "content-card", style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }, children: [_jsx("span", { style: { fontWeight: 600 }, children: "P\u00E9riode :" }), [7, 30, 90].map((d) => (_jsxs("button", { type: "button", className: `button${days === d ? " button-primary" : " button-outline"}`, onClick: () => onSetDays(d), children: [d, "j"] }, d))), _jsxs("div", { style: { marginLeft: "auto", display: "flex", gap: "8px" }, children: [_jsx("button", { type: "button", className: "button button-outline", disabled: exportBusy === "csv", onClick: () => void handleExport("csv"), children: exportBusy === "csv" ? "Export…" : "⬇ CSV" }), _jsx("button", { type: "button", className: "button button-outline", disabled: exportBusy === "json", onClick: () => void handleExport("json"), children: exportBusy === "json" ? "Export…" : "⬇ JSON" })] })] }), loading && _jsx("p", { className: "inline-hint", style: { padding: "16px" }, children: "Chargement des statistiques\u2026" }), !loading && !stats && (_jsx("div", { className: "content-card", children: _jsxs("p", { children: ["Aucune donn\u00E9e disponible. Commence par noter des tenues dans ", _jsx("em", { children: "Id\u00E9es de looks" }), "."] }) })), stats && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "stats-cards", children: [_jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-icon gold", children: "\u25C9" }), _jsx("span", { className: "summary-label", children: "Retours total" }), _jsx("strong", { children: stats.total_feedbacks }), _jsxs("small", { children: ["sur ", days, " derniers jours"] })] }), _jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-icon pink", children: "\u2605" }), _jsx("span", { className: "summary-label", children: "Note moyenne" }), _jsxs("strong", { children: [stats.average_rating.toFixed(1), " / 5"] }), _jsx("small", { children: "sur tous les retours" })] }), _jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-icon blue", children: "\u2726" }), _jsx("span", { className: "summary-label", children: "Entra\u00EEnement IA" }), _jsx("strong", { children: stats.readiness_for_training.has_sufficient_data
                                            ? "✓ Prêt"
                                            : `${stats.readiness_for_training.pair_count} / ${stats.readiness_for_training.next_threshold}` }), _jsx("small", { children: stats.readiness_for_training.last_trained_at
                                            ? `Dernier : ${new Date(stats.readiness_for_training.last_trained_at).toLocaleDateString("fr-FR")}`
                                            : "Jamais entraîné" })] })] }), _jsxs("section", { className: "content-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "DISTRIBUTION" }), _jsx("h3", { children: "R\u00E9partition des notes" })] }) }), _jsxs("table", { style: { width: "100%", borderCollapse: "collapse" }, children: [_jsx("thead", { children: _jsxs("tr", { style: { textAlign: "left", borderBottom: "1px solid var(--border)" }, children: [_jsx("th", { style: { padding: "8px" }, children: "Note" }), _jsx("th", { style: { padding: "8px" }, children: "Nombre" }), _jsx("th", { style: { padding: "8px" }, children: "Proportion" })] }) }), _jsx("tbody", { children: [5, 4, 3, 2, 1].map((star) => {
                                            const count = stats.rating_distribution[star] ?? 0;
                                            const pct = stats.total_feedbacks > 0 ? Math.round((count / stats.total_feedbacks) * 100) : 0;
                                            return (_jsxs("tr", { style: { borderBottom: "1px solid var(--border)" }, children: [_jsx("td", { style: { padding: "8px" }, children: "★".repeat(star) }), _jsx("td", { style: { padding: "8px" }, children: count }), _jsx("td", { style: { padding: "8px" }, children: _jsxs("div", { style: { display: "flex", alignItems: "center", gap: "8px" }, children: [_jsx("div", { style: { flex: 1, background: "var(--surface-2, #eee)", borderRadius: "4px", height: "8px" }, children: _jsx("div", { style: { width: `${pct}%`, background: "var(--accent, #e88)", borderRadius: "4px", height: "8px" } }) }), _jsxs("span", { style: { minWidth: "36px", fontSize: "0.85em" }, children: [pct, "%"] })] }) })] }, star));
                                        }) })] })] }), stats.avg_rating_trend.length > 0 && (_jsxs("section", { className: "content-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "\u00C9VOLUTION" }), _jsx("h3", { children: "Tendance des notes dans le temps" })] }) }), _jsx("ul", { style: { listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "6px" }, children: stats.avg_rating_trend.map((point) => (_jsxs("li", { style: { display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }, children: [_jsx("span", { children: new Date(`${point.date}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) }), _jsxs("span", { children: [_jsx("strong", { children: point.avg_rating.toFixed(1) }), _jsxs("span", { style: { color: "var(--text-muted)", marginLeft: "8px" }, children: ["(", point.count, " retour", point.count > 1 ? "s" : "", ")"] })] })] }, point.date))) })] })), (stats.most_liked_items.length > 0 || stats.most_disliked_items.length > 0) && (_jsxs("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }, children: [stats.most_liked_items.length > 0 && (_jsxs("section", { className: "content-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "POPULAIRES" }), _jsx("h3", { children: "Pi\u00E8ces les plus appr\u00E9ci\u00E9es" })] }) }), _jsx("ul", { style: { listStyle: "none", padding: 0, margin: 0 }, children: stats.most_liked_items.map((item) => (_jsxs("li", { style: { padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }, children: [_jsxs("span", { style: { fontFamily: "monospace", fontSize: "0.8em" }, children: [item.item_id.slice(0, 8), "\u2026"] }), _jsxs("span", { children: ["\uD83D\uDC4D ", item.count, "\u00D7 \u00B7 ", item.avg_rating.toFixed(1), "\u2605"] })] }, item.item_id))) })] })), stats.most_disliked_items.length > 0 && (_jsxs("section", { className: "content-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "\u00C0 REVOIR" }), _jsx("h3", { children: "Pi\u00E8ces les moins appr\u00E9ci\u00E9es" })] }) }), _jsx("ul", { style: { listStyle: "none", padding: 0, margin: 0 }, children: stats.most_disliked_items.map((item) => (_jsxs("li", { style: { padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }, children: [_jsxs("span", { style: { fontFamily: "monospace", fontSize: "0.8em" }, children: [item.item_id.slice(0, 8), "\u2026"] }), _jsxs("span", { children: ["\uD83D\uDC4E ", item.count, "\u00D7 \u00B7 ", item.avg_rating.toFixed(1), "\u2605"] })] }, item.item_id))) })] }))] })), stats.recent_feedbacks.length > 0 && (_jsxs("section", { className: "content-card", children: [_jsx("div", { className: "card-heading", children: _jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "ACTIVIT\u00C9 R\u00C9CENTE" }), _jsx("h3", { children: "Derniers retours" })] }) }), _jsxs("table", { style: { width: "100%", borderCollapse: "collapse" }, children: [_jsx("thead", { children: _jsxs("tr", { style: { textAlign: "left", borderBottom: "1px solid var(--border)" }, children: [_jsx("th", { style: { padding: "8px" }, children: "Date" }), _jsx("th", { style: { padding: "8px" }, children: "Tenue" }), _jsx("th", { style: { padding: "8px" }, children: "Note" }), _jsx("th", { style: { padding: "8px" }, children: "Commentaire" })] }) }), _jsx("tbody", { children: stats.recent_feedbacks.map((fb) => (_jsxs("tr", { style: { borderBottom: "1px solid var(--border)" }, children: [_jsx("td", { style: { padding: "8px", whiteSpace: "nowrap" }, children: new Date(fb.created_at).toLocaleDateString("fr-FR") }), _jsxs("td", { style: { padding: "8px", fontFamily: "monospace", fontSize: "0.8em" }, children: [fb.outfit_id.slice(0, 8), "\u2026"] }), _jsx("td", { style: { padding: "8px" }, children: "★".repeat(fb.rating) }), _jsx("td", { style: { padding: "8px", color: "var(--text-muted)" }, children: fb.comment ?? "—" })] }, fb.id))) })] })] }))] }))] }));
}
