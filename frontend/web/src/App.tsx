import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  api,
  ClothingItem,
  CurrentUser,
  getApiError,
  Outfit,
  PackingList,
  PurchaseResult,
  ScheduledOutfit,
  StyleProfile,
  uploadPhoto,
} from "./api";
import "./styles.css";

type Screen =
  | "overview"
  | "wardrobe"
  | "outfits"
  | "calendar"
  | "profile"
  | "packing"
  | "purchase"
  | "tryon";

const NAV_ITEMS: { id: Screen; label: string; icon: string; group: string }[] = [
  { id: "overview", label: "Accueil", icon: "⌂", group: "TON ESPACE" },
  { id: "wardrobe", label: "Mon dressing", icon: "◈", group: "TON ESPACE" },
  { id: "outfits", label: "Idées de looks", icon: "✧", group: "TON ESPACE" },
  { id: "calendar", label: "Calendrier", icon: "▦", group: "TON ESPACE" },
  { id: "profile", label: "Mon style", icon: "◎", group: "DÉCOUVRIR" },
  { id: "packing", label: "Ma valise", icon: "▣", group: "DÉCOUVRIR" },
  { id: "purchase", label: "J’achète ou pas ?", icon: "♡", group: "DÉCOUVRIR" },
  { id: "tryon", label: "Essayage virtuel", icon: "✦", group: "DÉCOUVRIR" },
];

const SCREEN_COPY: Record<Screen, { title: string; subtitle: string }> = {
  overview: { title: "Bonjour, bienvenue chez toi ✨", subtitle: "Ton style, tes pièces et tes inspirations au même endroit." },
  wardrobe: { title: "Mon dressing", subtitle: "Toutes tes pièces réunies, prêtes à composer de nouveaux looks." },
  outfits: { title: "Idées de looks", subtitle: "Des tenues pensées selon l’occasion, la saison et la météo." },
  calendar: { title: "Mon calendrier", subtitle: "Prépare tes tenues et retrouve-les au bon moment." },
  profile: { title: "Mon style", subtitle: "Découvre ce que ton dressing révèle de tes préférences." },
  packing: { title: "Ma valise", subtitle: "Prépare une sélection de pièces pour ton prochain voyage." },
  purchase: { title: "J’achète ou pas ?", subtitle: "Vérifie si une nouvelle pièce s’accorde à ton dressing." },
  tryon: { title: "Essayage virtuel", subtitle: "Visualise une pièce sur ta photo avant de l’ajouter à ton look." },
};

