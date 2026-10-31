import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ClothingItem,
  OutfitFeedback,
  ItemUsage,
  CurrentUser,
  getApiError,
  Outfit,
  PackingList,
  PurchaseResult,
  PurchaseHistoryItem,
  WishlistEntry,
  CatalogAlternative,
  formatTnd,
  getPurchaseHistory,
  deleteHistoryEntry,
  clearPurchaseHistory,
  getWishlist,
  addToWishlist,
  removeFromWishlist,
  ScheduledOutfit,
  StyleProfile,
  uploadPhoto,
  analyzePhoto,
  WardrobeAnalysisResponse,
  parseLowCategoryConfidence,
  LowCategoryConfidence,
  submitOutfitFeedback,
} from "./api";
import "./styles.css";
import LlmAssistant from "./LlmAssistant";

type Screen =
  | "overview"
  | "wardrobe"
  | "outfits"
  | "calendar"
  | "profile"
  | "assistant"
  | "packing"
  | "purchase"
  | "tryon"
  | "donation";

const NAV_ITEMS: { id: Screen; label: string; icon: string; group: string }[] = [
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
];

const SCREEN_COPY: Record<Screen, { title: string; subtitle: string }> = {
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
};

const OCCASIONS = [
  ["quotidien", "Quotidien"],
  ["travail", "Travail"],
  ["sortie", "Sortie"],
  ["soirée", "Soirée"],
  ["événement", "Événement"],
];
const CITIES = ["Tunis", "Sousse", "Sfax", "Djerba"];
const WARDROBE_CATEGORIES: [string, string][] = [["haut", "Haut"], ["bas", "Bas"], ["robe", "Robe"], ["veste", "Veste"], ["chaussures", "Chaussures"], ["sac", "Sac"], ["accessoire", "Accessoire"]];

interface CategoryPromptState extends LowCategoryConfidence {
  imageUrl: string;
  season: string;
}

const SEASONS = ["printemps", "été", "automne", "hiver"];
// Wardrobe-item seasons: same vocabulary the backend validates (ClothingItem season).
const ITEM_SEASONS: [string, string][] = [["ete", "☀️ Été"], ["hiver", "❄️ Hiver"], ["mi_saison", "🍂 Mi-saison"], ["toutes_saisons", "🌍 Toutes saisons"]];
const itemSeasonLabel = (value: string | null | undefined) => ITEM_SEASONS.find(([key]) => key === value)?.[1] ?? null;
const WARDROBE_FAVORITES_KEY = "dressme_wardrobe_favorites";
const OUTFIT_FAVORITES_KEY = "dressme_favorite_outfits";
const DONATIONS_STORAGE_KEY = "dressme_donations_list";

export interface DonationItem {
  id: string;
  item: ClothingItem;
  addedAt: string;
  status: "pending" | "donated";
  condition: "comme_neuf" | "bon_etat" | "a_recycler";
  targetOrg?: string;
}

function todayLocal(): string {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
}

function dayString(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function readIds(key: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(value) && value.every((id) => typeof id === "string") ? value : [];
  } catch {
    return [];
  }
}

function categoryLabel(value: string | null | undefined): string {
  if (!value) return "Autre";
  return value.charAt(0).toLocaleUpperCase("fr") + value.slice(1).replace(/_/g, " ");
}

function Avatar({ user, size = "normal" }: { user: CurrentUser | null; size?: "normal" | "large" }) {
  const initials = (user?.full_name ?? user?.email ?? "DM").trim().slice(0, 1).toLocaleUpperCase("fr");
  return user?.avatar_photo_url
    ? <img className={`avatar avatar-${size}`} src={user.avatar_photo_url} alt="Photo de profil" />
    : <span className={`avatar avatar-placeholder avatar-${size}`} aria-label="Profil">{initials || "D"}</span>;
}

