import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import { api, getApiError } from "./api";
const topics = [{ id: "wardrobe", label: "Mon dressing" }, { id: "item", label: "Une pièce" }, { id: "outfit", label: "Une tenue" }, { id: "purchase", label: "Un achat" }];
export default function LlmAssistant({ onNavigate }) {
    const [context, setContext] = useState(null);
    const [contextError, setContextError] = useState("");
    const [loading, setLoading] = useState(true);
    const [topic, setTopic] = useState("wardrobe");
    const [recordId, setRecordId] = useState("");
    const [message, setMessage] = useState("");
    const [turns, setTurns] = useState([]);
    const [busy, setBusy] = useState(false);
    const [wardrobeOnly, setWardrobeOnly] = useState(false);
    const thread = useRef(null);
    const latestReply = useRef(null);
    const serial = useRef(0);
    const composer = useRef(null);
    async function refresh() {
        setLoading(true);
        setContextError("");
        try {
            const { data } = await api.get("/llm/context");
            setContext(data);
        }
        catch (error) {
            setContextError(getApiError(error));
        }
        finally {
            setLoading(false);
        }
    }
    useEffect(() => { void refresh(); }, []);
    useEffect(() => {
        const last = turns[turns.length - 1];
        if (!last || !thread.current)
            return;
        const top = (last.answer || last.error) && latestReply.current ? latestReply.current.offsetTop - 16 : thread.current.scrollHeight;
        thread.current.scrollTo({ top, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }, [turns]);
    function chooseTopic(value) {
        setTopic(value);
        setRecordId(value === "item" ? context?.items[0]?.id ?? "" : value === "outfit" ? context?.outfits[0]?.id ?? "" : value === "purchase" ? context?.purchases[0]?.id ?? "" : "");
    }
    async function send(event) {
        event.preventDefault();
        const question = message.trim();
        if (!question || busy || loading || !context || (topic !== "wardrobe" && !recordId))
            return;
        const id = ++serial.current;
        const history = turns.filter((t) => t.answer?.status === "success").slice(-4).flatMap((t) => [
            { role: "user", content: t.question.slice(0, 2000) },
            { role: "assistant", content: [t.answer?.explanation, ...(t.answer?.ideas ?? []).map((i) => `${i.title}: ${i.advice}${i.optional_additions.length ? " Compléments optionnels non confirmés: " + i.optional_additions.join(", ") : ""}`), t.answer?.follow_up].filter(Boolean).join("\n").slice(0, 2000) },
        ]);
        setTurns((current) => [...current, { id, question, topic, recordId }]);
        setMessage("");
        setBusy(true);
        try {
            const { data } = await api.post("/llm/chat", { message: question, topic, record_id: recordId || null, history, wardrobe_only: wardrobeOnly });
            setTurns((current) => current.map((t) => t.id === id ? { ...t, answer: data } : t));
        }
        catch (error) {
            setTurns((current) => current.map((t) => t.id === id ? { ...t, error: getApiError(error) } : t));
        }
        finally {
            setBusy(false);
            composer.current?.focus();
        }
    }
    const options = topic === "item" ? context?.items.map((i) => ({ id: i.id, label: [i.category, ...i.colors].filter(Boolean).join(" · ") })) : topic === "outfit" ? context?.outfits.map((o, i) => ({ id: o.id, label: `${o.occasion ?? "Tenue"} · ${o.item_count} pièces · ${i + 1}` })) : context?.purchases.map((p) => ({ id: p.id, label: [p.category, p.color].filter(Boolean).join(" · ") }));
    const missingSelection = topic !== "wardrobe" && (!options?.length || !recordId);
    const suggestions = topic === "item" ? ["Comment styler cette pièce au quotidien ?", "Et pour une soirée, sans talons ?"] : topic === "outfit" ? ["Comment rendre cette tenue plus habillée ?", "Propose une variante plus décontractée"] : topic === "purchase" ? ["Est-ce que cet achat répond à un vrai besoin ?", "Comment utiliser ce que je possède déjà ?"] : ["Aide-moi à composer une tenue pour un entretien", "Comment apporter de la couleur à mon style ?"];
    return _jsxs("div", { className: "assistant-layout", children: [_jsxs("aside", { className: "content-card assistant-context", children: [_jsx("span", { className: "eyebrow", children: "TON DRESSING, NOTRE POINT DE D\u00C9PART" }), _jsx("h2", { children: "\u00C0 ta fa\u00E7on." }), _jsx("p", { children: "Une pi\u00E8ce \u00E0 r\u00E9inventer, une occasion, une envie de changement ? On construit tes id\u00E9es ensemble." }), loading ? _jsx("p", { role: "status", children: "Je retrouve ton dressing\u2026" }) : contextError ? _jsx("p", { role: "alert", children: contextError }) : context && _jsxs(_Fragment, { children: [_jsxs("div", { className: "assistant-count", children: [_jsx("strong", { children: context.profile.wardrobe_size }), _jsx("span", { children: "pi\u00E8ces dans ton dressing" })] }), _jsxs("div", { className: "style-chips", children: [context.profile.favorite_colors.map((c) => _jsxs("span", { children: ["\u25CF ", c] }, c)), context.profile.favorite_styles.map((s) => _jsxs("span", { children: ["\u2727 ", s] }, s))] }), context.items.length > 0 ? _jsxs(_Fragment, { children: [_jsx("h3", { children: "Une pi\u00E8ce en t\u00EAte ?" }), _jsx("div", { className: "assistant-items", children: context.items.slice(0, 6).map((i) => _jsxs("button", { type: "button", disabled: busy, className: topic === "item" && recordId === i.id ? "is-selected" : "", onClick: () => { setTopic("item"); setRecordId(i.id); composer.current?.focus(); }, children: [/^https?:/.test(i.image_url) ? _jsx("img", { src: i.image_url, alt: "", loading: "lazy", onError: (e) => { e.currentTarget.style.display = "none"; } }) : _jsx("span", { className: "assistant-piece-icon", children: "\u2727" }), _jsxs("span", { children: [_jsx("b", { children: i.category ?? "Pièce" }), _jsx("small", { children: i.colors.join(", ") || "Couleur non renseignée" })] })] }, i.id)) })] }) : _jsxs("div", { className: "assistant-empty-wardrobe", children: [_jsx("h3", { children: "Ton dressing commence ici" }), _jsx("p", { children: "Tu peux d\u00E9j\u00E0 demander des conseils g\u00E9n\u00E9raux. Ajoute tes pi\u00E8ces pour des associations plus personnelles." }), _jsx("button", { type: "button", className: "button button-primary", onClick: () => onNavigate("wardrobe"), children: "Ajouter ma premi\u00E8re pi\u00E8ce" })] })] }), _jsx("button", { type: "button", className: "text-button", disabled: loading || busy, onClick: () => void refresh(), children: "\u21BB Actualiser mon dressing" })] }), _jsxs("section", { className: "content-card assistant-conversation", children: [_jsxs("div", { className: "assistant-heading", children: [_jsxs("div", { children: [_jsx("span", { className: "eyebrow", children: "TON ASSISTANT STYLE" }), _jsx("h2", { children: "On en parle ?" })] }), _jsx("button", { type: "button", className: "text-button", disabled: busy || !turns.length, onClick: () => setTurns([]), children: "Nouvelle conversation" })] }), _jsxs("div", { className: "assistant-thread", ref: thread, role: "log", "aria-label": "Conversation avec ton assistant", "aria-live": "polite", children: [!turns.length && _jsxs("div", { className: "assistant-welcome", children: [_jsx("span", { className: "llm-spark", "aria-hidden": "true", children: "\u2726" }), _jsx("h3", { children: "Qu\u2019est-ce qu\u2019on imagine aujourd\u2019hui ?" }), _jsx("p", { children: "Dis-moi ce que tu veux porter, l\u2019occasion ou ce qui te bloque. Tu peux ensuite pr\u00E9ciser : \u00AB plus simple \u00BB, \u00AB sans talons \u00BB, \u00AB avec mes pi\u00E8ces seulement \u00BB\u2026" })] }), turns.map((turn) => _jsxs("div", { className: "assistant-turn", children: [_jsxs("div", { className: "assistant-question", children: [_jsxs("small", { children: ["TOI \u00B7 ", topics.find((t) => t.id === turn.topic)?.label] }), _jsx("p", { children: turn.question })] }), _jsxs("div", { className: "assistant-reply", ref: turn.id === turns[turns.length - 1]?.id ? latestReply : undefined, children: [_jsx("span", { className: "assistant-mark", "aria-hidden": "true", children: "\u2726" }), _jsx("div", { children: turn.error ? _jsx("p", { role: "alert", children: turn.error }) : !turn.answer ? _jsx("p", { role: "status", children: "Je pr\u00E9pare des pistes pour toi\u2026" }) : turn.answer.status === "unavailable" ? _jsxs("div", { children: [_jsx("p", { children: turn.answer.failure_reason === "rate_limit" ? "Le service IA a atteint sa limite d’appels. Patiente un moment puis reprends ta question." : "L’assistant n’a pas pu répondre. Réessaie dans quelques instants." }), _jsx("button", { type: "button", className: "text-button", disabled: busy, onClick: () => { setTopic(turn.topic); setRecordId(turn.recordId); setMessage(turn.question); composer.current?.focus(); }, children: "Reprendre cette question \u2192" })] }) : _jsxs(_Fragment, { children: [turn.answer.decision && _jsxs("div", { className: "assistant-decision", children: [_jsxs("strong", { children: ["Verdict enregistr\u00E9 : ", turn.answer.decision.label, " \u00B7 ", turn.answer.decision.score, "/100"] }), _jsxs("details", { children: [_jsx("summary", { children: "Voir l\u2019analyse d\u2019origine" }), _jsx("p", { children: turn.answer.decision.rationale })] })] }), _jsx("p", { children: turn.answer.explanation }), !!turn.answer.ideas?.length && _jsxs("div", { className: "assistant-ideas", children: [_jsx("span", { className: "eyebrow", children: "PISTES DE STYLE" }), turn.answer.ideas.map((idea, i) => _jsxs("article", { className: "assistant-idea", children: [_jsxs("h3", { children: [_jsx("span", { children: String(i + 1).padStart(2, "0") }), idea.title] }), _jsx("p", { children: idea.advice }), !!idea.items.length && _jsxs("div", { className: "assistant-owned", children: [_jsx("small", { children: "Dans ton dressing" }), _jsx("div", { className: "style-chips", children: idea.items.map((item) => _jsx("span", { children: item.label }, item.id)) })] }), !!idea.optional_additions.length && _jsxs("p", { className: "assistant-optional", children: [_jsx("strong", { children: "Optionnel \u00B7 \u00E0 pr\u00E9voir :" }), " ", idea.optional_additions.join(" ; ")] })] }, i))] }), turn.answer.follow_up && _jsx("p", { className: "assistant-follow-up", children: turn.answer.follow_up }), turn.answer.status === "success" && _jsxs("details", { children: [_jsx("summary", { children: "Sur quoi je m\u2019appuie" }), turn.answer.evidence.map((source) => _jsxs("p", { children: [_jsx("strong", { children: source.label }), " \u00B7 ", source.detail] }, source.label))] })] }) })] })] }, turn.id))] }), _jsxs("form", { className: "assistant-composer", onSubmit: (event) => void send(event), children: [_jsx("div", { className: "assistant-topics", role: "group", "aria-label": "Sujet de la conversation", children: topics.map((t) => _jsx("button", { type: "button", disabled: busy, "aria-pressed": topic === t.id, onClick: () => chooseTopic(t.id), children: t.label }, t.id)) }), topic !== "wardrobe" && _jsxs("label", { className: "assistant-record", children: [topic === "item" ? "La pièce dont on parle" : topic === "outfit" ? "La tenue dont on parle" : "L’achat dont on parle", _jsxs("select", { "aria-label": "\u00C9l\u00E9ment s\u00E9lectionn\u00E9", value: recordId, disabled: busy, onChange: (e) => setRecordId(e.target.value), children: [_jsx("option", { value: "", children: "Choisir\u2026" }), options?.map((o) => _jsx("option", { value: o.id, children: o.label }, o.id))] })] }), missingSelection ? _jsxs("p", { className: "assistant-context-note", children: [options?.length ? "Sélectionne un élément ci-dessus pour en parler." : topic === "outfit" ? "Tu n’as pas encore de tenue enregistrée." : topic === "purchase" ? "Tu n’as pas encore d’achat analysé." : "Tu n’as pas encore de pièce enregistrée.", !options?.length && _jsxs("button", { type: "button", className: "text-button", onClick: () => onNavigate(topic === "outfit" ? "outfits" : topic === "purchase" ? "purchase" : "wardrobe"), children: ["Ouvrir ", topic === "outfit" ? "Idées de looks" : topic === "purchase" ? "J’achète ou pas ?" : "Mon dressing", " \u2192"] })] }) : _jsx("div", { className: "assistant-suggestions", children: suggestions.map((s) => _jsx("button", { type: "button", disabled: busy, onClick: () => { setMessage(s); composer.current?.focus(); }, children: s }, s)) }), _jsxs("label", { className: "assistant-wardrobe-only", children: [_jsx("input", { type: "checkbox", checked: wardrobeOnly, disabled: busy, onChange: (e) => setWardrobeOnly(e.target.checked) }), " Utiliser uniquement les pi\u00E8ces de mon dressing"] }), _jsx("label", { className: "assistant-message-label", htmlFor: "assistant-message", children: "Ta question" }), _jsxs("div", { className: "assistant-input", children: [_jsx("textarea", { id: "assistant-message", ref: composer, rows: 2, maxLength: 1500, value: message, disabled: busy || loading || !!contextError || missingSelection, onChange: (e) => setMessage(e.target.value), placeholder: "Comment porter cette pi\u00E8ce ? Et si je voulais un look plus habill\u00E9 ?", onKeyDown: (e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                                            e.preventDefault();
                                            e.currentTarget.form?.requestSubmit();
                                        } } }), _jsx("button", { type: "submit", className: "button button-primary", disabled: busy || loading || !context || missingSelection || !message.trim(), children: busy ? "…" : "Envoyer ↗" })] }), _jsx("p", { className: "assistant-footnote", children: "Des pistes \u00E0 adapter \u00E0 tes envies. Les compl\u00E9ments sugg\u00E9r\u00E9s ne sont pas forc\u00E9ment dans ton dressing." })] })] })] });
}
