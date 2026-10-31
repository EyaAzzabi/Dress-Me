import { FormEvent, useEffect, useRef, useState } from "react";
import { api, getApiError, StyleProfile } from "./api";

type Topic = "wardrobe" | "item" | "outfit" | "purchase";
interface Context {
  profile: StyleProfile;
  items: { id: string; category: string | null; colors: string[]; style: string | null; image_url: string }[];
  outfits: { id: string; occasion: string | null; item_count: number }[];
  purchases: { id: string; category: string; color: string | null; verdict: string }[];
}
interface Answer {
  status: "success" | "needs_data" | "unavailable";
  explanation: string | null;
  evidence: { label: string; detail: string }[];
  ideas?: { title: string; advice: string; items: { id: string; label: string }[]; optional_additions: string[] }[];
  follow_up?: string;
  failure_reason?: string | null;
  decision?: { verdict: string; label: string; score: number; rationale: string } | null;
}
interface Turn { id: number; question: string; topic: Topic; recordId: string; answer?: Answer; error?: string; }
const topics: { id: Topic; label: string }[] = [{ id: "wardrobe", label: "Mon dressing" }, { id: "item", label: "Une pièce" }, { id: "outfit", label: "Une tenue" }, { id: "purchase", label: "Un achat" }];

export default function LlmAssistant({ onNavigate }: { onNavigate: (screen: "wardrobe" | "outfits" | "purchase") => void }) {
  const [context, setContext] = useState<Context | null>(null);
  const [contextError, setContextError] = useState("");
  const [loading, setLoading] = useState(true);
  const [topic, setTopic] = useState<Topic>("wardrobe");
  const [recordId, setRecordId] = useState("");
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [wardrobeOnly, setWardrobeOnly] = useState(false);
  const thread = useRef<HTMLDivElement>(null);
  const latestReply = useRef<HTMLDivElement>(null);
  const serial = useRef(0);
  const composer = useRef<HTMLTextAreaElement>(null);
  async function refresh() {
    setLoading(true); setContextError("");
    try { const { data } = await api.get<Context>("/llm/context"); setContext(data); }
    catch (error) { setContextError(getApiError(error)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    const last = turns[turns.length - 1];
    if (!last || !thread.current) return;
    const top = (last.answer || last.error) && latestReply.current ? latestReply.current.offsetTop - 16 : thread.current.scrollHeight;
    thread.current.scrollTo({ top, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [turns]);
  function chooseTopic(value: Topic) {
    setTopic(value);
    setRecordId(value === "item" ? context?.items[0]?.id ?? "" : value === "outfit" ? context?.outfits[0]?.id ?? "" : value === "purchase" ? context?.purchases[0]?.id ?? "" : "");
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    const question = message.trim();
    if (!question || busy || loading || !context || (topic !== "wardrobe" && !recordId)) return;
    const id = ++serial.current;
    const history = turns.filter((t) => t.answer?.status === "success").slice(-4).flatMap((t) => [
      { role: "user", content: t.question.slice(0, 2000) },
      { role: "assistant", content: [t.answer?.explanation, ...(t.answer?.ideas ?? []).map((i) => `${i.title}: ${i.advice}${i.optional_additions.length ? " Compléments optionnels non confirmés: " + i.optional_additions.join(", ") : ""}`), t.answer?.follow_up].filter(Boolean).join("\n").slice(0, 2000) },
    ]);
    setTurns((current) => [...current, { id, question, topic, recordId }]);
    setMessage(""); setBusy(true);
    try {
      const { data } = await api.post<Answer>("/llm/chat", { message: question, topic, record_id: recordId || null, history, wardrobe_only: wardrobeOnly });
      setTurns((current) => current.map((t) => t.id === id ? { ...t, answer: data } : t));
    } catch (error) { setTurns((current) => current.map((t) => t.id === id ? { ...t, error: getApiError(error) } : t)); }
    finally { setBusy(false); composer.current?.focus(); }
  }
  const options = topic === "item" ? context?.items.map((i) => ({ id: i.id, label: [i.category, ...i.colors].filter(Boolean).join(" · ") })) : topic === "outfit" ? context?.outfits.map((o, i) => ({ id: o.id, label: `${o.occasion ?? "Tenue"} · ${o.item_count} pièces · ${i + 1}` })) : context?.purchases.map((p) => ({ id: p.id, label: [p.category, p.color].filter(Boolean).join(" · ") }));
  const missingSelection = topic !== "wardrobe" && (!options?.length || !recordId);
  const suggestions = topic === "item" ? ["Comment styler cette pièce au quotidien ?", "Et pour une soirée, sans talons ?"] : topic === "outfit" ? ["Comment rendre cette tenue plus habillée ?", "Propose une variante plus décontractée"] : topic === "purchase" ? ["Est-ce que cet achat répond à un vrai besoin ?", "Comment utiliser ce que je possède déjà ?"] : ["Aide-moi à composer une tenue pour un entretien", "Comment apporter de la couleur à mon style ?"];
  return <div className="assistant-layout">
    <aside className="content-card assistant-context"><span className="eyebrow">TON DRESSING, NOTRE POINT DE DÉPART</span><h2>À ta façon.</h2><p>Une pièce à réinventer, une occasion, une envie de changement ? On construit tes idées ensemble.</p>
      {loading ? <p role="status">Je retrouve ton dressing…</p> : contextError ? <p role="alert">{contextError}</p> : context && <>
        <div className="assistant-count"><strong>{context.profile.wardrobe_size}</strong><span>pièces dans ton dressing</span></div>
        <div className="style-chips">{context.profile.favorite_colors.map((c) => <span key={c}>● {c}</span>)}{context.profile.favorite_styles.map((s) => <span key={s}>✧ {s}</span>)}</div>
        {context.items.length > 0 ? <><h3>Une pièce en tête ?</h3><div className="assistant-items">{context.items.slice(0, 6).map((i) => <button type="button" key={i.id} disabled={busy} className={topic === "item" && recordId === i.id ? "is-selected" : ""} onClick={() => { setTopic("item"); setRecordId(i.id); composer.current?.focus(); }}>{/^https?:/.test(i.image_url) ? <img src={i.image_url} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : <span className="assistant-piece-icon">✧</span>}<span><b>{i.category ?? "Pièce"}</b><small>{i.colors.join(", ") || "Couleur non renseignée"}</small></span></button>)}</div></> : <div className="assistant-empty-wardrobe"><h3>Ton dressing commence ici</h3><p>Tu peux déjà demander des conseils généraux. Ajoute tes pièces pour des associations plus personnelles.</p><button type="button" className="button button-primary" onClick={() => onNavigate("wardrobe")}>Ajouter ma première pièce</button></div>}
      </>}
      <button type="button" className="text-button" disabled={loading || busy} onClick={() => void refresh()}>↻ Actualiser mon dressing</button>
    </aside>
    <section className="content-card assistant-conversation"><div className="assistant-heading"><div><span className="eyebrow">TON ASSISTANT STYLE</span><h2>On en parle ?</h2></div><button type="button" className="text-button" disabled={busy || !turns.length} onClick={() => setTurns([])}>Nouvelle conversation</button></div>
      <div className="assistant-thread" ref={thread} role="log" aria-label="Conversation avec ton assistant" aria-live="polite">
        {!turns.length && <div className="assistant-welcome"><span className="llm-spark" aria-hidden="true">✦</span><h3>Qu’est-ce qu’on imagine aujourd’hui ?</h3><p>Dis-moi ce que tu veux porter, l’occasion ou ce qui te bloque. Tu peux ensuite préciser : « plus simple », « sans talons », « avec mes pièces seulement »…</p></div>}
        {turns.map((turn) => <div className="assistant-turn" key={turn.id}><div className="assistant-question"><small>TOI · {topics.find((t) => t.id === turn.topic)?.label}</small><p>{turn.question}</p></div><div className="assistant-reply" ref={turn.id === turns[turns.length - 1]?.id ? latestReply : undefined}><span className="assistant-mark" aria-hidden="true">✦</span><div>{turn.error ? <p role="alert">{turn.error}</p> : !turn.answer ? <p role="status">Je prépare des pistes pour toi…</p> : turn.answer.status === "unavailable" ? <div><p>{turn.answer.failure_reason === "rate_limit" ? "Le service IA a atteint sa limite d’appels. Patiente un moment puis reprends ta question." : "L’assistant n’a pas pu répondre. Réessaie dans quelques instants."}</p><button type="button" className="text-button" disabled={busy} onClick={() => { setTopic(turn.topic); setRecordId(turn.recordId); setMessage(turn.question); composer.current?.focus(); }}>Reprendre cette question →</button></div> : <>
          {turn.answer.decision && <div className="assistant-decision"><strong>Verdict enregistré : {turn.answer.decision.label} · {turn.answer.decision.score}/100</strong><details><summary>Voir l’analyse d’origine</summary><p>{turn.answer.decision.rationale}</p></details></div>}
          <p>{turn.answer.explanation}</p>
          {!!turn.answer.ideas?.length && <div className="assistant-ideas"><span className="eyebrow">PISTES DE STYLE</span>{turn.answer.ideas.map((idea, i) => <article key={i} className="assistant-idea"><h3><span>{String(i + 1).padStart(2, "0")}</span>{idea.title}</h3><p>{idea.advice}</p>{!!idea.items.length && <div className="assistant-owned"><small>Dans ton dressing</small><div className="style-chips">{idea.items.map((item) => <span key={item.id}>{item.label}</span>)}</div></div>}{!!idea.optional_additions.length && <p className="assistant-optional"><strong>Optionnel · à prévoir :</strong> {idea.optional_additions.join(" ; ")}</p>}</article>)}</div>}
          {turn.answer.follow_up && <p className="assistant-follow-up">{turn.answer.follow_up}</p>}
          {turn.answer.status === "success" && <details><summary>Sur quoi je m’appuie</summary>{turn.answer.evidence.map((source) => <p key={source.label}><strong>{source.label}</strong> · {source.detail}</p>)}</details>}
        </>}</div></div></div>)}
      </div>
      <form className="assistant-composer" onSubmit={(event) => void send(event)}><div className="assistant-topics" role="group" aria-label="Sujet de la conversation">{topics.map((t) => <button key={t.id} type="button" disabled={busy} aria-pressed={topic === t.id} onClick={() => chooseTopic(t.id)}>{t.label}</button>)}</div>
        {topic !== "wardrobe" && <label className="assistant-record">{topic === "item" ? "La pièce dont on parle" : topic === "outfit" ? "La tenue dont on parle" : "L’achat dont on parle"}<select aria-label="Élément sélectionné" value={recordId} disabled={busy} onChange={(e) => setRecordId(e.target.value)}><option value="">Choisir…</option>{options?.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label>}
        {missingSelection ? <p className="assistant-context-note">{options?.length ? "Sélectionne un élément ci-dessus pour en parler." : topic === "outfit" ? "Tu n’as pas encore de tenue enregistrée." : topic === "purchase" ? "Tu n’as pas encore d’achat analysé." : "Tu n’as pas encore de pièce enregistrée."}{!options?.length && <button type="button" className="text-button" onClick={() => onNavigate(topic === "outfit" ? "outfits" : topic === "purchase" ? "purchase" : "wardrobe")}>Ouvrir {topic === "outfit" ? "Idées de looks" : topic === "purchase" ? "J’achète ou pas ?" : "Mon dressing"} →</button>}</p> : <div className="assistant-suggestions">{suggestions.map((s) => <button type="button" key={s} disabled={busy} onClick={() => { setMessage(s); composer.current?.focus(); }}>{s}</button>)}</div>}
        <label className="assistant-wardrobe-only"><input type="checkbox" checked={wardrobeOnly} disabled={busy} onChange={(e) => setWardrobeOnly(e.target.checked)} /> Utiliser uniquement les pièces de mon dressing</label>
        <label className="assistant-message-label" htmlFor="assistant-message">Ta question</label><div className="assistant-input"><textarea id="assistant-message" ref={composer} rows={2} maxLength={1500} value={message} disabled={busy || loading || !!contextError || missingSelection} onChange={(e) => setMessage(e.target.value)} placeholder="Comment porter cette pièce ? Et si je voulais un look plus habillé ?" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} /><button type="submit" className="button button-primary" disabled={busy || loading || !context || missingSelection || !message.trim()}>{busy ? "…" : "Envoyer ↗"}</button></div><p className="assistant-footnote">Des pistes à adapter à tes envies. Les compléments suggérés ne sont pas forcément dans ton dressing.</p>
      </form>
    </section>
  </div>;
}