function AuthScreen({ onAuthenticated, initialError }: { onAuthenticated: (token: string) => void; initialError: string }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);

  async function submit(event: FormEvent<HTMLFormElement>) {
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
      const { data } = await api.post<{ access_token: string }>("/auth/login", {
        email: email.trim(),
        password,
      });
      onAuthenticated(data.access_token);
    } catch (cause: unknown) {
      setError(getApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-story">
        <a className="auth-brand" href="#connexion" aria-label="DressMe">
          <img src="/dressme-logo.png" alt="DressMe — A smarter wardrobe for a brighter you" />
        </a>
        <img className="auth-story-photo" src="/sidi-bou-style-inspiration.jpg" alt="" />
        <div className="auth-story-copy">
          <span className="eyebrow">✦ TON STYLE, ENFIN À TOI</span>
          <h1>Le plaisir de s’habiller, <em>chaque jour.</em></h1>
          <p>Organise ton dressing, compose des looks qui te ressemblent et prépare tes prochaines aventures.</p>
          <div className="auth-points">
            <span><i>✓</i> Ton dressing à portée de main</span>
            <span><i>✓</i> Des idées selon tes envies</span>
            <span><i>✓</i> Une touche de Tunisie dans ton style</span>
          </div>
        </div>
        <p className="auth-footer">DressMe · Avec amour, depuis la Tunisie</p>
      </section>

      <section className="auth-panel" id="connexion">
        <form className="auth-card" onSubmit={submit}>
          <span className="auth-card-mark">✧</span>
          <p className="eyebrow">{mode === "login" ? "RAVIE DE TE REVOIR" : "BIENVENUE DANS TON ESPACE"}</p>
          <h2>{mode === "login" ? "Connecte-toi" : "Crée ton compte"}</h2>
          <p className="auth-subtitle">
            {mode === "login" ? "Retrouve ton dressing et tes inspirations." : "Quelques secondes pour commencer ton dressing."}
          </p>
          {mode === "register" && (
            <label className="field">
              <span>Ton nom</span>
              <input autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Ex. Amira Ben Ali" />
            </label>
          )}
          <label className="field">
            <span>Adresse e-mail</span>
            <input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="toi@exemple.com" />
          </label>
          <label className="field">
            <span>Mot de passe</span>
            <input required type="password" minLength={6} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Au moins 6 caractères" />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary auth-submit" type="submit" disabled={busy}>
            {busy ? "Un instant…" : mode === "login" ? "Entrer dans mon dressing" : "Créer mon compte"}
            {!busy && <span aria-hidden="true">→</span>}
          </button>
          <p className="auth-switch">
            {mode === "login" ? "Pas encore de compte ?" : "Tu as déjà un compte ?"}
            <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
              {mode === "login" ? "Créer mon compte" : "Me connecter"}
            </button>
          </p>
          <p className="auth-privacy">Tes données restent privées et liées à ton compte.</p>
        </form>
      </section>
    </main>
  );
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem("dressme_access_token") ?? "");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("dressme_theme") as "light" | "dark") || "light";
  });
  const [screen, setScreen] = useState<Screen>("overview");
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [usage, setUsage] = useState<Record<string, ItemUsage>>({});
  const [categoryPrompt, setCategoryPrompt] = useState<CategoryPromptState | null>(null);
  const [ingestionReview, setIngestionReview] = useState<{
    imageUrl: string;
    analysis: WardrobeAnalysisResponse;
    selectedCategory: string;
    selectedSeason: string;
  } | null>(null);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [scheduled, setScheduled] = useState<ScheduledOutfit[]>([]);
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [packingLists, setPackingLists] = useState<PackingList[]>([]);
  const [wardrobeFavorites, setWardrobeFavorites] = useState<string[]>(() => readIds(WARDROBE_FAVORITES_KEY));
  const [outfitFavorites, setOutfitFavorites] = useState<string[]>(() => readIds(OUTFIT_FAVORITES_KEY));
  const [donations, setDonations] = useState<DonationItem[]>(() => {
    try {
      const raw = localStorage.getItem(DONATIONS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [donationModalItem, setDonationModalItem] = useState<ClothingItem | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [monthAnchor, setMonthAnchor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dressme_theme", theme);
  }, [theme]);

  const today = todayLocal();
  const selectedNav = NAV_ITEMS.find((item) => item.id === screen);
  const displayName = user?.full_name?.split(/\s+/)[0] || "toi";
  const itemsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);

  useEffect(() => {
    if (!token || screen !== "wardrobe") return;
    let active = true;
    api.get<ItemUsage[]>("/wardrobe/usage")
      .then(({ data }) => { if (active) setUsage(Object.fromEntries(data.map((entry) => [entry.item_id, entry]))); })
      .catch(() => { /* usage is a nicety; the wardrobe still works without it */ });
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
      api.get<CurrentUser>("/auth/me"),
      api.get<ClothingItem[]>("/wardrobe/"),
    ])
      .then(([me, wardrobe]) => {
        if (!active) return;
        setUser(me.data);
        setItems(wardrobe.data);
        const ids = new Set(wardrobe.data.map((item) => item.id));
        const validFavorites = readIds(WARDROBE_FAVORITES_KEY).filter((id) => ids.has(id));
        setWardrobeFavorites(validFavorites);
        localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(validFavorites));
      })
      .catch((cause: unknown) => {
        if (!active) return;
        localStorage.removeItem("dressme_access_token");
        setToken("");
        setUser(null);
        setError(getApiError(cause));
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (!token || screen === "overview") return;
    let active = true;
    setError("");
    setLoading(true);
    const finish = () => { if (active) setLoading(false); };

    if (screen === "wardrobe") {
      api.get<ClothingItem[]>("/wardrobe/")
        .then(({ data }) => { if (active) setItems(data); })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else if (screen === "outfits") {
      api.get<Outfit[]>("/recommendations/outfits")
        .then(({ data }) => { if (active) setOutfits(data); })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else if (screen === "calendar") {
      const start = dayString(monthAnchor);
      const end = dayString(new Date(monthAnchor.getFullYear(), monthAnchor.getMonth() + 1, 0));
      api.get<ScheduledOutfit[]>("/calendar/", { params: { start, end } })
        .then(({ data }) => { if (active) setScheduled(data); })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else if (screen === "profile") {
      Promise.all([api.get<StyleProfile>("/style-profile/"), api.get<CurrentUser>("/auth/me")])
        .then(([style, me]) => {
          if (!active) return;
          setProfile(style.data);
          setUser(me.data);
        })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else if (screen === "packing") {
      api.get<PackingList[]>("/packing/")
        .then(({ data }) => { if (active) setPackingLists(data); })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else if (screen === "tryon") {
      Promise.all([api.get<CurrentUser>("/auth/me"), api.get<ClothingItem[]>("/wardrobe/")])
        .then(([me, wardrobe]) => {
          if (!active) return;
          setUser(me.data);
          setItems(wardrobe.data);
        })
        .catch((cause: unknown) => { if (active) setError(getApiError(cause)); })
        .finally(finish);
    } else {
      finish();
    }
    return () => { active = false; };
  }, [monthAnchor, screen, token]);

  useEffect(() => {
    if (!token || screen !== "overview") return;
    let active = true;
    const start = dayString(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
    const end = dayString(new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0));
    Promise.allSettled([
      api.get<StyleProfile>("/style-profile/"),
      api.get<Outfit[]>("/recommendations/outfits"),
      api.get<ScheduledOutfit[]>("/calendar/", { params: { start, end } }),
      api.get<PackingList[]>("/packing/"),
    ]).then(([style, looks, calendar, packing]) => {
      if (!active) return;
      if (style.status === "fulfilled") setProfile(style.value.data);
      if (looks.status === "fulfilled") setOutfits(looks.value.data);
      if (calendar.status === "fulfilled") setScheduled(calendar.value.data);
      if (packing.status === "fulfilled") setPackingLists(packing.value.data);
    });
    return () => { active = false; };
  }, [screen, token]);

  function authenticate(accessToken: string) {
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

  function navigate(target: Screen) {
    setScreen(target);
    setMenuOpen(false);
    setError("");
    setNotice("");
  }

  function reportError(cause: unknown) {
    setError(getApiError(cause));
    setNotice("");
  }

  async function submitItem(imageUrl: string, season: string, category?: string) {
    const { data } = await api.post<ClothingItem>("/wardrobe/", { image_url: imageUrl, season: season || undefined, category });
    setItems((current) => [data, ...current]);
    setNotice("La pièce a été analysée et ajoutée à ton dressing.");
  }

  const [uploadStage, setUploadStage] = useState("");
  const firstPhotoNoticeShown = useRef(sessionStorage.getItem("dressme_first_photo_notice") === "shown");

  async function addItem(file: File, season: string) {
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
      } catch (analyzeErr) {
        // Fallback to direct submit if analyze endpoint wasn't available
        try {
          await submitItem(imageUrl, season);
        } catch (cause: unknown) {
          const unsure = parseLowCategoryConfidence(cause);
          if (!unsure) throw cause;
          setCategoryPrompt({ ...unsure, imageUrl, season });
        }
      }
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function confirmIngestion(category: string, season: string, finalImageUrl?: string) {
    if (!ingestionReview) return;
    setBusy("wardrobe-upload");
    try {
      await submitItem(finalImageUrl || ingestionReview.imageUrl, season, category);
      setIngestionReview(null);
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function confirmCategory(category: string) {
    if (!categoryPrompt) return;
    setBusy("wardrobe-upload");
    try {
      await submitItem(categoryPrompt.imageUrl, categoryPrompt.season, category);
      setCategoryPrompt(null);
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function markWorn(item: ClothingItem) {
    try {
      const { data } = await api.post<ItemUsage>(`/wardrobe/${item.id}/worn`);
      setUsage((current) => ({ ...current, [data.item_id]: data }));
      setNotice("C'est noté : pièce portée aujourd'hui.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function changeSeason(item: ClothingItem, season: string) {
    try {
      const { data } = await api.patch<ClothingItem>(`/wardrobe/${item.id}`, { season });
      setItems((current) => current.map((currentItem) => (currentItem.id === data.id ? data : currentItem)));
      setNotice("La saison de la pièce a été enregistrée.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  function saveDonations(next: DonationItem[]) {
    setDonations(next);
    localStorage.setItem(DONATIONS_STORAGE_KEY, JSON.stringify(next));
  }

  async function requestDeleteItem(item: ClothingItem) {
    setDonationModalItem(item);
  }

  async function handleTransferToDonation(item: ClothingItem) {
    setDonationModalItem(null);
    try {
      const newDonation: DonationItem = {
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
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function handlePermanentDelete(item: ClothingItem) {
    setDonationModalItem(null);
    try {
      await api.delete(`/wardrobe/${item.id}`);
      setItems((current) => current.filter((currentItem) => currentItem.id !== item.id));
      const nextFavs = wardrobeFavorites.filter((id) => id !== item.id);
      setWardrobeFavorites(nextFavs);
      localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(nextFavs));
      setNotice("La pièce a été définitivement supprimée.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function restoreDonationToWardrobe(donation: DonationItem) {
    try {
      const { data } = await api.post<ClothingItem>("/wardrobe/", { image_url: donation.item.image_url });
      setItems((current) => [data, ...current]);
      const next = donations.filter((d) => d.id !== donation.id);
      saveDonations(next);
      setNotice("✨ La pièce est de retour dans ton dressing !");
    } catch {
      setItems((current) => [donation.item, ...current]);
      const next = donations.filter((d) => d.id !== donation.id);
      saveDonations(next);
      setNotice("✨ La pièce a été replacée dans ton dressing.");
    }
  }

  function markDonated(donationId: string, orgName?: string) {
    const next = donations.map((d) =>
      d.id === donationId
        ? { ...d, status: (d.status === "donated" ? "pending" : "donated") as "pending" | "donated", targetOrg: orgName ?? d.targetOrg }
        : d
    );
    saveDonations(next);
    setNotice("🎉 Félicitations pour ce geste solidaire et éco-responsable !");
  }

  function updateDonationCondition(donationId: string, condition: "comme_neuf" | "bon_etat" | "a_recycler") {
    const next = donations.map((d) => (d.id === donationId ? { ...d, condition } : d));
    saveDonations(next);
  }

  function removeDonation(donationId: string) {
    const next = donations.filter((d) => d.id !== donationId);
    saveDonations(next);
    setNotice("La pièce a été retirée de la boîte de dons.");
  }

  function toggleFavorite(id: string, kind: "wardrobe" | "outfit") {
    const current = kind === "wardrobe" ? wardrobeFavorites : outfitFavorites;
    const next = current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id];
    if (kind === "wardrobe") {
      setWardrobeFavorites(next);
      localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(next));
    } else {
      setOutfitFavorites(next);
      localStorage.setItem(OUTFIT_FAVORITES_KEY, JSON.stringify(next));
    }
  }

  async function generateLooks(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("looks");
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      const { data } = await api.post<{
        outfits: Outfit[];
        context: Record<string, string | null>;
        evaluation?: Record<string, number>;
      }>("/recommendations/outfits", {
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
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function saveOutfitFeedback(outfitId: string, rating: OutfitFeedback | null) {
    setBusy(`outfit-feedback:${outfitId}`);
    setError("");
    try {
      const updated = await submitOutfitFeedback(outfitId, rating);
      setOutfits((current) => current.map((outfit) => outfit.id === updated.id ? updated : outfit));
      setNotice(rating === "worn"
        ? "Merci, cette tenue est notée comme portée et ton historique est actualisé."
        : rating === null ? "Ton avis sur cette tenue a été retiré." : "Merci, ton avis aidera à personnaliser les prochaines idées.");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function scheduleOutfit(outfit: Outfit, date: string) {
    if (!date) {
      setError("Choisis une date pour planifier cette tenue.");
      return;
    }
    try {
      const { data } = await api.put<ScheduledOutfit>(`/calendar/${date}`, { item_ids: outfit.item_ids });
      setScheduled((current) => [...current.filter((entry) => entry.date !== date), data].sort((a, b) => a.date.localeCompare(b.date)));
      setNotice(`Tenue planifiée pour le ${new Date(`${date}T12:00:00`).toLocaleDateString("fr-TN", { day: "numeric", month: "long" })}.`);
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function saveCalendarOutfit(date: string, selectedIds: string[]) {
    try {
      const { data } = await api.put<ScheduledOutfit>(`/calendar/${date}`, { item_ids: selectedIds });
      setScheduled((current) => [...current.filter((entry) => entry.date !== date), data]);
      setNotice("Ta tenue est enregistrée dans le calendrier.");
      return data;
    } catch (cause: unknown) {
      reportError(cause);
      throw cause;
    }
  }

  async function renderCalendarOutfit(date: string) {
    setError("");
    try {
      // Slow on purpose: one paid try-on call per garment, so it only runs when asked.
      const { data } = await api.post<ScheduledOutfit>(`/calendar/${date}/render`);
      setScheduled((current) => current.map((entry) => (entry.date === data.date ? data : entry)));
      setNotice("Ton avatar porte la tenue du jour.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function removeCalendarOutfit(date: string) {
    try {
      await api.delete(`/calendar/${date}`);
      setScheduled((current) => current.filter((entry) => entry.date !== date));
      setNotice("La tenue a été retirée du calendrier.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function createPacking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("packing-create");
    setError("");
    try {
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const { data } = await api.post<PackingList>("/packing/", {
        destination: String(form.get("destination")).trim(),
        duration_days: Number(form.get("duration")),
        trip_type: String(form.get("tripType")),
        start_date: String(form.get("startDate") || "") || undefined,
      });
      setPackingLists((current) => [data, ...current]);
      formElement.reset();
      setNotice("Ta liste de valise est prête.");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function togglePackedItem(list: PackingList, itemId: string) {
    try {
      const { data } = await api.patch<PackingList>(`/packing/${list.id}/check`, {
        item_id: itemId,
        checked: !list.checked_item_ids.includes(itemId),
      });
      setPackingLists((current) => current.map((entry) => entry.id === list.id ? data : entry));
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function deletePackingList(id: string) {
    if (!window.confirm("Supprimer cette liste de voyage ?")) return;
    try {
      await api.delete(`/packing/${id}`);
      setPackingLists((current) => current.filter((entry) => entry.id !== id));
      setNotice("La liste de voyage a été supprimée.");
    } catch (cause: unknown) {
      reportError(cause);
    }
  }

  async function uploadAvatar(file: File) {
    setBusy("avatar");
    setError("");
    try {
      const imageUrl = await uploadPhoto(file);
      await api.put("/tryon/avatar", { image_url: imageUrl });
      setUser((current) => current ? { ...current, avatar_photo_url: imageUrl } : current);
      setNotice("Ta photo de référence est enregistrée.");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function runPurchaseCheck(file: File) {
    setBusy("purchase");
    setError("");
    try {
      const imageUrl = await uploadPhoto(file);
      const { data } = await api.post<PurchaseResult>("/purchase/check", { image_url: imageUrl });
      setPurchaseResult(data);
      setNotice("");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  const [purchaseResult, setPurchaseResult] = useState<PurchaseResult | null>(null);
  const [tryOnResult, setTryOnResult] = useState("");
  const [selectedTryOnItems, setSelectedTryOnItems] = useState<string[]>([]);

  // Real-time weather for topbar only
  const [topbarWeather, setTopbarWeather] = useState({ temp: 22, icon: "🌤️" });
  useEffect(() => {
    api.get("/weather/Tunis").then(({ data }) => setTopbarWeather({ temp: data.temp, icon: data.icon })).catch(() => {});
  }, []);

  function toggleTryOnItem(id: string) {
    setSelectedTryOnItems((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  function clearTryOnSelection() {
    setSelectedTryOnItems([]);
  }

  async function selectPresetAvatar(imageUrl: string) {
    setBusy("avatar");
    setError("");
    try {
      await api.put("/tryon/avatar", { image_url: imageUrl });
      setUser((current) => current ? { ...current, avatar_photo_url: imageUrl } : current);
      setNotice("Mannequin sélectionné avec succès ! ✨");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function generateTryOn() {
    if (selectedTryOnItems.length === 0) return;
    setBusy("tryon");
    setError("");
    setTryOnResult("");
    try {
      const payload =
        selectedTryOnItems.length === 1
          ? { garment_item_id: selectedTryOnItems[0] }
          : { garment_item_ids: selectedTryOnItems };
      const { data } = await api.post<{ result_image_url: string }>("/tryon/", payload);
      setTryOnResult(data.result_image_url);
      setNotice("Rendu d’essayage virtuel réussi ! ✨");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  if (!token) return <AuthScreen onAuthenticated={authenticate} initialError={error} />;
  if (loading && !user) return <main className="app-loading"><span className="loading-mark">D</span><p>Ton espace DressMe s’ouvre…</p></main>;

  return (
    <div className="workspace">
      <aside className={`sidebar${menuOpen ? " sidebar-open" : ""}`}>
        <a className="sidebar-brand" href="#accueil" onClick={(event) => { event.preventDefault(); navigate("overview"); }}>
            <img src="/dressme-logo.png" alt="DressMe — A smarter wardrobe for a brighter you" />
          </a>
        <div className="sidebar-profile">
          <Avatar user={user} />
          <div><strong>{displayName}</strong><span>Mon espace personnel</span></div>
          <span className="online-dot" aria-label="Connectée" />
        </div>
        <nav className="sidebar-nav" aria-label="Navigation de l’application">
          {["TON ESPACE", "DÉCOUVRIR"].map((group) => (
            <div className="nav-group" key={group}>
              <p>{group}</p>
              {NAV_ITEMS.filter((entry) => entry.group === group).map((entry) => (
                <button className={`nav-link${screen === entry.id ? " nav-link-active" : ""}`} key={entry.id} type="button" onClick={() => navigate(entry.id)}>
                  <span className="nav-icon">{entry.icon}</span><span>{entry.label}</span>
                  {entry.id === "wardrobe" && items.length > 0 && <span className="nav-count">{items.length}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note"><span>✦</span><p>Le chic d’ici,<br /><b>le style qui va partout.</b></p></div>
          <button type="button" className="signout-button" onClick={signOut}>↪ <span>Se déconnecter</span></button>
        </div>
      </aside>

      {menuOpen && <button className="sidebar-backdrop" aria-label="Fermer le menu" type="button" onClick={() => setMenuOpen(false)} />}

      <main className="main-panel">
        <header className="topbar">
          <button type="button" className="mobile-menu-toggle" aria-label="Ouvrir le menu" onClick={() => setMenuOpen(true)}>☰</button>
          <div className="breadcrumb">
            <span className="brand-dot">✦</span>
            <span>DressMe</span>
            <b>/</b>
            <strong>{selectedNav?.label ?? "Accueil"}</strong>
          </div>
          <div className="topbar-right">
            <span className="weather-chip" title="Météo actuelle en Tunisie">
              <span className="weather-icon">{topbarWeather.icon}</span> {topbarWeather.city} · {topbarWeather.temp}°C
            </span>
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
              title={theme === "light" ? "Passer en mode sombre" : "Passer en mode clair"}
              aria-label="Basculer le thème"
            >
              {theme === "light" ? "🌙" : "☀️"}
            </button>
            <label className={`topbar-quick-add${busy === "wardrobe-upload" ? " is-disabled" : ""}`} title="Ajouter une nouvelle pièce rapidement">
              <span>＋ Ajouter</span>
              <input
                type="file"
                accept="image/*"
                disabled={busy === "wardrobe-upload"}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void addItem(file, "");
                  event.target.value = "";
                }}
              />
            </label>
            <button className="topbar-avatar-button" type="button" onClick={() => navigate("profile")} aria-label="Ouvrir mon profil"><Avatar user={user} /></button>
          </div>
        </header>

        {screen === "overview" && (
          <section className="workspace-hero" aria-label="DressMe, avec amour depuis la Tunisie">
            <img className="workspace-hero-photo" src="/sidi-bou-style-inspiration.jpg" alt="" />
            <div className="workspace-hero-content">
              <div>
                <span className="hero-pill">TUNIS · SIDI BOU SAÏD ✦</span>
                <h2>Le chic d’ici, le style qui va partout.</h2>
                <p>Ton assistant personnel alimenté par l'IA pour sublimer chaque tenue au quotidien.</p>
              </div>
            </div>
          </section>
        )}

        <div className="page-content">
          {screen === "wardrobe" && busy === "wardrobe-upload" && <div className="content-card" role="status"><p>{uploadStage}</p><button type="button" className="text-button" onClick={() => navigate("assistant")}>Tester l’assistant IA pendant l’attente →</button></div>}
          {error && <div className="alert alert-error" role="alert"><span>!</span><p>{error}</p><button type="button" aria-label="Fermer l’erreur" onClick={() => setError("")}>×</button></div>}
          {notice && <div className="alert alert-success" role="status"><span>✓</span><p>{notice}</p><button type="button" aria-label="Fermer le message" onClick={() => setNotice("")}>×</button></div>}

          {screen === "overview" && (
            <>
              <PageHeading title={`Bonjour ${displayName} ✨`} subtitle="Ton style, tes pièces et tes inspirations au même endroit." />
              <section className="welcome-banner">
                <div className="welcome-copy"><span className="eyebrow">UN DRESSING QUI TE RESSEMBLE</span><h2>Prête à composer <em>ton prochain look&nbsp;?</em></h2><p>Explore tes pièces et laisse-toi inspirer par des associations faites pour toi.</p><button className="button button-primary" type="button" onClick={() => navigate("outfits")}>Trouver une tenue <span>→</span></button></div>
                <img className="welcome-photo" src="/tunisian-wardrobe-inspiration.jpg" alt="Un coin dressing inspiré par Sidi Bou Saïd" />
                <span className="welcome-stamp">صنع بحب ✦</span>
              </section>
              <div className="stats-cards">
                <button type="button" className="summary-card" onClick={() => navigate("wardrobe")}><span className="summary-icon pink">◈</span><span className="summary-label">Dans mon dressing</span><strong>{items.length}</strong><small>pièce{items.length === 1 ? "" : "s"} au total <b>→</b></small></button>
                <button type="button" className="summary-card" onClick={() => navigate("outfits")}><span className="summary-icon gold">✧</span><span className="summary-label">Idées de looks</span><strong>{outfits.length}</strong><small>tenue{outfits.length === 1 ? "" : "s"} disponible{outfits.length === 1 ? "" : "s"} <b>→</b></small></button>
                <button type="button" className="summary-card" onClick={() => navigate("calendar")}><span className="summary-icon blue">▦</span><span className="summary-label">Looks planifiés</span><strong>{scheduled.length}</strong><small>ce mois-ci <b>→</b></small></button>
                <button type="button" className="summary-card" onClick={() => navigate("packing")}><span className="summary-icon peach">▣</span><span className="summary-label">Prochain voyage</span><strong>{packingLists.length}</strong><small>liste{packingLists.length === 1 ? "" : "s"} de valise <b>→</b></small></button>
              </div>
              <div className="overview-grid">
                <section className="content-card">
                  <div className="card-heading"><div><span className="eyebrow">TES PROCHAINES TENUES</span><h3>Au programme</h3></div><button type="button" className="text-button" onClick={() => navigate("calendar")}>Tout voir →</button></div>
                  {scheduled.length === 0 ? <EmptyState icon="▦" title="Ton calendrier est encore libre" text="Planifie un look pour gagner du temps les matins pressés." action="Ouvrir le calendrier" onAction={() => navigate("calendar")} /> : <div className="upcoming-list">{scheduled.slice().sort((a, b) => a.date.localeCompare(b.date)).slice(0, 4).map((entry) => <div className="upcoming-row" key={entry.date}><span className="upcoming-date"><b>{new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { day: "2-digit" })}</b><small>{new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { month: "short" })}</small></span><div className="upcoming-images">{entry.items.slice(0, 3).map((item) => <img key={item.id} src={item.image_url} alt="" />)}</div><div className="upcoming-copy"><strong>{entry.items.length} pièces choisies</strong><span>{new Date(`${entry.date}T12:00:00`).toLocaleDateString("fr-TN", { weekday: "long" })}</span></div><button className="icon-button" type="button" onClick={() => navigate("calendar")} aria-label="Voir dans le calendrier">→</button></div>)}</div>}
                </section>
                <section className="content-card style-overview">
                  <div className="card-heading"><div><span className="eyebrow">TA SIGNATURE</span><h3>Mon style en bref</h3></div><span className="style-badge">✦</span></div>
                  {profile ? <><p className="style-overview-count"><strong>{profile.wardrobe_size}</strong> pièces analysées</p><div className="style-chips">{profile.favorite_styles.slice(0, 3).map((style) => <span key={style}>✧ {style}</span>)}{profile.favorite_colors.slice(0, 3).map((color) => <span key={color}>● {color}</span>)}</div><button type="button" className="text-button" onClick={() => navigate("profile")}>Explorer mon profil →</button></> : <EmptyState icon="◎" title="Ton profil se dessine" text="Ajoute des vêtements pour découvrir les couleurs et styles de ton dressing." action="Ajouter une pièce" onAction={() => navigate("wardrobe")} />}
                </section>
              </div>
              <section className="quick-actions">
                <div><span className="eyebrow">À DÉCOUVRIR</span><h3>Et si on allait plus loin ?</h3></div>
                <button type="button" onClick={() => navigate("purchase")}><span>♡</span><b>Vérifier un achat</b><small>Fais le bon choix</small><i>→</i></button>
                <button type="button" onClick={() => navigate("donation")}><span>🎁</span><b>Dons & Seconde vie</b><small>{donations.filter((d) => d.status === "pending").length} pièce(s) à donner</small><i>→</i></button>
                <button type="button" onClick={() => navigate("tryon")}><span>✦</span><b>Essayer une pièce</b><small>Projette-toi dans ton look</small><i>→</i></button>
                <button type="button" onClick={() => navigate("packing")}><span>▣</span><b>Préparer ma valise</b><small>Voyage sans rien oublier</small><i>→</i></button>
              </section>
            </>
          )}

          {screen === "wardrobe" && <WardrobeView items={items} favorites={wardrobeFavorites} busy={busy} onAdd={addItem} onDelete={requestDeleteItem} usage={usage} categoryPrompt={categoryPrompt} onConfirmCategory={confirmCategory} onCancelCategory={() => setCategoryPrompt(null)} onWorn={markWorn} onSeasonChange={changeSeason} onToggleFavorite={(id) => toggleFavorite(id, "wardrobe")} />}
          {donationModalItem && (
            <DonationPromptModal
              item={donationModalItem}
              onDonate={handleTransferToDonation}
              onDeletePermanent={handlePermanentDelete}
              onCancel={() => setDonationModalItem(null)}
            />
          )}
          {ingestionReview && <WardrobeIngestionModal review={ingestionReview} busy={busy === "wardrobe-upload"} onConfirm={confirmIngestion} onCancel={() => setIngestionReview(null)} />}
          {screen === "outfits" && <OutfitsView items={items} itemsById={itemsById} outfits={outfits} favorites={outfitFavorites} scheduled={scheduled} today={today} busy={busy} onGenerate={generateLooks} onToggleFavorite={(id) => toggleFavorite(id, "outfit")} onSchedule={scheduleOutfit} onFeedback={saveOutfitFeedback} />}
          {screen === "calendar" && <CalendarView anchor={monthAnchor} onMonthChange={setMonthAnchor} scheduled={scheduled} items={items} loading={loading} onSave={saveCalendarOutfit} onRemove={removeCalendarOutfit}  onRender={renderCalendarOutfit} />}
          {screen === "profile" && <ProfileView user={user} profile={profile} busy={busy} onAvatar={uploadAvatar} onNavigate={navigate} />}
          {screen === "assistant" && <LlmAssistant onNavigate={navigate} />}
          {screen === "packing" && <PackingView lists={packingLists} busy={busy} onCreate={createPacking} onToggle={togglePackedItem} onDelete={deletePackingList} />}
          {screen === "purchase" && (
            <PurchaseView
              result={purchaseResult}
              busy={busy}
              onCheck={runPurchaseCheck}
              onRestoreResult={setPurchaseResult}
            />
          )}
          {screen === "donation" && (
            <DonationView
              donations={donations}
              onMarkDonated={markDonated}
              onRestoreToWardrobe={restoreDonationToWardrobe}
              onRemoveDonation={removeDonation}
              onUpdateCondition={updateDonationCondition}
              onNavigate={navigate}
            />
          )}
          {screen === "tryon" && (
            <TryOnView
              user={user}
              items={items}
              selectedIds={selectedTryOnItems}
              result={tryOnResult}
              busy={busy}
              onToggleSelect={toggleTryOnItem}
              onClearSelect={clearTryOnSelection}
              onSelectPresetAvatar={selectPresetAvatar}
              onAvatar={uploadAvatar}
              onTryOn={generateTryOn}
            />
          )}

          <footer className="app-footer"><span>DressMe</span><span>Avec amour, depuis la Tunisie ✦</span><span>Ton dressing, en mieux.</span></footer>
        </div>
      </main>
    </div>
  );
}

function PageHeading({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">TON STUDIO DE STYLE</p><h1>{title}</h1><p className="page-subtitle">{subtitle}</p></div>{action}</div>;
}

function EmptyState({ icon, title, text, action, onAction }: { icon: string; title: string; text: string; action?: string; onAction?: () => void }) {
  return <div className="empty-state"><span>{icon}</span><h3>{title}</h3><p>{text}</p>{action && onAction && <button type="button" className="button button-outline" onClick={onAction}>{action} →</button>}</div>;
}

function CategoryPrompt({ prompt, busy, onConfirm, onCancel }: {
  prompt: CategoryPromptState;
  busy: boolean;
  onConfirm: (category: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState(prompt.suggested_category);
  return <section className="content-card category-prompt" role="alert">
    <img src={prompt.imageUrl} alt="Photo à classer" />
    <div>
      <span className="eyebrow">ON A BESOIN DE TOI</span>
      <h3>Quelle est cette pièce ?</h3>
      <p>{prompt.message} (DressMe hésite : « {categoryLabel(prompt.suggested_category)} », sûr à {Math.round(prompt.confidence * 100)} %.)</p>
      <div className="button-row">
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Catégorie de la pièce">{WARDROBE_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <button type="button" className="button button-primary" disabled={busy} onClick={() => void onConfirm(category)}>{busy ? "Ajout…" : "Ajouter comme ça"}</button>
        <button type="button" className="button button-outline" disabled={busy} onClick={onCancel}>Annuler</button>
      </div>
    </div>
  </section>;
}

function WardrobeIngestionModal({
  review,
  busy,
  onConfirm,
  onCancel,
}: {
  review: {
    imageUrl: string;
    analysis: WardrobeAnalysisResponse;
    selectedCategory: string;
    selectedSeason: string;
  };
  busy: boolean;
  onConfirm: (category: string, season: string, finalImageUrl?: string) => Promise<void>;
  onCancel: () => void;
}) {
  const { analysis, imageUrl } = review;
  const seg = analysis.segmentation;
  const hasExtracted = Boolean(seg?.person_detected && seg.extracted_garments && seg.extracted_garments.length > 0);

  const [selectedImage, setSelectedImage] = useState<string>(
    hasExtracted && seg?.extracted_garments?.[0]?.image_url
      ? seg.extracted_garments[0].image_url
      : imageUrl
  );
  const [category, setCategory] = useState(
    hasExtracted && seg?.extracted_garments?.[0]?.category
      ? seg.extracted_garments[0].category
      : review.selectedCategory
  );
  const [season, setSeason] = useState(review.selectedSeason);
  const cv = analysis.cv_diagnostics;
  const quality = cv?.quality;
  const rag = analysis.rag_analysis;
  const styling = analysis.styling_insights;
  const palette = analysis.kmeans_palette;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="ingestion-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-header-titles">
            <span className="eyebrow">AGENT D'INGESTION MULTIMODAL</span>
            <h2>Analyse IA du vêtement</h2>
            <p className="modal-sub">SegFormer AI, Computer Vision, Deep Learning & RAG</p>
          </div>
          <button type="button" className="modal-close" onClick={onCancel} aria-label="Fermer">✕</button>
        </div>

        {/* Human Detection & Garment Isolation Hero Banner */}
        {hasExtracted && seg?.extracted_garments && (
          <div className="seg-banner-container">
            <div className="seg-banner-header">
              <span className="seg-banner-icon">✂️</span>
              <div className="seg-banner-text">
                <div className="seg-banner-title-row">
                  <strong>Mannequin / Personne détectée sur la photo !</strong>
                  <span className="seg-ai-tag">SegFormer-B2 Vision AI</span>
                </div>
                <p>
                  L'intelligence artificielle a isolé les vêtements portés sur fond blanc épuré pour un rendu dressing professionnel. Choisis la pièce à enregistrer :
                </p>
              </div>
            </div>

            <div className="seg-garments-selector">
              {seg.extracted_garments.map((g, idx) => {
                const isSelected = selectedImage === g.image_url;
                return (
                  <button
                    key={idx}
                    type="button"
                    className={`seg-garment-card ${isSelected ? "active" : ""}`}
                    onClick={() => {
                      setSelectedImage(g.image_url);
                      setCategory(g.category);
                    }}
                  >
                    <div className="seg-img-container">
                      <img src={g.image_url} alt={g.category} />
                      {isSelected && <span className="seg-checked-badge">✓ Choisi</span>}
                    </div>
                    <div className="seg-garment-info">
                      <span className="seg-category-label">{categoryLabel(g.category)}</span>
                      <span className="seg-type-pill">Sans mannequin (isolé)</span>
                      <small className="seg-share-label">{(g.share * 100).toFixed(0)}% de la tenue</small>
                    </div>
                  </button>
                );
              })}

              <button
                type="button"
                className={`seg-garment-card ${selectedImage === imageUrl ? "active" : ""}`}
                onClick={() => {
                  setSelectedImage(imageUrl);
                  setCategory(review.selectedCategory);
                }}
              >
                <div className="seg-img-container">
                  <img src={imageUrl} alt="Photo brute originale" />
                  {selectedImage === imageUrl && <span className="seg-checked-badge">✓ Choisi</span>}
                </div>
                <div className="seg-garment-info">
                  <span className="seg-category-label">Photo brute</span>
                  <span className="seg-type-pill muted">Avec personne / décor</span>
                  <small className="seg-share-label">Image originale</small>
                </div>
              </button>
            </div>
          </div>
        )}

        <div className="ingestion-grid">
          {/* Left Column: Visual & Diagnostics */}
          <div className="ingestion-col-left">
            <div className="ingestion-preview-card">
              <img src={selectedImage} alt="Vêtement analysé" className="ingestion-photo" />
              {selectedImage !== imageUrl && (
                <div className="cutout-indicator-badge">
                  <span>✨ Vêtement détouré (mannequin retiré)</span>
                </div>
              )}
              {quality?.quality_score != null && (
                <div className={`quality-badge ${quality.sharpness}`}>
                  <span className="quality-icon">✦</span>
                  <span>Qualité CV : <b>{quality.quality_score}%</b> · {quality.sharpness === "sharp" ? "Photo nette" : quality.sharpness === "acceptable" ? "Acceptable" : "Floue"}</span>
                </div>
              )}
            </div>

            {/* OpenCV Metrics */}
            <div className="cv-metrics-card">
              <h4>Diagnostics Computer Vision (OpenCV)</h4>
              <div className="metrics-pills">
                <span title="Variance du Laplacien pour détection de flou">Laplacian : <b>{quality?.laplacian_variance ?? "-"}</b></span>
                <span>Luminosité : <b>{quality?.brightness ?? "-"}</b></span>
                <span>Contraste : <b>{quality?.contrast ?? "-"}</b></span>
                <span>Dimensions : <b>{cv?.dimensions?.width}×{cv?.dimensions?.height}</b></span>
              </div>
              {quality?.warnings && quality.warnings.length > 0 && (
                <div className="cv-warnings-list">
                  {quality.warnings.map((w: string, i: number) => (
                    <p key={i} className="cv-warning-item">ℹ️ {w}</p>
                  ))}
                </div>
              )}
            </div>

            {/* K-Means Color Palette */}
            {palette && palette.length > 0 && (
              <div className="kmeans-palette-card">
                <h4>Palette extraite par K-Means</h4>
                <div className="kmeans-swatches-grid">
                  {palette.map((p, idx) => (
                    <div key={idx} className="kmeans-swatch-item">
                      <span className="kmeans-swatch-circle" style={{ backgroundColor: p.hex }} />
                      <div className="kmeans-swatch-info">
                        <strong>{p.label}</strong>
                        <small>{p.hex} · {p.percentage}%</small>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Classification, RAG & Styling */}
          <div className="ingestion-col-right">
            {/* Duplicate Alert if RAG found similar */}
            {rag?.duplicate_warning && (
              <div className="rag-duplicate-alert">
                <span className="alert-icon">⚠️</span>
                <div>
                  <strong>Alerte Doublon RAG</strong>
                  <p>{rag.duplicate_warning}</p>
                  {rag.similar_items?.[0] && (
                    <div className="duplicate-thumb-row">
                      <img src={rag.similar_items[0].image_url} alt="Pièce similaire" className="duplicate-thumb" />
                      <span>{rag.similar_items[0].similarity}% similaire avec votre {categoryLabel(rag.similar_items[0].category)} existant</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Attributes Confirmation */}
            <div className="attributes-config-card">
              <h4>Classification & Confirmation</h4>
              <div className="form-row">
                <label className="field-group">
                  <span>Catégorie {analysis.confidence?.category ? <small className="conf-pill">{(analysis.confidence.category * 100).toFixed(0)}% confiance</small> : null}</span>
                  <select value={category} onChange={(e) => setCategory(e.target.value)}>
                    {WARDROBE_CATEGORIES.map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </label>

                <label className="field-group">
                  <span>Saison de la pièce</span>
                  <select value={season} onChange={(e) => setSeason(e.target.value)}>
                    <option value="toutes_saisons">Toutes saisons</option>
                    {ITEM_SEASONS.map(([val, label]) => (
                      <option key={val} value={val}>{label}</option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="detected-tags-row">
                {analysis.style && <span className="style-pill">✧ Style : <b>{categoryLabel(analysis.style)}</b></span>}
                {analysis.pattern && <span className="style-pill">▦ Motif : <b>{categoryLabel(analysis.pattern)}</b></span>}
                {analysis.colors && analysis.colors.length > 0 && (
                  <span className="style-pill">● Couleurs : <b>{analysis.colors.map(categoryLabel).join(", ")}</b></span>
                )}
              </div>
            </div>

            {/* RAG Complementary Pairings */}
            {rag?.recommended_pairings && rag.recommended_pairings.length > 0 && (
              <div className="rag-pairings-card">
                <h4>✦ Looks possibles avec ton dressing (RAG)</h4>
                <div className="pairings-scroll">
                  {rag.recommended_pairings.map((pair, i) => (
                    <div key={i} className="pairing-card">
                      <img src={pair.image_url} alt={pair.category} />
                      <div className="pairing-info">
                        <strong>{categoryLabel(pair.category)}</strong>
                        <small>{pair.colors?.map(categoryLabel).join(", ") || pair.style || "Dressing"}</small>
                        <span className="harmony-badge">Harmonie : {(pair.score * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Styling Insights */}
            {styling?.editorial_advice && (
              <div className="styling-insights-card">
                <h4>✨ Note du Styliste IA</h4>
                <p className="editorial-text">{styling.editorial_advice}</p>
                {styling.recommended_occasions && styling.recommended_occasions.length > 0 && (
                  <div className="occasions-chips">
                    {styling.recommended_occasions.map((occ, i) => (
                      <span key={i} className="occasion-chip">📍 {occ}</span>
                    ))}
                  </div>
                )}
                {styling.care_tip && (
                  <p className="care-tip-text">🧼 <b>Conseil d'entretien :</b> {styling.care_tip}</p>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="button button-outline" onClick={onCancel} disabled={busy}>
            Annuler
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={() => void onConfirm(category, season, selectedImage)}
            disabled={busy}
          >
            {busy ? "Enregistrement…" : "✓ Confirmer et ajouter au dressing"}
          </button>
        </div>
      </div>
    </div>
  );
}


function WardrobeView({ items, favorites, busy, usage, categoryPrompt, onConfirmCategory, onCancelCategory, onAdd, onDelete, onWorn, onSeasonChange, onToggleFavorite }: {
  items: ClothingItem[];
  favorites: string[];
  busy: string;
  onAdd: (file: File, season: string) => Promise<void>;
  onDelete: (item: ClothingItem) => void | Promise<void>;
  usage: Record<string, ItemUsage>;
  categoryPrompt: CategoryPromptState | null;
  onConfirmCategory: (category: string) => Promise<void>;
  onCancelCategory: () => void;
  onWorn: (item: ClothingItem) => Promise<void>;
  onSeasonChange: (item: ClothingItem, season: string) => Promise<void>;
  onToggleFavorite: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("toutes");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [season, setSeason] = useState("");
  const [sortBy, setSortBy] = useState<"recent" | "wear-desc" | "wear-asc" | "alpha">("recent");
  const [viewMode, setViewMode] = useState<"grid" | "compact">("grid");
  const [kpiFilter, setKpiFilter] = useState<"all" | "favorites" | "worn" | "toConfirm">("all");

  const toConfirmCount = items.filter((item) => item.season_source === "vision" || !item.season).length;
  const wornCount = items.filter((item) => (usage[item.id]?.wear_count || 0) > 0).length;

  const filtered = items.filter((item) => {
    if (kpiFilter === "favorites" && !favorites.includes(item.id)) return false;
    if (kpiFilter === "worn" && !(usage[item.id]?.wear_count > 0)) return false;
    if (kpiFilter === "toConfirm" && !(item.season_source === "vision" || !item.season)) return false;

    const matchesCategory = category === "toutes" || (item.category ?? "autre").toLocaleLowerCase() === category;
    const matchesFavorite = !favoritesOnly || favorites.includes(item.id);
    const matchesSeason = !season || item.season === season || (season !== "toutes_saisons" && item.season === "toutes_saisons");
    const searchable = [item.category, item.style, item.season, itemSeasonLabel(item.season), item.pattern, ...(item.colors ?? [])].join(" ").toLocaleLowerCase();
    return matchesCategory && matchesFavorite && matchesSeason && searchable.includes(query.trim().toLocaleLowerCase());
  });

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === "wear-desc") return (usage[b.id]?.wear_count || 0) - (usage[a.id]?.wear_count || 0);
    if (sortBy === "wear-asc") return (usage[a.id]?.wear_count || 0) - (usage[b.id]?.wear_count || 0);
    if (sortBy === "alpha") return (categoryLabel(a.category) || "").localeCompare(categoryLabel(b.category) || "");
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

  return <>
    <PageHeading title="Mon dressing" subtitle="Ajoute, retrouve et organise les pièces que tu aimes porter." action={<label className={`button button-primary file-button${busy === "wardrobe-upload" ? " is-disabled" : ""}`}>＋ {busy === "wardrobe-upload" ? "Analyse en cours…" : "Ajouter une pièce"}<input type="file" accept="image/*" disabled={busy === "wardrobe-upload"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onAdd(file, season); event.target.value = ""; }} /></label>} />

    {categoryPrompt && <CategoryPrompt prompt={categoryPrompt} busy={busy === "wardrobe-upload"} onConfirm={onConfirmCategory} onCancel={onCancelCategory} />}

    {/* Quick KPI stats chips */}
    <div className="wardrobe-kpi-bar">
      <button
        type="button"
        className={`kpi-chip ${kpiFilter === "all" && !favoritesOnly ? "is-active" : ""}`}
        onClick={() => { setKpiFilter("all"); setFavoritesOnly(false); }}
      >
        <span className="kpi-icon">◈</span>
        <div className="kpi-meta">
          <strong>{items.length}</strong>
          <span>Toutes les pièces</span>
        </div>
      </button>
      <button
        type="button"
        className={`kpi-chip ${kpiFilter === "favorites" || favoritesOnly ? "is-active" : ""}`}
        onClick={() => { setKpiFilter("favorites"); setFavoritesOnly(true); }}
      >
        <span className="kpi-icon pink">♥</span>
        <div className="kpi-meta">
          <strong>{favorites.length}</strong>
          <span>Favoris</span>
        </div>
      </button>
      <button
        type="button"
        className={`kpi-chip ${kpiFilter === "worn" ? "is-active" : ""}`}
        onClick={() => { setKpiFilter("worn"); setFavoritesOnly(false); }}
      >
        <span className="kpi-icon gold">⚡</span>
        <div className="kpi-meta">
          <strong>{wornCount}</strong>
          <span>Déjà portées</span>
        </div>
      </button>
      {toConfirmCount > 0 && (
        <button
          type="button"
          className={`kpi-chip warn ${kpiFilter === "toConfirm" ? "is-active" : ""}`}
          onClick={() => { setKpiFilter("toConfirm"); setFavoritesOnly(false); }}
        >
          <span className="kpi-icon warn">⚠️</span>
          <div className="kpi-meta">
            <strong>{toConfirmCount}</strong>
            <span>À confirmer</span>
          </div>
        </button>
      )}
    </div>

    {/* Quick Category Chips */}
    {categories.length > 0 && (
      <div className="category-chips-bar">
        <button
          type="button"
          className={`cat-chip ${category === "toutes" ? "active" : ""}`}
          onClick={() => setCategory("toutes")}
        >
          Toutes <small>({items.length})</small>
        </button>
        {categories.map((cat) => {
          const count = items.filter((i) => (i.category ?? "autre").toLowerCase() === cat).length;
          return (
            <button
              key={cat}
              type="button"
              className={`cat-chip ${category === cat ? "active" : ""}`}
              onClick={() => setCategory(cat)}
            >
              {categoryLabel(cat)} <small>({count})</small>
            </button>
          );
        })}
      </div>
    )}

    {/* Complete Toolbar */}
    <div className="wardrobe-toolbar">
      <label className="search-field">
        <span>⌕</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Chercher une couleur, un style, un mot-clé…"
        />
        {query && (
          <button type="button" className="clear-search-btn" onClick={() => setQuery("")} title="Effacer la recherche">✕</button>
        )}
      </label>

      <label className="filter-select">
        <span>Saison</span>
        <select value={season} onChange={(event) => setSeason(event.target.value)}>
          <option value="">Toutes saisons</option>
          {ITEM_SEASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>

      <label className="filter-select">
        <span>Trier par</span>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value as any)}>
          <option value="recent">Plus récents</option>
          <option value="wear-desc">Plus souvent portés</option>
          <option value="wear-asc">Moins portés</option>
          <option value="alpha">Catégorie (A-Z)</option>
        </select>
      </label>

      <div className="view-mode-toggle" role="group" aria-label="Mode d'affichage">
        <button
          type="button"
          className={viewMode === "grid" ? "active" : ""}
          onClick={() => setViewMode("grid")}
          title="Grille standard"
        >
          ⊞
        </button>
        <button
          type="button"
          className={viewMode === "compact" ? "active" : ""}
          onClick={() => setViewMode("compact")}
          title="Grille compacte"
        >
          ⊟
        </button>
      </div>

      {hasActiveFilters && (
        <button type="button" className="reset-filters-btn" onClick={resetAllFilters} title="Réinitialiser tous les filtres">
          ✕ Réinitialiser
        </button>
      )}
    </div>

    <div className="results-line">
      <span>
        <b>{sorted.length}</b> pièce{sorted.length > 1 ? "s" : ""} trouvée{sorted.length > 1 ? "s" : ""}
        {hasActiveFilters && <span className="active-filter-badge"> · Filtres actifs</span>}
      </span>
      <span className="photo-tip">💡 Photos nettes sur fond uni = reconnaissance IA optimale</span>
    </div>

    {sorted.length === 0 ? (
      <EmptyState
        icon={items.length === 0 ? "◈" : "⌕"}
        title={items.length === 0 ? "Ton dressing commence ici" : "Aucune pièce trouvée"}
        text={items.length === 0 ? "Ajoute une photo de vêtement : DressMe identifiera sa catégorie, ses couleurs et son style." : "Essaie d’ajuster ta recherche ou de réinitialiser tes filtres."}
      />
    ) : (
      <div className={`clothing-grid ${viewMode === "compact" ? "is-compact" : ""}`}>
        {sorted.map((item) => {
          const palette = (item.attribute_confidence as any)?.kmeans_palette;
          const cvDiag = (item.attribute_confidence as any)?.cv_diagnostics;
          const ragAnalysis = (item.attribute_confidence as any)?.rag_analysis;
          const styling = (item.attribute_confidence as any)?.styling_insights;
          const wearInfo = usage[item.id];
          return (
            <article className="clothing-card" key={item.id}>
              <div className="clothing-photo">
                <img src={item.image_url} alt={categoryLabel(item.category)} loading="lazy" />
                <span className="photo-category-tag">{categoryLabel(item.category)}</span>
                <button
                  type="button"
                  className={`favorite-toggle${favorites.includes(item.id) ? " is-favorite" : ""}`}
                  aria-label={favorites.includes(item.id) ? "Retirer des favoris" : "Ajouter aux favoris"}
                  aria-pressed={favorites.includes(item.id)}
                  onClick={() => onToggleFavorite(item.id)}
                >
                  {favorites.includes(item.id) ? "♥" : "♡"}
                </button>
              </div>

              <div className="clothing-info">
                <div className="clothing-title-row">
                  <h3>{item.style ? categoryLabel(item.style) : "Pièce de mon dressing"}</h3>
                  {item.season && <span className="season-badge">{itemSeasonLabel(item.season)}</span>}
                </div>
                <p className="clothing-attributes-desc">
                  {[...(item.colors ?? []), item.pattern].filter(Boolean).map(categoryLabel).join(" · ") || "Style à découvrir"}
                </p>

                {Array.isArray(palette) && palette.length > 0 && (
                  <div className="kmeans-palette-row">
                    {palette.map((p: any, i: number) => (
                      <span
                        key={i}
                        title={`${p.label} (${p.percentage}%)`}
                        className="palette-dot"
                        style={{ backgroundColor: p.hex }}
                      />
                    ))}
                    <small className="palette-tag">K-Means IA</small>
                  </div>
                )}

                {styling?.editorial_advice && (
                  <details className="outfit-explanation">
                    <summary>✦ Note du Styliste & RAG</summary>
                    <div className="explanation-drawer">
                      {cvDiag?.quality?.sharpness && (
                        <p className="diag-tag">✓ OpenCV : netteté {cvDiag.quality.sharpness}</p>
                      )}
                      {ragAnalysis?.duplicate_warning && (
                        <p className="dup-warning">⚠️ {ragAnalysis.duplicate_warning}</p>
                      )}
                      <p className="editorial-content">{styling.editorial_advice}</p>
                      {styling.care_tip && (
                        <p className="care-tip-line">🧼 {styling.care_tip}</p>
                      )}
                    </div>
                  </details>
                )}

                <div className="card-actions-row">
                  <label className="season-picker">
                    <select
                      aria-label="Saison de la pièce"
                      value={item.season ?? ""}
                      onChange={(event) => { if (event.target.value) void onSeasonChange(item, event.target.value); }}
                    >
                      <option value="" disabled>Saison ?</option>
                      {ITEM_SEASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                    {(item.season_source === "vision" || !item.season) && <span className="confirm-badge">À confirmer</span>}
                  </label>

                  <div className="wear-log-container">
                    <span className="wear-count-badge">
                      {wearInfo ? `Porté ${wearInfo.wear_count}×` : "Neuf (0×)"}
                    </span>
                    <button
                      type="button"
                      className="worn-button"
                      onClick={() => void onWorn(item)}
                      title="Enregistrer comme porté aujourd'hui"
                    >
                      ＋ Porté
                    </button>
                  </div>
                </div>

                <button type="button" className="remove-link" onClick={() => void onDelete(item)}>
                  Retirer du dressing
                </button>
              </div>
            </article>
          );
        })}
      </div>
    )}
  </>;
}

function OutfitsView({ items, itemsById, outfits, favorites, scheduled, today, busy, onGenerate, onToggleFavorite, onSchedule, onFeedback }: {
  items: ClothingItem[];
  itemsById: Map<string, ClothingItem>;
  outfits: Outfit[];
  favorites: string[];
  scheduled: ScheduledOutfit[];
  today: string;
  busy: string;
  onGenerate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onToggleFavorite: (id: string) => void;
  onSchedule: (outfit: Outfit, date: string) => Promise<void>;
  onFeedback: (outfitId: string, rating: OutfitFeedback | null) => Promise<void>;
}) {
  const [showFavorites, setShowFavorites] = useState(false);
  const [selectedOccasion, setSelectedOccasion] = useState("");
  const [selectedCity, setSelectedCity] = useState("Tunis");
  const [planDates, setPlanDates] = useState<Record<string, string>>({});
  const [cityWeathers, setCityWeathers] = useState<Record<string, { temp: number; icon: string }>>({
    Tunis:  { temp: 22, icon: "🌤️" },
    Sousse: { temp: 24, icon: "☀️" },
    Sfax:   { temp: 21, icon: "⛅" },
    Djerba: { temp: 25, icon: "🌴" },
  });

  useEffect(() => {
    ["Tunis", "Sousse", "Sfax", "Djerba"].forEach((city) => {
      api.get(`/weather/${city}`)
        .then(({ data }) => setCityWeathers((prev) => ({ ...prev, [city]: { temp: data.temp, icon: data.icon } })))
        .catch(() => {});
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
    { name: "Tunis",  temp: `${cityWeathers["Tunis"]?.temp ?? 22}°C`,  icon: cityWeathers["Tunis"]?.icon  ?? "🌤️" },
    { name: "Sousse", temp: `${cityWeathers["Sousse"]?.temp ?? 24}°C`, icon: cityWeathers["Sousse"]?.icon ?? "☀️" },
    { name: "Sfax",   temp: `${cityWeathers["Sfax"]?.temp ?? 21}°C`,   icon: cityWeathers["Sfax"]?.icon   ?? "⛅" },
    { name: "Djerba", temp: `${cityWeathers["Djerba"]?.temp ?? 25}°C`, icon: cityWeathers["Djerba"]?.icon ?? "🌴" },
  ];

  const tomorrow = new Date(Date.now() + 86400000).toISOString().split("T")[0];

  const KNOWN_OCCASIONS = ["quotidien", "travail", "sortie", "soirée", "événement"];
  const filtered = outfits.filter((outfit) => {
    if (showFavorites && !favorites.includes(outfit.id)) return false;
    if (selectedOccasion && outfit.occasion) {
      // Normalize: check if the outfit occasion starts with or contains the selected occasion
      const occ = outfit.occasion.toLowerCase();
      const sel = selectedOccasion.toLowerCase();
      if (occ !== sel && !occ.startsWith(sel) && !occ.includes(sel)) return false;
    }
    // If selectedOccasion is set but outfit.occasion is not in known list, still show it
    return true;
  });

  return <>
    <PageHeading title="Des looks faits pour toi" subtitle="Recommandations intelligentes générées à partir de ta garde-robe, de la météo et de tes envies." />

    {/* Interactive Look Generation Form */}
    <form className="content-card recommendation-form modern-generator-card" onSubmit={(event) => void onGenerate(event)}>
      <div className="card-heading">
        <div>
          <span className="eyebrow">STUDIO DE COMPOSITION IA</span>
          <h3>Génère une tenue sur-mesure</h3>
        </div>
        <span className="form-sparkle">✦</span>
      </div>

      {/* Occasion Quick Chips */}
      <div className="form-section-group">
        <label className="section-mini-label">1. Choisis ton occasion :</label>
        <input type="hidden" name="occasion" value={selectedOccasion} />
        <div className="interactive-chips-row">
          {OCCASION_DATA.map((occ) => (
            <button
              type="button"
              key={occ.id}
              className={`generator-chip ${selectedOccasion === occ.id ? "active" : ""}`}
              onClick={() => setSelectedOccasion(occ.id)}
            >
              <span className="chip-icon">{occ.icon}</span>
              <span>{occ.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="form-section-group">
        <label className="section-mini-label" htmlFor="outfit-request-text">Une envie précise ? (facultatif)</label>
        <textarea
          id="outfit-request-text"
          name="request_text"
          className="request-textarea"
          maxLength={500}
          placeholder="Ex. Je vais dîner au restaurant après le travail"
        />
        <p className="inline-hint">Décris le contexte en langage courant. Les pièces proposées restent limitées à ton dressing.</p>
      </div>

      {/* City & Weather Chips */}
      <div className="form-section-group">
        <label className="section-mini-label">2. Destination & Météo :</label>
        <input type="hidden" name="city" value={selectedCity} />
        <div className="interactive-chips-row">
          {CITY_DATA.map((city) => (
            <button
              type="button"
              key={city.name}
              className={`generator-chip city-chip ${selectedCity === city.name ? "active" : ""}`}
              onClick={() => setSelectedCity(city.name)}
            >
              <span>{city.icon}</span>
              <span>{city.name}</span>
              <small className="temp-badge">{city.temp}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="form-submit-row">
        <p className="generator-hint">
          {items.length} pièces dans ton dressing prêtes à être associées par l'algorithme Polyvore IA.
        </p>
        <button className="button button-primary generator-btn" disabled={busy === "looks" || items.length === 0}>
          {busy === "looks" ? "Composition du look par l'IA…" : "✨ Trouver mes tenues"}
        </button>
      </div>
      {items.length === 0 && <p className="inline-hint error-hint">Ajoute d’abord quelques vêtements dans ton dressing pour recevoir des propositions.</p>}
    </form>

    {/* Proposals Toolbar */}
    <div className="section-toolbar">
      <div>
        <span className="eyebrow">PROPOSITIONS DU STYLISTE</span>
        <h2>{filtered.length} look{filtered.length > 1 ? "s" : ""} disponible{filtered.length > 1 ? "s" : ""}</h2>
      </div>
      <div className="segmented-control">
        <button className={!showFavorites ? "active" : ""} type="button" onClick={() => setShowFavorites(false)}>
          Tous les looks ({outfits.length})
        </button>
        <button className={showFavorites ? "active" : ""} type="button" onClick={() => setShowFavorites(true)}>
          ♥ Coups de cœur {favorites.length > 0 && `(${favorites.length})`}
        </button>
      </div>
    </div>

    {filtered.length === 0 ? (
      <EmptyState
        icon={showFavorites ? "♡" : "✧"}
        title={showFavorites ? "Aucun look favori pour le moment" : "Prête pour de nouvelles inspirations ?"}
        text={showFavorites ? "Appuie sur le cœur d'un look pour le retrouver dans tes favoris." : "Clique sur 'Trouver mes tenues' ci-dessus pour que l'IA compose tes tenues idéales."}
      />
    ) : (
      <div className="outfit-grid">
        {filtered.map((outfit) => {
          const outfitItems = outfit.item_ids.map((id) => itemsById.get(id)).filter((item): item is ClothingItem => Boolean(item));
          const isPlanned = scheduled.some((entry) => entry.item_ids.length === outfit.item_ids.length && entry.item_ids.every((id) => outfit.item_ids.includes(id)));
          const matchPercent = outfit.relevance_score != null ? Math.round(outfit.relevance_score * 100) : 88;

          return (
            <article className="outfit-card modern-outfit-card" key={outfit.id}>
              <div className="outfit-card-top">
                <div>
                  <span className="category-pill">{outfit.occasion ? categoryLabel(outfit.occasion) : "Suggestion Styliste"}</span>
                  <h3>Un look pour {outfit.occasion ? categoryLabel(outfit.occasion) : "toi"}</h3>
                </div>
                <button
                  type="button"
                  className={`favorite-toggle outfit-heart${favorites.includes(outfit.id) ? " is-favorite" : ""}`}
                  aria-label={favorites.includes(outfit.id) ? "Retirer des favoris" : "Ajouter aux favoris"}
                  onClick={() => onToggleFavorite(outfit.id)}
                >
                  {favorites.includes(outfit.id) ? "♥" : "♡"}
                </button>
              </div>

              {/* Items row */}
              <div className="outfit-items modern-outfit-items">
                {outfitItems.map((item) => (
                  <div className="outfit-piece" key={item.id}>
                    <img src={item.image_url} alt={categoryLabel(item.category)} loading="lazy" />
                    <span className="piece-category-tag">{categoryLabel(item.category)}</span>
                  </div>
                ))}
              </div>

              {/* Meta & Match Score */}
              <div className="outfit-meta modern-outfit-meta">
                <span className={`match-score-pill ${matchPercent >= 85 ? "high-match" : ""}`}>
                  ✦ {matchPercent}% Harmonie Stylistique
                </span>
                <span className="pieces-count-tag">{outfit.item_ids.length} pièces associées</span>
              </div>

              {outfit.explanation && (
                <details className="outfit-explanation">
                  <summary>✦ Conseil éditorial de style</summary>
                  <p>{outfit.explanation}</p>
                </details>
              )}

              <div className="outfit-feedback-actions" aria-label="Donner ton avis sur cette tenue">
                {([
                  ["like", "👍 J’aime"],
                  ["dislike", "👎 Pas pour moi"],
                  ["worn", "✓ Déjà portée"],
                ] as const).map(([rating, label]) => {
                  const isBusy = busy === `outfit-feedback:${outfit.id}`;
                  const active = outfit.feedback === rating;
                  return (
                    <button
                      key={rating}
                      type="button"
                      className={`outfit-feedback-button${active ? " is-selected" : ""}`}
                      disabled={isBusy}
                      aria-pressed={active}
                      onClick={() => void onFeedback(outfit.id, active ? null : rating)}
                    >
                      {isBusy ? "Enregistrement…" : label}
                    </button>
                  );
                })}
              </div>

              {/* Scheduling Quick Actions */}
              <div className="schedule-quick-container">
                <div className="quick-plan-buttons">
                  <button
                    type="button"
                    className="plan-shortcut-btn"
                    onClick={() => void onSchedule(outfit, today)}
                    title="Planifier pour aujourd'hui"
                  >
                    ⚡ Aujourd'hui
                  </button>
                  <button
                    type="button"
                    className="plan-shortcut-btn"
                    onClick={() => void onSchedule(outfit, tomorrow)}
                    title="Planifier pour demain"
                  >
                    Demain
                  </button>
                </div>
                <div className="schedule-row">
                  <input
                    aria-label="Date de planification"
                    type="date"
                    min={today}
                    value={planDates[outfit.id] ?? today}
                    onChange={(event) => setPlanDates((current) => ({ ...current, [outfit.id]: event.target.value }))}
                  />
                  <button
                    type="button"
                    className="button button-outline"
                    onClick={() => void onSchedule(outfit, planDates[outfit.id] ?? today)}
                  >
                    {isPlanned ? "✓ Déjà prévu" : "📅 Planifier"}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    )}
  </>;
}

function DayThumb({ plan }: { plan: ScheduledOutfit }) {
  if (plan.render_image_url) return <img className="day-thumb" src={plan.render_image_url} alt="" loading="lazy" />;
  return <span className="day-collage" aria-hidden="true">{plan.items.slice(0, 4).map((item) => <img key={item.id} src={item.image_url} alt="" loading="lazy" />)}</span>;
}

function CalendarView({ anchor, onMonthChange, scheduled, items, loading, onSave, onRemove, onRender }: {
  anchor: Date;
  onMonthChange: (date: Date) => void;
  scheduled: ScheduledOutfit[];
  items: ClothingItem[];
  loading: boolean;
  onSave: (date: string, ids: string[]) => Promise<ScheduledOutfit>;
  onRemove: (date: string) => Promise<void>;
  onRender: (date: string) => Promise<void>;
}) {
  const [rendering, setRendering] = useState(false);
  const [selectedDate, setSelectedDate] = useState(todayLocal());
  const [editing, setEditing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const monthName = anchor.toLocaleDateString("fr-TN", { month: "long", year: "numeric" });
  const firstWeekday = (new Date(anchor.getFullYear(), anchor.getMonth(), 1).getDay() + 6) % 7;
  const dayCount = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate();
  const days: (number | null)[] = [...Array(firstWeekday).fill(null), ...Array.from({ length: dayCount }, (_, index) => index + 1)];
  while (days.length % 7) days.push(null);
  const plan = scheduled.find((entry) => entry.date === selectedDate);

  const currentMonthPlansCount = scheduled.filter((entry) => {
    const entryDate = new Date(entry.date);
    return entryDate.getMonth() === anchor.getMonth() && entryDate.getFullYear() === anchor.getFullYear();
  }).length;

  function changeMonth(delta: number) {
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
    } finally {
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
    } catch {
      return;
    } finally {
      setSaving(false);
    }
  }

  return <>
    <PageHeading title="Mon calendrier de style" subtitle="Visualise tes tenues quotidiennes, prépare tes matins à l'avance et habille ton avatar." />

    <div className="calendar-layout modern-calendar-layout">
      {/* Calendar Card */}
      <section className="content-card calendar-card">
        <div className="calendar-month-header">
          <div className="month-nav-group">
            <button type="button" className="month-arrow" aria-label="Mois précédent" onClick={() => changeMonth(-1)}>‹</button>
            <button type="button" className="today-jump-btn" onClick={jumpToToday}>Aujourd'hui</button>
            <button type="button" className="month-arrow" aria-label="Mois suivant" onClick={() => changeMonth(1)}>›</button>
          </div>
          <div>
            <span className="eyebrow">AGENDA DE MODE</span>
            <h2>{monthName}</h2>
            <small className="month-stat-sub">{currentMonthPlansCount} tenue{currentMonthPlansCount > 1 ? "s" : ""} programmée{currentMonthPlansCount > 1 ? "s" : ""}</small>
          </div>
        </div>

        <div className="calendar-grid">
          {["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((day) => (
            <span className="weekday" key={day}>{day}</span>
          ))}
          {days.map((day, index) => {
            if (!day) return <span className="calendar-blank" key={`blank-${index}`} />;
            const date = `${anchor.getFullYear()}-${String(anchor.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const dayPlan = scheduled.find((entry) => entry.date === date);
            const hasOutfit = Boolean(dayPlan);
            return (
              <button
                type="button"
                key={date}
                className={`calendar-day${hasOutfit ? " has-outfit" : ""}${selectedDate === date ? " selected" : ""}${date === todayLocal() ? " is-today" : ""}`}
                aria-label={`${day}${hasOutfit ? ", tenue planifiée" : ""}`}
                aria-pressed={selectedDate === date}
                onClick={() => { setSelectedDate(date); setEditing(false); }}
              >
                {dayPlan && <DayThumb plan={dayPlan} />}
                <span className="day-number">{day}</span>
                {hasOutfit && <span className="day-outfit-dot" title="Tenue planifiée" />}
              </button>
            );
          })}
        </div>
        {loading && <p className="inline-hint">Synchronisation du calendrier…</p>}
      </section>

      {/* Selected Day Details Card */}
      <section className="content-card day-details modern-day-details">
        <div className="day-details-header">
          <div>
            <span className="eyebrow">{selectedDate === todayLocal() ? "AUJOURD'HUI" : "JOUR SÉLECTIONNÉ"}</span>
            <h2>{new Date(`${selectedDate}T12:00:00`).toLocaleDateString("fr-TN", { weekday: "long", day: "numeric", month: "long" })}</h2>
          </div>
          <span className={`day-status-pill ${plan ? "status-planned" : "status-free"}`}>
            {plan ? "✦ Tenue prévue" : "Jour libre"}
          </span>
        </div>

        {plan && !editing ? (
          <>
            {plan.render_image_url && (
              <div className="avatar-render-wrap">
                <img className="avatar-render" src={plan.render_image_url} alt="Toi avec la tenue de ce jour" />
                <span className="avatar-render-badge">✨ Rendu Avatar IA</span>
              </div>
            )}
            <div className="day-plan-images modern-day-plan-images">
              {plan.items.map((item) => (
                <div key={item.id} className="day-plan-item-card">
                  <img src={item.image_url} alt={categoryLabel(item.category)} />
                  <span>{categoryLabel(item.category)}</span>
                </div>
              ))}
            </div>
            <p className="day-plan-summary">
              <b>{plan.items.length}</b> pièce{plan.items.length > 1 ? "s" : ""} sélectionnée{plan.items.length > 1 ? "s" : ""} pour cette journée.
            </p>
            <div className="button-row">
              {!plan.render_image_url && (
                <button type="button" className="button button-outline" disabled={rendering} onClick={() => void renderOnAvatar()}>
                  {rendering ? "Création du rendu… (≈ 1 min)" : "✦ Voir sur mon avatar"}
                </button>
              )}
              <button type="button" className="button button-primary" onClick={startEdit}>Modifier</button>
              <button type="button" className="button button-danger-light" onClick={() => void onRemove(selectedDate)}>Retirer</button>
            </div>
          </>
        ) : !editing ? (
          <div className="day-empty-state-wrap">
            <div className="day-empty-icon">✧</div>
            <h3>Aucune tenue pour ce jour</h3>
            <p className="inline-hint">Sélectionne les pièces de ton dressing pour composer ton look en toute sérénité.</p>
            <button type="button" className="button button-primary" onClick={startEdit}>＋ Planifier un look</button>
          </div>
        ) : (
          <>
            <p className="inline-hint">Clique sur les pièces de ton dressing à associer pour cette date :</p>
            <div className="calendar-pick-grid">
              {items.map((item) => (
                <button
                  type="button"
                  className={`calendar-pick-item${selectedIds.includes(item.id) ? " picked" : ""}`}
                  aria-pressed={selectedIds.includes(item.id)}
                  key={item.id}
                  onClick={() => setSelectedIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])}
                >
                  <img src={item.image_url} alt={categoryLabel(item.category)} />
                  <span>{categoryLabel(item.category)}</span>
                  {selectedIds.includes(item.id) && <span className="picked-check">✓</span>}
                </button>
              ))}
            </div>
            {items.length === 0 && <p className="inline-hint">Ajoute des pièces dans ton dressing avant de planifier.</p>}
            <div className="button-row">
              <button type="button" className="button button-primary" disabled={saving || selectedIds.length === 0} onClick={() => void save()}>
                {saving ? "Enregistrement…" : `Valider la tenue (${selectedIds.length})`}
              </button>
              <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Annuler</button>
            </div>
          </>
        )}
      </section>
    </div>
  </>;
}

function ProfileView({ user, profile, busy, onAvatar, onNavigate }: {
  user: CurrentUser | null;
  profile: StyleProfile | null;
  busy: string;
  onAvatar: (file: File) => Promise<void>;
  onNavigate: (screen: Screen) => void;
}) {
  const maxCount = profile ? Math.max(1, ...Object.values(profile.category_counts)) : 1;
  return <>
    <PageHeading title="Mon profil de style" subtitle="Découvre ce que ton dressing révèle de tes préférences, tes couleurs signature et ton archétype vestimentaire." />
    <div className="profile-layout modern-profile-layout">
      {/* Profile Card */}
      <section className="content-card profile-card">
        <div className="profile-cover">
          <span className="profile-sun">☀</span>
          <span className="profile-flower">✿</span>
          <span className="profile-arch" />
        </div>
        <div className="profile-person">
          <Avatar user={user} size="large" />
          <div>
            <h2>{user?.full_name || "Mon espace DressMe"}</h2>
            <p>{user?.email}</p>
          </div>
          <label className={`button button-outline file-button${busy === "avatar" ? " is-disabled" : ""}`}>
            {busy === "avatar" ? "Envoi…" : user?.avatar_photo_url ? "Changer ma photo" : "Ajouter une photo"}
            <input type="file" accept="image/*" disabled={busy === "avatar"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onAvatar(file); event.target.value = ""; }} />
          </label>
        </div>
        <div className="profile-stat-line">
          <strong>{profile?.wardrobe_size ?? 0}</strong>
          <span>pièces enregistrées au total</span>
        </div>
        {profile?.narrative && <blockquote className="style-narrative">“{profile.narrative}”</blockquote>}
      </section>

      {/* Category breakdown & Color Palette */}
      <section className="content-card profile-analysis-card">
        <div className="card-heading">
          <div>
            <span className="eyebrow">ADN & SIGNATURE VESTIMENTAIRE</span>
            <h3>Répartition de ta garde-robe</h3>
          </div>
        </div>

        {profile && Object.entries(profile.category_counts).length > 0 ? (
          <div className="category-bars">
            {Object.entries(profile.category_counts).sort((a, b) => b[1] - a[1]).map(([name, count]) => (
              <div className="category-bar-row" key={name}>
                <span>{categoryLabel(name)}</span>
                <div><i style={{ width: `${(count / maxCount) * 100}%` }} /></div>
                <b>{count} ({Math.round((count / (profile.wardrobe_size || 1)) * 100)}%)</b>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon="◈" title="Ton profil se construit" text="Ajoute des vêtements dans ton dressing pour révéler tes statistiques." onAction={() => onNavigate("wardrobe")} action="Ouvrir le dressing" />
        )}

        <div className="preference-block">
          <h4>Couleurs dominantes</h4>
          <div className="style-chips">
            {profile?.favorite_colors.length ? profile.favorite_colors.map((color) => (
              <span key={color} className="color-chip-pill">● {color}</span>
            )) : <small>Ajoute des pièces pour découvrir ta palette signature.</small>}
          </div>

          <h4 style={{ marginTop: "16px" }}>Styles favoris</h4>
          <div className="style-chips">
            {profile?.favorite_styles.length ? profile.favorite_styles.map((style) => (
              <span key={style} className="style-chip-pill">✧ {style}</span>
            )) : <small>Ton style se découvrira au fil de tes ajouts.</small>}
          </div>
        </div>
      </section>
    </div>

    {/* Quick Access */}
    <section className="quick-actions profile-quick">
      <div><span className="eyebrow">CONTINUER L'EXPÉRIENCE</span><h3>Tes outils style</h3></div>
      <button type="button" onClick={() => onNavigate("calendar")}><span>▦</span><b>Calendrier</b><small>Planifier un look</small><i>→</i></button>
      <button type="button" onClick={() => onNavigate("packing")}><span>▣</span><b>Ma valise</b><small>Préparer un voyage</small><i>→</i></button>
      <button type="button" onClick={() => onNavigate("tryon")}><span>✦</span><b>Essayage virtuel</b><small>Tester une pièce</small><i>→</i></button>
    </section>
  </>;
}

function PackingView({ lists, busy, onCreate, onToggle, onDelete }: {
  lists: PackingList[];
  busy: string;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onToggle: (list: PackingList, id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [filterState, setFilterState] = useState<Record<string, "all" | "remaining" | "packed">>({});

  return <>
    <PageHeading title="Ma valise intelligente" subtitle="Une sélection optimisée selon ta destination, la météo et la durée de ton escapade." />

    <form className="content-card packing-form modern-packing-form" onSubmit={(event) => void onCreate(event)}>
      <div className="card-heading">
        <div>
          <span className="eyebrow">NOUVEAU VOYAGE</span>
          <h3>Où pars-tu prochainement ?</h3>
        </div>
        <span className="form-sparkle">✈</span>
      </div>
      <div className="form-grid">
        <label className="field">
          <span>Destination</span>
          <input name="destination" required placeholder="Ex. Djerba, Paris, Rome..." />
        </label>
        <label className="field">
          <span>Durée (jours)</span>
          <input name="duration" type="number" min="1" max="90" defaultValue="4" required />
        </label>
        <label className="field">
          <span>Type de séjour</span>
          <select name="tripType" defaultValue="plage">
            <option value="plage">🏖️ Plage & Détente</option>
            <option value="business">💼 Professionnel & Conférence</option>
            <option value="tourisme">🏛️ Tourisme & Découverte</option>
            <option value="fête">🎉 Fête & Événement</option>
          </select>
        </label>
        <label className="field">
          <span>Date de départ (facultatif)</span>
          <input name="startDate" type="date" />
        </label>
      </div>
      <div className="form-submit-row">
        <p>L'IA sélectionnera les pièces les plus polyvalentes et adaptées de ton dressing.</p>
        <button className="button button-primary" disabled={busy === "packing-create"}>
          {busy === "packing-create" ? "Préparation de la valise…" : "🎒 Générer ma valise →"}
        </button>
      </div>
    </form>

    {lists.length === 0 ? (
      <EmptyState icon="▣" title="Aucun voyage prévu pour l'instant" text="Crée une liste de valise pour préparer ta prochaine escapade en quelques secondes." />
    ) : (
      <div className="packing-list-grid">
        {lists.map((list) => {
          const currentFilter = filterState[list.id] ?? "all";
          const totalCount = list.items.length;
          const packedCount = list.checked_item_ids.length;
          const percent = totalCount ? Math.round((packedCount / totalCount) * 100) : 0;
          const isComplete = totalCount > 0 && packedCount === totalCount;

          const displayItems = list.items.filter((item) => {
            const isPacked = list.checked_item_ids.includes(item.id);
            if (currentFilter === "remaining") return !isPacked;
            if (currentFilter === "packed") return isPacked;
            return true;
          });

          return (
            <article className="content-card packing-list-card modern-packing-card" key={list.id}>
              <div className="packing-list-heading">
                <div>
                  <span className="category-pill">{list.duration_days} jours · {categoryLabel(list.trip_type)}{list.season && ` · ${itemSeasonLabel(list.season)}`}</span>
                  <h3>{list.destination}</h3>
                </div>
                <button className="remove-link" type="button" onClick={() => void onDelete(list.id)}>Supprimer la liste</button>
              </div>

              {/* Progress */}
              <div className="packing-progress">
                <div className="packing-progress-labels">
                  <span><b>{packedCount}</b> / {totalCount} pièces prêtes</span>
                  <span className="packing-percent-tag">{percent}%</span>
                </div>
                <i><b style={{ width: `${percent}%` }} /></i>
                {isComplete && <span className="packing-complete-badge">✨ Valise 100% prête, bon voyage !</span>}
              </div>

              {/* Checklist Filter Tabs */}
              <div className="packing-filter-tabs">
                <button
                  type="button"
                  className={currentFilter === "all" ? "active" : ""}
                  onClick={() => setFilterState((prev) => ({ ...prev, [list.id]: "all" }))}
                >
                  Toutes ({totalCount})
                </button>
                <button
                  type="button"
                  className={currentFilter === "remaining" ? "active" : ""}
                  onClick={() => setFilterState((prev) => ({ ...prev, [list.id]: "remaining" }))}
                >
                  À mettre ({totalCount - packedCount})
                </button>
                <button
                  type="button"
                  className={currentFilter === "packed" ? "active" : ""}
                  onClick={() => setFilterState((prev) => ({ ...prev, [list.id]: "packed" }))}
                >
                  Emballées ({packedCount})
                </button>
              </div>

              {/* Items List */}
              <div className="packing-items">
                {displayItems.map((item) => {
                  const checked = list.checked_item_ids.includes(item.id);
                  return (
                    <label className={`packing-item${checked ? " packed" : ""}`} key={item.id}>
                      <input type="checkbox" checked={checked} onChange={() => void onToggle(list, item.id)} />
                      <img src={item.image_url} alt="" />
                      <span>{categoryLabel(item.category)}</span>
                      {checked && <small className="item-packed-tag">Prêt ✓</small>}
                    </label>
                  );
                })}
              </div>
              {list.items.length === 0 && <p className="inline-hint">Ajoute plus de pièces à ton dressing pour enrichir cette liste.</p>}
            </article>
          );
        })}
      </div>
    )}
  </>;
}

const PURCHASE_CATEGORY_LABELS: Record<string, string> = {
  haut: "Haut", bas: "Bas", robe: "Robe", veste: "Veste",
  chaussures: "Chaussures", sac: "Sac", accessoire: "Accessoire",
};

const PURCHASE_VERDICTS: Record<PurchaseResult["verdict"], string> = {
  recommended: "Recommandé",
  think_twice: "À réfléchir",
  not_recommended: "Déconseillé",
};

function openStorePage(url?: string | null) {
  if (url) window.open(url, "_blank", "noopener,noreferrer");
}

function PurchaseView({ result, busy, onCheck, onRestoreResult }: {
  result: PurchaseResult | null;
  busy: string;
  onCheck: (file: File) => Promise<void>;
  onRestoreResult: (result: PurchaseResult) => void;
}) {
  const [history, setHistory] = useState<PurchaseHistoryItem[]>([]);
  const [wishlist, setWishlist] = useState<WishlistEntry[]>([]);
  const [shopTab, setShopTab] = useState<"history" | "wishlist">("history");
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);
  const brands = result?.tunisian_brands ?? [];
  const savedKeys = useMemo(() => new Set(wishlist.map((item) => item.item_key)), [wishlist]);

  const refreshHistory = () => { getPurchaseHistory().then(setHistory).catch(() => {}); };
  const refreshWishlist = () => { getWishlist().then(setWishlist).catch(() => {}); };

  useEffect(() => { refreshHistory(); refreshWishlist(); }, []);
  useEffect(() => { refreshHistory(); }, [result]);

  const verdictText =
    result?.verdict === "recommended"
      ? "Coup de cœur : Cette pièce s’accorde à merveille avec ton dressing !"
      : result?.verdict === "think_twice"
      ? "À réfléchir : Tu possèdes déjà des pièces très similaires."
      : "Achat risqué : Cette pièce sera difficile à associer avec ton style actuel.";

  async function toggleSave(product: CatalogAlternative) {
    if (!product.item_key) return;
    const key = product.item_key;
    if (savedKeys.has(key)) {
      setWishlist((current) => current.filter((item) => item.item_key !== key));
      await removeFromWishlist(key).catch(refreshWishlist);
    } else {
      await addToWishlist(key).then((entry) => {
        setWishlist((current) => [entry, ...current.filter((item) => item.item_key !== key)]);
      }).catch(refreshWishlist);
    }
  }

  function openHistory(item: PurchaseHistoryItem) {
    setActiveHistoryId(item.id);
    onRestoreResult(item.result);
  }

  function removeHistory(item: PurchaseHistoryItem) {
    setHistory((current) => current.filter((entry) => entry.id !== item.id));
    if (item.id === activeHistoryId) setActiveHistoryId(null);
    deleteHistoryEntry(item.id).catch(refreshHistory);
  }

  function ProductCard({ product }: { product: CatalogAlternative }) {
    const saved = product.item_key != null && savedKeys.has(product.item_key);
    const href = product.product_url || product.store_url;
    return (
      <article className="alternative-card">
        {product.image_url ? <img src={product.image_url} alt={product.name} /> : <span className="alternative-placeholder">✧</span>}
        <div>
          <b>{product.name}</b>
          <small>{[product.brand, product.category].filter(Boolean).join(" · ")}</small>
          <strong>{formatTnd(product.price) ?? "Prix n.c."}</strong>
        </div>
        <div className="purchase-card-actions">
          {product.item_key && (
            <button type="button" className={`wish-heart${saved ? " is-saved" : ""}`} onClick={() => void toggleSave(product)} title={saved ? "Retirer de la wishlist" : "Ajouter à la wishlist"}>
              {saved ? "♥" : "♡"}
            </button>
          )}
          {href && (
            <a className="store-link" href={href} target="_blank" rel="noreferrer">
              {product.buyable ? "Acheter" : "Voir"} ↗
            </a>
          )}
        </div>
      </article>
    );
  }

  return <>
    <PageHeading title="J’achète ou pas ?" subtitle="Un doute en boutique ou en ligne ? Téléverse la photo d'un vêtement pour vérifier sa compatibilité avant d'acheter." />

    <div className="purchase-layout modern-purchase-layout">
      <section className="content-card purchase-card">
        <span className="eyebrow">CONSEILLER D'ACHAT IA</span>
        <h2>Une pièce te fait envie ?</h2>
        <p>Prends une photo ou fais une capture d'écran de l'article convoité. DressMe analyse instantanément sa couleur, sa coupe et vérifie son harmonie avec l'ensemble de ton dressing.</p>

        <label className={`upload-drop${busy === "purchase" ? " is-loading" : ""}`}>
          <input
            type="file"
            accept="image/*"
            disabled={busy === "purchase"}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onCheck(file);
              event.target.value = "";
            }}
          />
          <span className="upload-icon">{busy === "purchase" ? "◌" : "📷"}</span>
          <strong>{busy === "purchase" ? "Analyse FashionCLIP & RAG en cours…" : "Choisir ou déposer la photo du vêtement"}</strong>
          <small>JPG, PNG, WebP · Analyse instantanée et privée</small>
        </label>
        <p className="privacy-note">🔒 Analyse 100% confidentielle liée à ton dressing.</p>
      </section>

      <section className="content-card purchase-result modern-purchase-result">
        {result ? (
          <>
            <div className={`verdict-banner verdict-${result.verdict}`}>
              <span className="verdict-icon">
                {result.verdict === "recommended" ? "✓" : result.verdict === "think_twice" ? "⚠️" : "×"}
              </span>
              <div>
                <span className="eyebrow">VERDICT DU STYLISTE</span>
                <h2>{verdictText}</h2>
              </div>
            </div>

            <div className="compatibility-meter modern-compat-meter">
              <div className="meter-header">
                <span>Score d’harmonie avec ton dressing</span>
                <b>{result.score ?? Math.round(result.compatibility_score * 100)}</b>
              </div>
              <i className="meter-track">
                <b
                  className={`meter-bar ${result.verdict}`}
                  style={{ width: `${Math.min(100, Math.max(0, result.compatibility_score * 100))}%` }}
                />
              </i>
            </div>

            <div className="verdict-explanation-box">
              <h4>✦ Analyse du styliste :</h4>
              <p className="verdict-explanation">{result.explanation}</p>
            </div>

            {result.catalog_alternatives.length > 0 && (
              <div className="alternatives-section">
                <h3>Alternatives en Tunisie</h3>
                <p className="section-hint">Trouvées par ressemblance visuelle (FashionCLIP) — ouvre la page produit de la marque.</p>
                <div className="alternatives">
                  {result.catalog_alternatives.map((alternative, index) => (
                    <ProductCard key={alternative.item_key ?? `${alternative.name}-${index}`} product={alternative} />
                  ))}
                </div>
              </div>
            )}

            {brands.length > 0 && (
              <div className="brands-section">
                <h3>Marques tunisiennes pour toi</h3>
                <p className="section-hint">Classées par affinité visuelle avec cet article et ton style.</p>
                {brands.map((brand, rank) => {
                  const best = brands[0].affinity || 1;
                  const match = Math.round((brand.affinity / best) * 100);
                  return (
                    <article className="brand-card" key={brand.name}>
                      <div className="brand-card-top">
                        <span className={`brand-rank${rank === 0 ? " is-first" : ""}`}>{rank + 1}</span>
                        <div>
                          <b>{brand.name}</b>
                          <small>
                            {brand.product_count} articles similaires
                            {brand.price_min != null && brand.price_max != null
                              ? ` · ${formatTnd(brand.price_min)} – ${formatTnd(brand.price_max)}`
                              : ""}
                          </small>
                          <i className="brand-affinity"><b style={{ width: `${match}%` }} /></i>
                        </div>
                        {brand.website && (
                          <a className="store-link" href={brand.website} target="_blank" rel="noreferrer">Site ↗</a>
                        )}
                      </div>
                      {brand.showcase.length > 0 && (
                        <div className="brand-showcase">
                          {brand.showcase.map((product, index) => (
                            <button
                              type="button"
                              className="showcase-item"
                              key={product.item_key ?? `${product.name}-${index}`}
                              onClick={() => openStorePage(product.product_url || product.store_url || brand.website)}
                            >
                              {product.image_url ? <img src={product.image_url} alt="" /> : <span>✧</span>}
                              <b>{product.name}</b>
                              <small>{formatTnd(product.price) ?? "Prix n.c."}</small>
                            </button>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <EmptyState
            icon="♡"
            title="En attente d'une pièce à analyser"
            text="Téléverse la photo d'un vêtement à gauche pour découvrir le score de compatibilité, les alternatives tunisiennes et nos conseils d'achat."
          />
        )}
      </section>
    </div>

    <section className="content-card shopping-space">
      <div className="shopping-space-head">
        <div>
          <span className="eyebrow">MON ESPACE SHOPPING</span>
          <h2>Historique et wishlist</h2>
          <p>Tes analyses et tes coups de cœur, suivis en direct.</p>
        </div>
        <div className="shopping-stats">
          <span><b>{history.length}</b> analyses</span>
          <span><b>{wishlist.length}</b> wishlist</span>
        </div>
      </div>
      <div className="shopping-tabs">
        <button type="button" className={shopTab === "history" ? "active" : ""} onClick={() => setShopTab("history")}>
          Historique ({history.length})
        </button>
        <button type="button" className={shopTab === "wishlist" ? "active" : ""} onClick={() => setShopTab("wishlist")}>
          Wishlist ({wishlist.length})
        </button>
      </div>
      {shopTab === "history" ? (
        history.length === 0 ? (
          <p className="inline-hint">Chaque article analysé est enregistré ici, pour le revoir en un geste.</p>
        ) : (
          <div className="shopping-list">
            {history.map((item) => (
              <article className={`shopping-row${item.id === activeHistoryId ? " is-active" : ""}`} key={item.id}>
                <button type="button" className="shopping-row-main" onClick={() => openHistory(item)}>
                  <img src={item.image_url} alt="" />
                  <div>
                    <b>{PURCHASE_CATEGORY_LABELS[item.category] ?? item.category}{item.color ? ` · ${item.color}` : ""}</b>
                    <small className={`verdict-tag verdict-${item.verdict}`}>{PURCHASE_VERDICTS[item.verdict]} · {item.score}</small>
                  </div>
                </button>
                <button type="button" className="text-button" onClick={() => removeHistory(item)}>Supprimer</button>
              </article>
            ))}
            <button type="button" className="text-button danger" onClick={() => { setHistory([]); setActiveHistoryId(null); clearPurchaseHistory().catch(refreshHistory); }}>
              Effacer tout l'historique
            </button>
          </div>
        )
      ) : wishlist.length === 0 ? (
        <p className="inline-hint">Touche ♡ sur une alternative : on suit son prix et on ouvre la page de la marque.</p>
      ) : (
        <div className="shopping-list">
          {wishlist.map((item) => (
            <article className="shopping-row" key={item.item_key}>
              <button type="button" className="shopping-row-main" onClick={() => openStorePage(item.product_url || item.store_url)}>
                {item.image_url ? <img src={item.image_url} alt="" /> : <span className="alternative-placeholder">♡</span>}
                <div>
                  <b>{item.name}</b>
                  <small>{[item.brand, formatTnd(item.live_price ?? item.saved_price)].filter(Boolean).join(" · ")}</small>
                </div>
              </button>
              <button type="button" className="text-button" onClick={() => { setWishlist((current) => current.filter((entry) => entry.item_key !== item.item_key)); removeFromWishlist(item.item_key).catch(refreshWishlist); }}>
                Retirer
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  </>;
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

function TryOnView({
  user,
  items,
  selectedIds,
  result,
  busy,
  onToggleSelect,
  onClearSelect,
  onSelectPresetAvatar,
  onAvatar,
  onTryOn,
}: {
  user: CurrentUser | null;
  items: ClothingItem[];
  selectedIds: string[];
  result: string;
  busy: string;
  onToggleSelect: (id: string) => void;
  onClearSelect: () => void;
  onSelectPresetAvatar: (url: string) => Promise<void>;
  onAvatar: (file: File) => Promise<void>;
  onTryOn: () => Promise<void>;
}) {
  const [categoryFilter, setCategoryFilter] = useState("all");

  const categories = [
    { id: "all", label: "Toutes les pièces" },
    { id: "haut", label: "Hauts" },
    { id: "bas", label: "Bas" },
    { id: "robe", label: "Robes" },
    { id: "veste", label: "Vestes" },
  ];

  const filteredItems =
    categoryFilter === "all"
      ? items
      : items.filter((it) => it.category === categoryFilter);

  const selectedPieces = items.filter((it) => selectedIds.includes(it.id));

  // Determine active preset (if any)
  const activePreset = PRESET_AVATARS.find((preset) => {
    if (!user?.avatar_photo_url) return false;
    return (
      user.avatar_photo_url.includes(preset.url) ||
      user.avatar_photo_url.includes(preset.id)
    );
  });

  return (
    <>
      <PageHeading
        title="Studio d’Essayage Virtuel ✨"
        subtitle="Choisis un mannequin de référence ou ta photo, sélectionne une ou plusieurs pièces et visualise ta tenue en haute définition."
      />

      <div className="tryon-studio-layout">
        {/* ================= ÉTAPE 1 : MANNEQUIN & AVATAR ================= */}
        <section className="tryon-card-premium">
          <span className="tryon-step-badge">Étape 01 · Mannequin</span>
          <h3 className="tryon-step-title">Ton Mannequin de Référence</h3>
          <p className="tryon-step-desc">
            Sélectionne l’un des 3 mannequins ci-dessous en un clic, ou téléverse ta propre photo en pied.
          </p>

          <div className="tryon-presets-title">
            <span>Mannequins d’Exemple</span>
            <span style={{ fontSize: "11px", color: "var(--rose)", fontWeight: 700 }}>
              3 modèles prêts
            </span>
          </div>

          <div className="tryon-presets-grid">
            {PRESET_AVATARS.map((preset) => {
              const isSelected =
                activePreset?.id === preset.id ||
                user?.avatar_photo_url?.includes(preset.url);
              return (
                <button
                  type="button"
                  key={preset.id}
                  className={`tryon-preset-card${isSelected ? " is-active" : ""}`}
                  onClick={() => void onSelectPresetAvatar(preset.url)}
                  disabled={busy === "avatar"}
                  title={`Choisir ${preset.name}`}
                >
                  <div className="tryon-preset-img-wrap">
                    <img src={preset.url} alt={preset.name} />
                  </div>
                  <span className="tryon-preset-name">{preset.name}</span>
                  <span className="tryon-preset-tag">{preset.tag}</span>
                  {isSelected && <span className="tryon-preset-check">✓</span>}
                </button>
              );
            })}
          </div>

          {/* Active Avatar Full Preview */}
          <div className="tryon-active-preview">
            {user?.avatar_photo_url ? (
              <>
                <img src={user.avatar_photo_url} alt="Photo du modèle actif" />
                <span className="tryon-active-badge">
                  {activePreset
                    ? `✦ ${activePreset.name} sélectionné`
                    : "✦ Photo personnelle active"}
                </span>
              </>
            ) : (
              <div style={{ padding: "30px 15px", textAlign: "center", color: "#64748b" }}>
                <span style={{ fontSize: "32px", display: "block", marginBottom: "6px" }}>👤</span>
                <strong style={{ fontSize: "13px", color: "var(--navy)" }}>Aucun mannequin sélectionné</strong>
                <p style={{ fontSize: "11px", margin: "4px 0 0" }}>
                  Clique sur un modèle ci-dessus pour l’activer.
                </p>
              </div>
            )}
          </div>

          {/* Import Custom Photo */}
          <label className="tryon-upload-btn">
            <span>{busy === "avatar" ? "⏳ Envoi en cours…" : "📷 Importer ma propre photo en pied"}</span>
            <input
              type="file"
              accept="image/*"
              disabled={busy === "avatar"}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void onAvatar(file);
                event.target.value = "";
              }}
            />
          </label>
        </section>

        {/* ================= ÉTAPE 2 : SÉLECTION MULTI-VÊTEMENTS ================= */}
        <section className="tryon-card-premium">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <span className="tryon-step-badge">Étape 02 · Dressing</span>
              <h3 className="tryon-step-title">Compose ta Tenue</h3>
              <p className="tryon-step-desc">
                Tu peux choisir <strong>plus d’un vêtement</strong> (ex: Haut + Bas, ou Veste + Robe) pour un look complet.
              </p>
            </div>
            {selectedIds.length > 0 && (
              <button
                type="button"
                className="text-button"
                style={{ fontSize: "12px", color: "var(--rose)", fontWeight: 700, padding: "4px 8px" }}
                onClick={onClearSelect}
              >
                Tout désélectionner ({selectedIds.length})
              </button>
            )}
          </div>

          {/* Category Filter Pills */}
          <div className="tryon-cat-filter">
            {categories.map((cat) => (
              <button
                key={cat.id}
                type="button"
                className={`tryon-pill${categoryFilter === cat.id ? " is-active" : ""}`}
                onClick={() => setCategoryFilter(cat.id)}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Garments Grid */}
          {filteredItems.length > 0 ? (
            <div className="tryon-garments-grid">
              {filteredItems.map((item) => {
                const isSelected = selectedIds.includes(item.id);
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`tryon-garment-card${isSelected ? " is-selected" : ""}`}
                    aria-pressed={isSelected}
                    onClick={() => onToggleSelect(item.id)}
                  >
                    <img className="tryon-garment-img" src={item.image_url} alt={categoryLabel(item.category)} />
                    <div className="tryon-garment-footer">
                      <span className="tryon-garment-cat">{categoryLabel(item.category)}</span>
                      {item.colors && item.colors[0] && (
                        <span style={{ fontSize: "9px", color: "#94a3b8" }}>{item.colors[0]}</span>
                      )}
                    </div>
                    {isSelected && <span className="tryon-garment-check">✓</span>}
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon="◈"
              title="Aucune pièce trouvée"
              text="Ajoute des pièces dans ton dressing pour pouvoir les essayer."
            />
          )}

          {/* Selected Pieces Dock */}
          {selectedPieces.length > 0 && (
            <div className="tryon-selection-dock">
              <div style={{ width: "100%" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--navy)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  Tenue sélectionnée ({selectedPieces.length} {selectedPieces.length === 1 ? "pièce" : "pièces"}) :
                </span>
                <div className="tryon-selected-pieces" style={{ marginTop: "6px" }}>
                  {selectedPieces.map((piece) => (
                    <div key={piece.id} className="tryon-piece-chip">
                      <img src={piece.image_url} alt="" />
                      <span>{categoryLabel(piece.category)}</span>
                      <button
                        type="button"
                        aria-label="Retirer cette pièce"
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleSelect(piece.id);
                        }}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Action Button */}
          <button
            type="button"
            className="tryon-cta-btn"
            disabled={!user?.avatar_photo_url || selectedIds.length === 0 || busy === "tryon"}
            onClick={() => void onTryOn()}
          >
            {busy === "tryon" ? (
              <>
                <span className="tryon-spinner" />
                <span>Génération du look en cours…</span>
              </>
            ) : selectedIds.length > 1 ? (
              <>
                <span>✨</span>
                <span>Essayer la tenue complète ({selectedIds.length} pièces)</span>
              </>
            ) : selectedIds.length === 1 ? (
              <>
                <span>✨</span>
                <span>Essayer cette pièce</span>
              </>
            ) : (
              <span>Sélectionne au moins une pièce</span>
            )}
          </button>

          {!user?.avatar_photo_url && (
            <p className="inline-hint" style={{ marginTop: "10px", textAlign: "center" }}>
              👈 Choisis d’abord un mannequin à gauche pour démarrer.
            </p>
          )}

          {busy === "tryon" && (
            <div className="tryon-generating-state">
              <span className="tryon-spinner" />
              <div>
                <strong style={{ fontSize: "13px", color: "var(--rose)" }}>L’IA habille ton mannequin…</strong>
                <p style={{ margin: "2px 0 0", fontSize: "11px", color: "#64748b" }}>
                  Génération haute définition en cours. Cela prend généralement entre 30 et 60 secondes.
                </p>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* ================= ÉTAPE 3 : RÉSULTAT DU LOOK ================= */}
      {result && (
        <section className="tryon-showcase" id="tryon-result-section">
          <span className="tryon-step-badge">Étape 03 · Rendu Haute Couture</span>
          <h2 style={{ fontFamily: '"Playfair Display", Georgia, serif', fontSize: "28px", color: "var(--navy)", margin: "8px 0 6px" }}>
            Voilà ton look généré ✨
          </h2>
          <p style={{ fontSize: "14px", color: "#64748b", margin: "0 auto 16px", maxWidth: "540px" }}>
            Voici le résultat de l’essayage virtuel combinant ton modèle et les pièces sélectionnées.
          </p>

          <img className="tryon-showcase-img" src={result} alt="Résultat de l’essayage virtuel" />

          <div className="tryon-showcase-actions">
            <a
              href={result}
              target="_blank"
              rel="noopener noreferrer"
              className="button button-primary"
              style={{ padding: "11px 22px", textDecoration: "none" }}
              download="mon-look-dressme.jpg"
            >
              📥 Enregistrer / Ouvrir l’image
            </a>
          </div>
        </section>
      )}
    </>
  );
}

/* ========================================================
   MODAL CONFIRMATION : DONNER OU SUPPRIMER ?
   ======================================================== */
function DonationPromptModal({
  item,
  onDonate,
  onDeletePermanent,
  onCancel,
}: {
  item: ClothingItem;
  onDonate: (item: ClothingItem) => Promise<void>;
  onDeletePermanent: (item: ClothingItem) => Promise<void>;
  onCancel: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="donation-prompt-modal" onClick={(e) => e.stopPropagation()}>
        <div className="donation-prompt-header">
          <div className="donation-prompt-icon">🎁</div>
          <div>
            <span className="eyebrow">SECONDE VIE & SOLIDARITÉ</span>
            <h2>Que souhaites-tu faire de cette pièce&nbsp;?</h2>
          </div>
          <button type="button" className="modal-close" onClick={onCancel} aria-label="Fermer">✕</button>
        </div>

        <div className="donation-prompt-body">
          <div className="donation-prompt-item-preview">
            <img src={item.image_url} alt={categoryLabel(item.category)} />
            <div>
              <strong>{categoryLabel(item.category)}</strong>
              <small>{itemSeasonLabel(item.season) ?? "Toutes saisons"}</small>
            </div>
          </div>

          <p className="donation-prompt-intro">
            Plutôt que de simplement l’effacer, tu peux offrir une seconde vie utile à ce vêtement en le mettant en donation pour des associations caritatives en Tunisie.
          </p>

          <div className="donation-prompt-choices">
            {/* Option A : Donation (Recommandé) */}
            <div className="donation-choice-box recommended">
              <div className="donation-choice-badge">✦ RECOMMANDÉ & ÉCO-RESPONSABLE</div>
              <div className="donation-choice-header">
                <span className="choice-icon">🎁</span>
                <div>
                  <h4>Transférer vers mes dons</h4>
                  <p>
                    Cette pièce sera retirée de ton dressing et archivée dans ta page <b>« Dons & Seconde vie »</b>. Tu pourras y trouver des associations partenaires proches pour la déposer.
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="button button-primary donation-action-btn"
                onClick={() => void onDonate(item)}
              >
                <span>🎁</span> Mettre en donation
              </button>
            </div>

            {/* Option B : Suppression définitive */}
            <div className="donation-choice-box secondary">
              <div className="donation-choice-header">
                <span className="choice-icon">🗑️</span>
                <div>
                  <h4>Supprimer définitivement</h4>
                  <p>
                    Efface irrévocablement ce vêtement de ton dressing et de la base de données.
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="button button-ghost danger-ghost-btn"
                onClick={() => void onDeletePermanent(item)}
              >
                Supprimer sans donner
              </button>
            </div>
          </div>
        </div>

        <div className="donation-prompt-footer">
          <button type="button" className="button button-outline" onClick={onCancel}>
            Annuler et conserver dans mon dressing
          </button>
        </div>
      </div>
    </div>
  );
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

function DonationView({
  donations,
  onMarkDonated,
  onRestoreToWardrobe,
  onRemoveDonation,
  onUpdateCondition,
  onNavigate,
}: {
  donations: DonationItem[];
  onMarkDonated: (donationId: string, orgName?: string) => void;
  onRestoreToWardrobe: (donation: DonationItem) => Promise<void>;
  onRemoveDonation: (donationId: string) => void;
  onUpdateCondition: (donationId: string, condition: "comme_neuf" | "bon_etat" | "a_recycler") => void;
  onNavigate: (screen: Screen) => void;
}) {
  const [activeTab, setActiveTab] = useState<"all" | "pending" | "donated">("all");
  const [selectedCity, setSelectedCity] = useState<string>("Toutes");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDonationForOrg, setSelectedDonationForOrg] = useState<string | null>(null);

  const pendingCount = donations.filter((d) => d.status === "pending").length;
  const donatedCount = donations.filter((d) => d.status === "donated").length;
  const totalCount = donations.length;

  // Ecological impact metrics
  const waterSavedLiters = totalCount * 2700;
  const co2SavedKg = Math.round(totalCount * 12);

  const filteredDonations = donations.filter((d) => {
    if (activeTab === "pending") return d.status === "pending";
    if (activeTab === "donated") return d.status === "donated";
    return true;
  });

  const CITIES_LIST = ["Toutes", "Tunis", "Sousse", "Sfax", "Nabeul", "Bizerte", "Djerba"];

  const filteredOrgs = TUNISIAN_DONATION_ORGS.filter((org) => {
    if (selectedCity !== "Toutes" && !org.cities.includes(selectedCity)) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = org.name.toLowerCase().includes(q);
      const matchSub = org.subtitle.toLowerCase().includes(q);
      const matchAccepted = org.accepted.some((a) => a.toLowerCase().includes(q));
      const matchCities = org.cities.some((c) => c.toLowerCase().includes(q));
      if (!matchName && !matchSub && !matchAccepted && !matchCities) return false;
    }
    return true;
  });

  return (
    <>
      <PageHeading
        title="Dons & Seconde vie"
        subtitle="Donne une deuxième vie à tes vêtements oubliés, réduis ton empreinte textile et soutiens des associations caritatives en Tunisie."
      />

      {/* ================= ÉCO-IMPACT & STATS ================= */}
      <section className="donation-impact-banner">
        <div className="donation-impact-copy">
          <span className="eyebrow">MODE CIRCULAIRE & SOLIDARITÉ</span>
          <h2>Ton impact positif pour la planète et les autres</h2>
          <p>
            Chaque vêtement réemployé évite des milliers de litres d'eau de fabrication et apporte chaleur et dignité à une personne dans le besoin.
          </p>
        </div>

        <div className="donation-impact-grid">
          <div className="donation-stat-card">
            <span className="stat-icon">🎁</span>
            <strong>{pendingCount}</strong>
            <small>Pièce{pendingCount > 1 ? "s" : ""} prête{pendingCount > 1 ? "s" : ""} à donner</small>
          </div>
          <div className="donation-stat-card">
            <span className="stat-icon gold">✨</span>
            <strong>{donatedCount}</strong>
            <small>Pièce{donatedCount > 1 ? "s" : ""} déjà donnée{donatedCount > 1 ? "s" : ""}</small>
          </div>
          <div className="donation-stat-card">
            <span className="stat-icon blue">💧</span>
            <strong>{waterSavedLiters.toLocaleString("fr-FR")} L</strong>
            <small>Eau douce préservée</small>
          </div>
          <div className="donation-stat-card">
            <span className="stat-icon green">🌍</span>
            <strong>{co2SavedKg} kg</strong>
            <small>Émissions CO₂ évitées</small>
          </div>
        </div>
      </section>

      {/* ================= SECTION 1 : MES PIÈCES À DONNER ================= */}
      <section className="content-card modern-packing-card" style={{ marginBottom: "26px" }}>
        <div className="card-heading">
          <div>
            <span className="eyebrow">MON TROUSSEAU SOLIDAIRE</span>
            <h3>Mes vêtements en attente de don ({donations.length})</h3>
          </div>
          <button type="button" className="button button-outline" onClick={() => onNavigate("wardrobe")}>
            ＋ Ajouter depuis mon dressing
          </button>
        </div>

        {/* Filter Tabs */}
        <div className="packing-filter-tabs">
          <button
            type="button"
            className={activeTab === "all" ? "active" : ""}
            onClick={() => setActiveTab("all")}
          >
            Toutes ({totalCount})
          </button>
          <button
            type="button"
            className={activeTab === "pending" ? "active" : ""}
            onClick={() => setActiveTab("pending")}
          >
            En attente ({pendingCount})
          </button>
          <button
            type="button"
            className={activeTab === "donated" ? "active" : ""}
            onClick={() => setActiveTab("donated")}
          >
            Données avec succès ({donatedCount})
          </button>
        </div>

        {filteredDonations.length === 0 ? (
          <EmptyState
            icon="🎁"
            title={activeTab === "donated" ? "Aucune pièce marquée comme donnée" : "Ta boîte de dons est vide"}
            text={
              activeTab === "donated"
                ? "Marque tes pièces comme 'Données' une fois déposées à l'association de ton choix !"
                : "Lorsque tu retires une pièce de ton dressing, sélectionne 'Mettre en donation' pour la retrouver ici et lui trouver une destination solidaire."
            }
            action={activeTab !== "donated" ? "Explorer mon dressing" : undefined}
            onAction={activeTab !== "donated" ? () => onNavigate("wardrobe") : undefined}
          />
        ) : (
          <div className="donations-grid">
            {filteredDonations.map((d) => {
              const isDonated = d.status === "donated";
              return (
                <article key={d.id} className={`donation-card ${isDonated ? "is-donated" : ""}`}>
                  <div className="donation-card-photo-wrap">
                    <img src={d.item.image_url} alt={categoryLabel(d.item.category)} />
                    <span className="piece-category-tag">{categoryLabel(d.item.category)}</span>
                    {isDonated && <span className="donation-badge-overlay">✓ Donné !</span>}
                  </div>

                  <div className="donation-card-content">
                    <div className="donation-card-title-row">
                      <h4>{categoryLabel(d.item.category)}</h4>
                      <small className="donation-date-tag">
                        Ajouté le {new Date(d.addedAt).toLocaleDateString("fr-TN", { day: "numeric", month: "short" })}
                      </small>
                    </div>

                    {/* Condition Selector */}
                    <div className="donation-condition-row">
                      <label>État du vêtement :</label>
                      <select
                        value={d.condition}
                        disabled={isDonated}
                        onChange={(e) =>
                          onUpdateCondition(d.id, e.target.value as "comme_neuf" | "bon_etat" | "a_recycler")
                        }
                      >
                        <option value="comme_neuf">✨ Très bon état / Comme neuf</option>
                        <option value="bon_etat">👌 Bon état général</option>
                        <option value="a_recycler">♻️ À recycler (fibres/upcycling)</option>
                      </select>
                    </div>

                    {d.targetOrg && (
                      <p className="donation-target-tag">
                        📍 Destination : <b>{d.targetOrg}</b>
                      </p>
                    )}

                    <div className="donation-actions-row">
                      <button
                        type="button"
                        className={`button ${isDonated ? "button-ghost" : "button-primary"} mark-donated-btn`}
                        onClick={() => onMarkDonated(d.id)}
                      >
                        {isDonated ? "↩ Remettre en attente" : "✓ Marquer comme donné"}
                      </button>

                      <button
                        type="button"
                        className="button button-outline restore-btn"
                        onClick={() => void onRestoreToWardrobe(d)}
                        title="Replacer ce vêtement dans mon dressing principal"
                      >
                        Remettre au dressing
                      </button>

                      <button
                        type="button"
                        className="remove-link delete-don-btn"
                        onClick={() => onRemoveDonation(d.id)}
                        title="Retirer de la liste"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* ================= SECTION 2 : RECOMMANDATIONS D'ASSOCIATIONS ================= */}
      <section className="content-card" style={{ marginBottom: "26px" }}>
        <div className="card-heading">
          <div>
            <span className="eyebrow">POINTS DE COLLECTE & SOLIDARITÉ EN TUNISIE</span>
            <h3>Où donner tes vêtements&nbsp;? ({filteredOrgs.length} organismes)</h3>
          </div>
          <span className="form-sparkle">📍</span>
        </div>

        <p style={{ fontSize: "12.5px", color: "var(--muted)", margin: "0 0 16px" }}>
          Voici notre sélection d'organismes vérifiés et de banques vestimentaires en Tunisie. Choisis l'association la plus proche de chez toi pour y déposer tes vêtements propres.
        </p>

        {/* City Filter Chips & Search Bar */}
        <div className="orgs-toolbar">
          <div className="interactive-chips-row">
            {CITIES_LIST.map((cityName) => (
              <button
                type="button"
                key={cityName}
                className={`generator-chip ${selectedCity === cityName ? "active" : ""}`}
                onClick={() => setSelectedCity(cityName)}
              >
                <span>{cityName === "Toutes" ? "🌍" : "📍"}</span>
                <span>{cityName}</span>
              </button>
            ))}
          </div>

          <div className="search-field" style={{ maxWidth: "340px", marginTop: "10px" }}>
            <span className="search-icon">🔍</span>
            <input
              placeholder="Rechercher une association, quartier, mot-clé…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button type="button" className="search-clear-btn" onClick={() => setSearchQuery("")}>
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Organizations Grid */}
        <div className="orgs-grid">
          {filteredOrgs.map((org) => (
            <article key={org.id} className="org-card">
              <div className="org-card-top">
                <div>
                  <span className="org-badge">{org.badge}</span>
                  <h4>{org.name}</h4>
                  <small className="org-subtitle">{org.subtitle}</small>
                </div>
              </div>

              <p className="org-description">{org.description}</p>

              <div className="org-accepted-section">
                <span className="org-accepted-label">Articles acceptés :</span>
                <div className="org-accepted-chips">
                  {org.accepted.map((itemType) => (
                    <span key={itemType} className="org-accepted-pill">
                      {itemType}
                    </span>
                  ))}
                </div>
              </div>

              <div className="org-contact-box">
                <div className="contact-line">
                  <span>📍</span>
                  <strong>{org.address}</strong>
                </div>
                <div className="contact-line">
                  <span>📞</span>
                  <a href={`tel:${org.phone}`}>{org.phone}</a>
                  <span style={{ margin: "0 6px", opacity: 0.5 }}>·</span>
                  <span>✉️</span>
                  <a href={`mailto:${org.email}`}>{org.email}</a>
                </div>
                <div className="contact-line hours-line">
                  <span>⏰</span>
                  <small>{org.hours}</small>
                </div>
              </div>

              <div className="org-action-row">
                <button
                  type="button"
                  className="button button-primary org-choose-btn"
                  onClick={() => {
                    const pendingFirst = donations.find((d) => d.status === "pending");
                    if (pendingFirst) {
                      onMarkDonated(pendingFirst.id, org.name);
                    } else {
                      alert(`Pour faire un don à ${org.name}, contacte-les au ${org.phone} ou rends-toi à : ${org.address}.`);
                    }
                  }}
                >
                  {pendingCount > 0 ? `🎁 Attribuer un don à ${org.name}` : "📞 Contacter cette association"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ================= SECTION 3 : GUIDE POUR BIEN DONNER ================= */}
      <section className="donation-tips-box">
        <div className="card-heading">
          <div>
            <span className="eyebrow">CONSEILS DU STYLISTE DRESSME</span>
            <h3>Comment bien préparer ses dons en 3 gestes simples&nbsp;?</h3>
          </div>
          <span className="form-sparkle">✨</span>
        </div>

        <div className="donation-tips-grid">
          <div className="donation-tip-item">
            <span className="tip-number">1</span>
            <h4>Laver et plier soigneusement</h4>
            <p>
              Même s'ils sont d'occasion, des vêtements lavés et propres permettent aux bénévoles de les distribuer directement sans frais de pressing.
            </p>
          </div>
          <div className="donation-tip-item">
            <span className="tip-number">2</span>
            <h4>Vérifier fermetures & boutons</h4>
            <p>
              Assure-toi que les zips glissent bien et que les boutons sont attachés. Un vêtement prêt à être porté immédiatement est un vrai cadeau de dignité.
            </p>
          </div>
          <div className="donation-tip-item">
            <span className="tip-number">3</span>
            <h4>Séparer par sacs et saisons</h4>
            <p>
              Emballe tes vêtements dans des sacs étanches et étiquette-les si possible (*« Hiver Homme »*, *« Été Enfant »*). Cela facilite grandement le tri des maraudes.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