const OCCASIONS = [
  ["quotidien", "Quotidien"],
  ["travail", "Travail"],
  ["sortie", "Sortie"],
  ["soirée", "Soirée"],
  ["événement", "Événement"],
];
const CITIES = ["Tunis", "Sousse", "Sfax", "Djerba"];
const SEASONS = ["printemps", "été", "automne", "hiver"];
const WARDROBE_FAVORITES_KEY = "dressme_wardrobe_favorites";
const OUTFIT_FAVORITES_KEY = "dressme_favorite_outfits";

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
  const [screen, setScreen] = useState<Screen>("overview");
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [outfits, setOutfits] = useState<Outfit[]>([]);
  const [scheduled, setScheduled] = useState<ScheduledOutfit[]>([]);
  const [profile, setProfile] = useState<StyleProfile | null>(null);
  const [packingLists, setPackingLists] = useState<PackingList[]>([]);
  const [wardrobeFavorites, setWardrobeFavorites] = useState<string[]>(() => readIds(WARDROBE_FAVORITES_KEY));
  const [outfitFavorites, setOutfitFavorites] = useState<string[]>(() => readIds(OUTFIT_FAVORITES_KEY));
  const [loading, setLoading] = useState(Boolean(token));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [monthAnchor, setMonthAnchor] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));

  const today = todayLocal();
  const selectedNav = NAV_ITEMS.find((item) => item.id === screen);
  const displayName = user?.full_name?.split(/\s+/)[0] || "toi";
  const itemsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);

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

  async function addItem(file: File, season: string) {
    setBusy("wardrobe-upload");
    setError("");
    try {
      const imageUrl = await uploadPhoto(file);
      const { data } = await api.post<ClothingItem>("/wardrobe/", { image_url: imageUrl, season: season || undefined });
      setItems((current) => [data, ...current]);
      setNotice("La pièce a été analysée et ajoutée à ton dressing.");
    } catch (cause: unknown) {
      reportError(cause);
    } finally {
      setBusy("");
    }
  }

  async function deleteItem(item: ClothingItem) {
    if (!window.confirm("Retirer cette pièce de ton dressing ?")) return;
    try {
      await api.delete(`/wardrobe/${item.id}`);
      setItems((current) => current.filter((currentItem) => currentItem.id !== item.id));
      const next = wardrobeFavorites.filter((id) => id !== item.id);
      setWardrobeFavorites(next);
      localStorage.setItem(WARDROBE_FAVORITES_KEY, JSON.stringify(next));
      setNotice("La pièce a été supprimée.");
    } catch (cause: unknown) {
      reportError(cause);
    }
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
      const { data } = await api.post<{ outfits: Outfit[]; context: Record<string, string | null> }>("/recommendations/outfits", {
        occasion: String(form.get("occasion") || "") || undefined,
        city: String(form.get("city") || "") || undefined,
        season: String(form.get("season") || "") || undefined,
      });
      setOutfits(data.outfits);
      setNotice(`${data.outfits.length} idée${data.outfits.length === 1 ? "" : "s"} de tenue proposée${data.outfits.length === 1 ? "" : "s"}.`);
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
  const [selectedTryOnItem, setSelectedTryOnItem] = useState("");

  async function generateTryOn() {
    if (!selectedTryOnItem) return;
    setBusy("tryon");
    setError("");
    setTryOnResult("");
    try {
      const { data } = await api.post<{ result_image_url: string }>("/tryon/", { garment_item_id: selectedTryOnItem });
      setTryOnResult(data.result_image_url);
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
          <div className="breadcrumb"><span>DressMe</span><b>/</b>{selectedNav?.label ?? "Accueil"}</div>
          <div className="topbar-right">
            <span className="today-label">{new Date().toLocaleDateString("fr-TN", { weekday: "long", day: "numeric", month: "long" })}</span>
            <button className="topbar-avatar-button" type="button" onClick={() => navigate("profile")} aria-label="Ouvrir mon profil"><Avatar user={user} /></button>
          </div>
        </header>

        <section className="workspace-hero" aria-label="DressMe, avec amour depuis la Tunisie">
          <img className="workspace-hero-photo" src="/sidi-bou-style-inspiration.jpg" alt="" />
          <div className="workspace-hero-content">
            <img src="/dressme-logo.png" alt="DressMe — A smarter wardrobe for a brighter you" />
            <div><span>TUNIS · SIDI BOU SAÏD</span><strong>Le chic d’ici, le style qui va partout.</strong></div>
          </div>
          <span className="workspace-zellige zellige-left">✦</span>
          <span className="workspace-zellige zellige-right">✦</span>
        </section>

        <div className="page-content">
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
              <section className="quick-actions"><div><span className="eyebrow">À DÉCOUVRIR</span><h3>Et si on allait plus loin ?</h3></div><button type="button" onClick={() => navigate("purchase")}><span>♡</span><b>Vérifier un achat</b><small>Fais le bon choix</small><i>→</i></button><button type="button" onClick={() => navigate("tryon")}><span>✦</span><b>Essayer une pièce</b><small>Projette-toi dans ton look</small><i>→</i></button><button type="button" onClick={() => navigate("packing")}><span>▣</span><b>Préparer ma valise</b><small>Voyage sans rien oublier</small><i>→</i></button></section>
            </>
          )}

          {screen === "wardrobe" && <WardrobeView items={items} favorites={wardrobeFavorites} busy={busy} onAdd={addItem} onDelete={deleteItem} onToggleFavorite={(id) => toggleFavorite(id, "wardrobe")} />}
          {screen === "outfits" && <OutfitsView items={items} itemsById={itemsById} outfits={outfits} favorites={outfitFavorites} scheduled={scheduled} today={today} busy={busy} onGenerate={generateLooks} onToggleFavorite={(id) => toggleFavorite(id, "outfit")} onSchedule={scheduleOutfit} />}
          {screen === "calendar" && <CalendarView anchor={monthAnchor} onMonthChange={setMonthAnchor} scheduled={scheduled} items={items} loading={loading} onSave={saveCalendarOutfit} onRemove={removeCalendarOutfit} />}
          {screen === "profile" && <ProfileView user={user} profile={profile} busy={busy} onAvatar={uploadAvatar} onNavigate={navigate} />}
          {screen === "packing" && <PackingView lists={packingLists} busy={busy} onCreate={createPacking} onToggle={togglePackedItem} onDelete={deletePackingList} />}
          {screen === "purchase" && <PurchaseView result={purchaseResult} busy={busy} onCheck={runPurchaseCheck} />}
          {screen === "tryon" && <TryOnView user={user} items={items} selectedId={selectedTryOnItem} result={tryOnResult} busy={busy} onSelect={setSelectedTryOnItem} onAvatar={uploadAvatar} onTryOn={generateTryOn} />}

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

function WardrobeView({ items, favorites, busy, onAdd, onDelete, onToggleFavorite }: {
  items: ClothingItem[];
  favorites: string[];
  busy: string;
  onAdd: (file: File, season: string) => Promise<void>;
  onDelete: (item: ClothingItem) => Promise<void>;
  onToggleFavorite: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("toutes");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [season, setSeason] = useState("");
  const filtered = items.filter((item) => {
    const matchesCategory = category === "toutes" || (item.category ?? "autre").toLocaleLowerCase() === category;
    const matchesFavorite = !favoritesOnly || favorites.includes(item.id);
    const searchable = [item.category, item.style, item.season, item.pattern, ...(item.colors ?? [])].join(" ").toLocaleLowerCase();
    return matchesCategory && matchesFavorite && searchable.includes(query.trim().toLocaleLowerCase());
  });
  const categories = Array.from(new Set(items.map((item) => (item.category ?? "autre").toLocaleLowerCase()))).sort();

  return <>
    <PageHeading title="Mon dressing" subtitle="Ajoute, retrouve et organise les pièces que tu aimes porter." action={<label className={`button button-primary file-button${busy === "wardrobe-upload" ? " is-disabled" : ""}`}>＋ {busy === "wardrobe-upload" ? "Analyse en cours…" : "Ajouter une pièce"}<input type="file" accept="image/*" disabled={busy === "wardrobe-upload"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onAdd(file, season); event.target.value = ""; }} /></label>} />
    <div className="wardrobe-toolbar"><label className="search-field"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Chercher une couleur, un style…" /></label><label className="filter-select"><span>Catégorie</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="toutes">Toutes</option>{categories.map((value) => <option key={value} value={value}>{categoryLabel(value)}</option>)}</select></label><button type="button" className={`filter-favorite${favoritesOnly ? " is-selected" : ""}`} aria-pressed={favoritesOnly} onClick={() => setFavoritesOnly((current) => !current)}>♡ Favoris</button><label className="season-select"><span>Saison de la pièce (facultatif)</span><select value={season} onChange={(event) => setSeason(event.target.value)}><option value="">Non précisée</option>{SEASONS.map((value) => <option key={value} value={value}>{categoryLabel(value)}</option>)}</select></label></div>
    <div className="results-line"><span><b>{filtered.length}</b> pièce{filtered.length === 1 ? "" : "s"} {favoritesOnly ? "dans tes favoris" : "dans ton dressing"}</span><span>Ajoute une photo nette d’une seule pièce pour une meilleure analyse.</span></div>
    {filtered.length === 0 ? <EmptyState icon={items.length === 0 ? "◈" : "⌕"} title={items.length === 0 ? "Ton dressing commence ici" : "Aucune pièce trouvée"} text={items.length === 0 ? "Ajoute une photo de vêtement : DressMe identifiera sa catégorie, ses couleurs et son style." : "Essaie d’ajuster ta recherche ou tes filtres."} /> : <div className="clothing-grid">{filtered.map((item) => <article className="clothing-card" key={item.id}><div className="clothing-photo"><img src={item.image_url} alt={categoryLabel(item.category)} loading="lazy" /><button type="button" className={`favorite-toggle${favorites.includes(item.id) ? " is-favorite" : ""}`} aria-label={favorites.includes(item.id) ? "Retirer des favoris" : "Ajouter aux favoris"} aria-pressed={favorites.includes(item.id)} onClick={() => onToggleFavorite(item.id)}>{favorites.includes(item.id) ? "♥" : "♡"}</button></div><div className="clothing-info"><span className="category-pill">{categoryLabel(item.category)}</span><h3>{item.style ? categoryLabel(item.style) : "Pièce de mon dressing"}</h3><p>{[...(item.colors ?? []), item.season, item.pattern].filter(Boolean).map(categoryLabel).join(" · ") || "Style à découvrir"}</p><button type="button" className="remove-link" onClick={() => void onDelete(item)}>Retirer du dressing</button></div></article>)}</div>}
  </>;
}

function OutfitsView({ items, itemsById, outfits, favorites, scheduled, today, busy, onGenerate, onToggleFavorite, onSchedule }: {
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
}) {
  const [showFavorites, setShowFavorites] = useState(false);
  const [planDates, setPlanDates] = useState<Record<string, string>>({});
  const filtered = showFavorites ? outfits.filter((outfit) => favorites.includes(outfit.id)) : outfits;
  return <>
    <PageHeading title="Des looks faits pour toi" subtitle="Choisis ton occasion et ta ville pour recevoir des idées depuis ton dressing." />
    <form className="content-card recommendation-form" onSubmit={(event) => void onGenerate(event)}>
      <div className="card-heading"><div><span className="eyebrow">TON INSPIRATION DU JOUR</span><h3>Quel est le programme ?</h3></div><span className="form-sparkle">✧</span></div>
      <div className="form-grid"><label className="field"><span>Occasion</span><select name="occasion" defaultValue=""><option value="">Toutes les occasions</option>{OCCASIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="field"><span>Ville</span><select name="city" defaultValue=""><option value="">Sans météo locale</option>{CITIES.map((city) => <option key={city} value={city}>{city}</option>)}</select></label><label className="field"><span>Saison</span><select name="season" defaultValue=""><option value="">Automatique</option>{SEASONS.map((season) => <option key={season} value={season}>{categoryLabel(season)}</option>)}</select></label></div>
      <div className="form-submit-row"><p>Les propositions utilisent les pièces de ton dressing.</p><button className="button button-primary" disabled={busy === "looks" || items.length === 0}>{busy === "looks" ? "Recherche de tenues…" : "✨  Trouver des looks"}</button></div>
      {items.length === 0 && <p className="inline-hint">Ajoute d’abord quelques pièces pour recevoir des recommandations.</p>}
    </form>
    <div className="section-toolbar"><div><span className="eyebrow">TES PROPOSITIONS</span><h2>{filtered.length} look{filtered.length === 1 ? "" : "s"}</h2></div><div className="segmented-control"><button className={!showFavorites ? "active" : ""} type="button" onClick={() => setShowFavorites(false)}>Tous les looks</button><button className={showFavorites ? "active" : ""} type="button" onClick={() => setShowFavorites(true)}>♥ Favoris {favorites.length > 0 && `· ${favorites.length}`}</button></div></div>
    {filtered.length === 0 ? <EmptyState icon={showFavorites ? "♡" : "✧"} title={showFavorites ? "Pas encore de look favori" : "Tes prochains looks apparaîtront ici"} text={showFavorites ? "Appuie sur le cœur d’une proposition pour la retrouver ici." : "Choisis une occasion et lance une recherche pour composer tes premières tenues."} /> : <div className="outfit-grid">{filtered.map((outfit) => {
      const outfitItems = outfit.item_ids.map((id) => itemsById.get(id)).filter((item): item is ClothingItem => Boolean(item));
      const isPlanned = scheduled.some((entry) => entry.item_ids.length === outfit.item_ids.length && entry.item_ids.every((id) => outfit.item_ids.includes(id)));
      return <article className="outfit-card" key={outfit.id}><div className="outfit-card-top"><div><span className="category-pill">{outfit.occasion ?? "Suggestion personnalisée"}</span><h3>Un look pour {outfit.occasion ?? "toi"}</h3></div><button type="button" className={`favorite-toggle outfit-heart${favorites.includes(outfit.id) ? " is-favorite" : ""}`} aria-label={favorites.includes(outfit.id) ? "Retirer des looks favoris" : "Enregistrer dans les looks favoris"} aria-pressed={favorites.includes(outfit.id)} onClick={() => onToggleFavorite(outfit.id)}>{favorites.includes(outfit.id) ? "♥" : "♡"}</button></div><div className="outfit-items">{outfitItems.map((item) => <div className="outfit-piece" key={item.id}><img src={item.image_url} alt={categoryLabel(item.category)} loading="lazy" /><span>{categoryLabel(item.category)}</span></div>)}</div><div className="outfit-meta">{outfit.relevance_score != null && <span className="match-score">✦ {Math.round(outfit.relevance_score * 100)}% match</span>}<span>{outfit.item_ids.length} pièce{outfit.item_ids.length === 1 ? "" : "s"}</span></div>{outfit.explanation && <details className="outfit-explanation"><summary>Voir le conseil de style</summary><p>{outfit.explanation}</p></details>}<div className="schedule-row"><input aria-label="Date de planification" type="date" min={today} value={planDates[outfit.id] ?? today} onChange={(event) => setPlanDates((current) => ({ ...current, [outfit.id]: event.target.value }))} /><button type="button" className="button button-outline" onClick={() => void onSchedule(outfit, planDates[outfit.id] ?? today)}>{isPlanned ? "Planifier à nouveau" : "📅 Planifier"}</button></div></article>;
    })}</div>}
  </>;
}

function CalendarView({ anchor, onMonthChange, scheduled, items, loading, onSave, onRemove }: {
  anchor: Date;
  onMonthChange: (date: Date) => void;
  scheduled: ScheduledOutfit[];
  items: ClothingItem[];
  loading: boolean;
  onSave: (date: string, ids: string[]) => Promise<ScheduledOutfit>;
  onRemove: (date: string) => Promise<void>;
}) {
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

  function changeMonth(delta: number) {
    const next = new Date(anchor.getFullYear(), anchor.getMonth() + delta, 1);
    onMonthChange(next);
    setSelectedDate(dayString(next));
    setEditing(false);
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
    <PageHeading title="Mon calendrier" subtitle="Visualise tes tenues prévues et choisis les pièces à porter chaque jour." />
    <div className="calendar-layout">
      <section className="content-card calendar-card"><div className="calendar-month-header"><button type="button" className="month-arrow" aria-label="Mois précédent" onClick={() => changeMonth(-1)}>‹</button><div><span className="eyebrow">TON AGENDA STYLE</span><h2>{monthName}</h2></div><button type="button" className="month-arrow" aria-label="Mois suivant" onClick={() => changeMonth(1)}>›</button></div><div className="calendar-grid">{["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"].map((day) => <span className="weekday" key={day}>{day}</span>)}{days.map((day, index) => {
        if (!day) return <span className="calendar-blank" key={`blank-${index}`} />;
        const date = `${anchor.getFullYear()}-${String(anchor.getMonth() + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const hasOutfit = scheduled.some((entry) => entry.date === date);
        return <button type="button" key={date} className={`calendar-day${selectedDate === date ? " selected" : ""}${date === todayLocal() ? " is-today" : ""}`} aria-label={`${day}${hasOutfit ? ", tenue planifiée" : ""}`} aria-pressed={selectedDate === date} onClick={() => { setSelectedDate(date); setEditing(false); }}><span>{day}</span>{hasOutfit && <i />}</button>;
      })}</div>{loading && <p className="inline-hint">Chargement du calendrier…</p>}</section>
      <section className="content-card day-details"><span className="eyebrow">TA JOURNÉE</span><h2>{new Date(`${selectedDate}T12:00:00`).toLocaleDateString("fr-TN", { weekday: "long", day: "numeric", month: "long" })}</h2>{plan && !editing ? <><div className="day-plan-images">{plan.items.map((item) => <div key={item.id}><img src={item.image_url} alt={categoryLabel(item.category)} /><span>{categoryLabel(item.category)}</span></div>)}</div><p className="inline-hint">{plan.items.length} pièce{plan.items.length === 1 ? "" : "s"} choisie{plan.items.length === 1 ? "" : "s"} pour cette journée.</p><div className="button-row"><button type="button" className="button button-primary" onClick={startEdit}>Modifier la tenue</button><button type="button" className="button button-danger-light" onClick={() => void onRemove(selectedDate)}>Retirer</button></div></> : !editing ? <><div className="day-empty-icon">✧</div><p className="inline-hint">Aucune tenue prévue. Choisis des pièces pour préparer ta journée.</p><button type="button" className="button button-primary" onClick={startEdit}>＋ Planifier un look</button></> : <><p className="inline-hint">Sélectionne les pièces de ton dressing à porter ce jour.</p><div className="calendar-pick-grid">{items.map((item) => <button type="button" className={`calendar-pick-item${selectedIds.includes(item.id) ? " picked" : ""}`} aria-pressed={selectedIds.includes(item.id)} key={item.id} onClick={() => setSelectedIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])}><img src={item.image_url} alt={categoryLabel(item.category)} /><span>{categoryLabel(item.category)}</span></button>)}</div>{items.length === 0 && <p className="inline-hint">Ajoute des pièces au dressing avant de planifier.</p>}<div className="button-row"><button type="button" className="button button-primary" disabled={saving || selectedIds.length === 0} onClick={() => void save()}>{saving ? "Enregistrement…" : "Enregistrer"}</button><button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Annuler</button></div></>}</section>
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
    <PageHeading title="Mon style" subtitle="Les couleurs, les catégories et les inspirations qui composent ton dressing." />
    <div className="profile-layout"><section className="content-card profile-card"><div className="profile-cover" style={{ backgroundImage: "linear-gradient(180deg, rgba(26,35,126,.12), rgba(26,35,126,.22)), url('/tunisian-wardrobe-inspiration.jpg')" }}><span className="profile-sun">☀</span><span className="profile-flower">✿</span><span className="profile-arch" /></div><div className="profile-person"><Avatar user={user} size="large" /><div><h2>{user?.full_name || "Mon espace DressMe"}</h2><p>{user?.email}</p></div><label className={`button button-outline file-button${busy === "avatar" ? " is-disabled" : ""}`}>{busy === "avatar" ? "Envoi…" : user?.avatar_photo_url ? "Changer ma photo" : "Ajouter une photo"}<input type="file" accept="image/*" disabled={busy === "avatar"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onAvatar(file); event.target.value = ""; }} /></label></div><div className="profile-stat-line"><strong>{profile?.wardrobe_size ?? 0}</strong><span>pièces dans ton dressing</span></div>{profile?.narrative && <blockquote className="style-narrative">“{profile.narrative}”</blockquote>}</section><section className="content-card"><div className="card-heading"><div><span className="eyebrow">ANALYSE DU DRESSING</span><h3>Les pièces que tu portes</h3></div></div>{profile && Object.entries(profile.category_counts).length > 0 ? <div className="category-bars">{Object.entries(profile.category_counts).sort((a, b) => b[1] - a[1]).map(([name, count]) => <div className="category-bar-row" key={name}><span>{categoryLabel(name)}</span><div><i style={{ width: `${(count / maxCount) * 100}%` }} /></div><b>{count}</b></div>)}</div> : <EmptyState icon="◈" title="Ton dressing attend ses premières pièces" text="Les catégories apparaîtront ici après l’ajout de vêtements." onAction={() => onNavigate("wardrobe")} action="Ouvrir le dressing" />}<div className="preference-block"><h4>Couleurs préférées</h4><div className="style-chips">{profile?.favorite_colors.length ? profile.favorite_colors.map((color) => <span key={color}>● {color}</span>) : <small>Ajoute des pièces pour découvrir ta palette.</small>}</div><h4>Styles favoris</h4><div className="style-chips">{profile?.favorite_styles.length ? profile.favorite_styles.map((style) => <span key={style}>✧ {style}</span>) : <small>Ton profil de style se construit avec ton dressing.</small>}</div></div></section></div><section className="quick-actions profile-quick"><div><span className="eyebrow">ACCÈS RAPIDE</span><h3>Continue ton expérience</h3></div><button type="button" onClick={() => onNavigate("calendar")}><span>▦</span><b>Calendrier</b><small>Planifier un look</small><i>→</i></button><button type="button" onClick={() => onNavigate("packing")}><span>▣</span><b>Ma valise</b><small>Préparer un voyage</small><i>→</i></button><button type="button" onClick={() => onNavigate("tryon")}><span>✦</span><b>Essayage virtuel</b><small>Tester une pièce</small><i>→</i></button></section>
  </>;
}

function PackingView({ lists, busy, onCreate, onToggle, onDelete }: {
  lists: PackingList[];
  busy: string;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onToggle: (list: PackingList, id: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  return <>
    <PageHeading title="Prête pour le voyage" subtitle="Une valise pensée selon ta destination, la durée et les pièces de ton dressing." />
    <form className="content-card packing-form" onSubmit={(event) => void onCreate(event)}><div className="card-heading"><div><span className="eyebrow">NOUVELLE ESCAPADE</span><h3>Où part-on ?</h3></div><span className="form-sparkle">✈</span></div><div className="form-grid"><label className="field"><span>Destination</span><input name="destination" required placeholder="Ex. Djerba" /></label><label className="field"><span>Durée (jours)</span><input name="duration" type="number" min="1" max="90" defaultValue="3" required /></label><label className="field"><span>Type de voyage</span><select name="tripType" defaultValue="plage"><option value="plage">Plage & détente</option><option value="business">Professionnel</option><option value="tourisme">Tourisme & découverte</option></select></label></div><div className="form-submit-row"><p>DressMe sélectionnera des pièces adaptées à ton voyage.</p><button className="button button-primary" disabled={busy === "packing-create"}>{busy === "packing-create" ? "Préparation…" : "Créer ma liste →"}</button></div></form>{lists.length === 0 ? <EmptyState icon="▣" title="Aucun voyage prévu" text="Crée une liste pour préparer ta prochaine valise depuis ton dressing." /> : <div className="packing-list-grid">{lists.map((list) => <article className="content-card packing-list-card" key={list.id}><div className="packing-list-heading"><div><span className="category-pill">{list.duration_days} jours · {list.trip_type}</span><h3>{list.destination}</h3></div><button className="remove-link" type="button" onClick={() => void onDelete(list.id)}>Supprimer</button></div><div className="packing-progress"><span>{list.checked_item_ids.length} / {list.items.length} pièces dans la valise</span><i><b style={{ width: `${list.items.length ? (list.checked_item_ids.length / list.items.length) * 100 : 0}%` }} /></i></div><div className="packing-items">{list.items.map((item) => { const checked = list.checked_item_ids.includes(item.id); return <label className={`packing-item${checked ? " packed" : ""}`} key={item.id}><input type="checkbox" checked={checked} onChange={() => void onToggle(list, item.id)} /><img src={item.image_url} alt="" /><span>{categoryLabel(item.category)}</span></label>; })}</div>{list.items.length === 0 && <p className="inline-hint">Ajoute plus de pièces à ton dressing pour enrichir cette liste.</p>}</article>)}</div>}
  </>;
}

function PurchaseView({ result, busy, onCheck }: {
  result: PurchaseResult | null;
  busy: string;
  onCheck: (file: File) => Promise<void>;
}) {
  const verdictText = result?.verdict === "recommended" ? "Cette pièce s’accorde à ton dressing" : result?.verdict === "think_twice" ? "À réfléchir avant de craquer" : "Cette pièce s’intègre difficilement";
  return <>
    <PageHeading title="J’achète ou pas ?" subtitle="Une photo suffit pour savoir si cette pièce complète vraiment ton dressing." />
    <div className="purchase-layout"><section className="content-card purchase-card"><span className="eyebrow">CONSEIL AVANT ACHAT</span><h2>Une envie en tête ?</h2><p>Ajoute une photo de l’article que tu envisages. DressMe le compare aux couleurs et aux pièces de ton dressing.</p><label className={`upload-drop${busy === "purchase" ? " is-loading" : ""}`}><input type="file" accept="image/*" disabled={busy === "purchase"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onCheck(file); event.target.value = ""; }} /><span className="upload-icon">{busy === "purchase" ? "◌" : "↑"}</span><strong>{busy === "purchase" ? "Analyse en cours…" : "Choisir une photo"}</strong><small>JPG, PNG ou image de ton appareil</small></label><p className="privacy-note">🔒 Ta photo est utilisée uniquement pour cette analyse.</p></section><section className="content-card purchase-result">{result ? <><span className={`verdict-icon verdict-${result.verdict}`}>{result.verdict === "recommended" ? "✓" : result.verdict === "think_twice" ? "?" : "×"}</span><span className="eyebrow">TON RÉSULTAT</span><h2>{verdictText}</h2><div className="compatibility-meter"><div><span>Compatibilité avec ton style</span><b>{Math.round(result.compatibility_score * 100)}%</b></div><i><b style={{ width: `${Math.min(100, Math.max(0, result.compatibility_score * 100))}%` }} /></i></div><p className="verdict-explanation">{result.explanation}</p>{result.catalog_alternatives.length > 0 && <><h3>Des alternatives à découvrir</h3><div className="alternatives">{result.catalog_alternatives.map((alternative, index) => <article className="alternative-card" key={`${alternative.name}-${index}`}>{alternative.image_url ? <img src={alternative.image_url} alt={alternative.name} /> : <span className="alternative-placeholder">✧</span>}<div><b>{alternative.name}</b><small>{[alternative.brand, alternative.category].filter(Boolean).join(" · ")}</small><strong>{alternative.price != null ? `${alternative.price} TND` : "Voir le produit"}</strong></div></article>)}</div></>}</> : <EmptyState icon="♡" title="Ton avis style personnalisé" text="Envoie une photo pour voir la compatibilité, obtenir un conseil et trouver des alternatives." />}</section></div>
  </>;
}

function TryOnView({ user, items, selectedId, result, busy, onSelect, onAvatar, onTryOn }: {
  user: CurrentUser | null;
  items: ClothingItem[];
  selectedId: string;
  result: string;
  busy: string;
  onSelect: (id: string) => void;
  onAvatar: (file: File) => Promise<void>;
  onTryOn: () => Promise<void>;
}) {
  return <>
    <PageHeading title="Essayage virtuel" subtitle="Choisis ta photo et une pièce de ton dressing pour imaginer la tenue." />
    <div className="tryon-layout"><section className="content-card tryon-photo-card"><div className="card-heading"><div><span className="eyebrow">ÉTAPE 1</span><h3>Ta photo de référence</h3></div><span className="step-dot">01</span></div><label className="avatar-upload">{user?.avatar_photo_url ? <img src={user.avatar_photo_url} alt="Photo personnelle" /> : <span className="avatar-placeholder-large">＋</span>}<span>{busy === "avatar" ? "Envoi en cours…" : user?.avatar_photo_url ? "Changer ma photo" : "Ajouter une photo plein pied"}</span><input type="file" accept="image/*" disabled={busy === "avatar"} onChange={(event) => { const file = event.target.files?.[0]; if (file) void onAvatar(file); event.target.value = ""; }} /></label><p className="privacy-note">Choisis une photo claire, de face et en pied. Ta photo reste associée à ton compte.</p></section><section className="content-card tryon-garment-card"><div className="card-heading"><div><span className="eyebrow">ÉTAPE 2</span><h3>Choisis une pièce</h3></div><span className="step-dot">02</span></div>{items.length ? <div className="tryon-items">{items.map((item) => <button type="button" className={`tryon-item${selectedId === item.id ? " selected" : ""}`} key={item.id} aria-pressed={selectedId === item.id} onClick={() => onSelect(item.id)}><img src={item.image_url} alt={categoryLabel(item.category)} /><span>{categoryLabel(item.category)}</span>{selectedId === item.id && <i>✓</i>}</button>)}</div> : <EmptyState icon="◈" title="Ton dressing est vide" text="Ajoute une pièce avant de l’essayer virtuellement." />}<button type="button" className="button button-primary tryon-button" disabled={!user?.avatar_photo_url || !selectedId || busy === "tryon"} onClick={() => void onTryOn()}>{busy === "tryon" ? "Génération en cours…" : "✧  Essayer cette pièce"}</button>{!user?.avatar_photo_url && <p className="inline-hint">Ajoute d’abord ta photo de référence.</p>}</section></div>{result && <section className="content-card tryon-result"><span className="eyebrow">TON LOOK</span><h2>Voilà une idée à essayer ✨</h2><img src={result} alt="Résultat de l’essayage virtuel" /></section>}
  </>;
}
