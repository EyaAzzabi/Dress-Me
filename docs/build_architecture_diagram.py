"""Generates docs/assets/dressme_architecture_current.png: an accurate diagram of the
9 agents actually in backend/app/agents/, replacing the 5-box ideation sketch."""

from pathlib import Path
import cairosvg

HERE = Path(__file__).resolve().parent
OUT_SVG = HERE / "assets" / "dressme_architecture_current.svg"
OUT_PNG = HERE / "assets" / "dressme_architecture_current.png"

RED = "#C90C0F"
DARK = "#1a1a1a"
GRAY = "#555555"
BORDER = "#999999"
LIGHT = "#f7f7f7"
AGENT_FILL = "#fdeceb"

W, H = 1500, 1035


def box(x, y, w, h, fill="#ffffff", stroke=BORDER, rx=8, sw=1.4):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=15, weight="normal", color=DARK, anchor="middle", italic=False):
    style = "italic" if italic else "normal"
    return (f'<text x="{x}" y="{y}" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" font-style="{style}" '
            f'fill="{color}" text-anchor="{anchor}">{esc(s)}</text>')


def wrapped(x, y, lines, size=12.5, color=GRAY, anchor="middle", lh=15):
    out = []
    for i, line in enumerate(lines):
        out.append(text(x, y + i * lh, line, size=size, color=color, anchor=anchor))
    return "\n".join(out)


def arrow(x1, y1, x2, y2, color="#888888", sw=1.6):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}" marker-end="url(#arrow)"/>')


parts = []
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
parts.append(f'''<defs>
  <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
    <path d="M0,0 L6,3 L0,6 Z" fill="#888888"/>
  </marker>
</defs>''')

# Title
parts.append(text(W / 2, 40, "DressMe: Current Architecture", size=25, weight="bold"))
parts.append(text(W / 2, 64, "Client / API / orchestrator, as implemented in backend/app/", size=13.5, color=GRAY))

# Row 1: User, Frontend, Backend API, External services
r1y = 90
r1h = 110
box_user = (40, r1y, 190, r1h)
box_front = (260, r1y, 260, r1h)
box_api = (550, r1y, 300, r1h)
box_ext = (880, r1y, 580, r1h)

parts.append(box(*box_user, fill=LIGHT))
parts.append(text(box_user[0] + box_user[2] / 2, r1y + 24, "User", size=14.5, weight="bold"))
parts.append(wrapped(box_user[0] + box_user[2] / 2, r1y + 46, ["Adds wardrobe photos,", "asks for outfits/packing,", "checks a purchase"]))

parts.append(box(*box_front, fill=LIGHT))
parts.append(text(box_front[0] + box_front[2] / 2, r1y + 24, "Frontend", size=14.5, weight="bold"))
parts.append(wrapped(box_front[0] + box_front[2] / 2, r1y + 46, ["React web app  /  Expo", "(React Native) mobile app"]))

parts.append(box(*box_api, fill=LIGHT))
parts.append(text(box_api[0] + box_api[2] / 2, r1y + 24, "Backend API  (FastAPI, /api/v1)", size=14.5, weight="bold"))
parts.append(wrapped(box_api[0] + box_api[2] / 2, r1y + 46, ["Auth (JWT), REST endpoints,", "request routing to agents"]))

parts.append(box(*box_ext, fill=LIGHT))
parts.append(text(box_ext[0] + box_ext[2] / 2, r1y + 24, "External services", size=14.5, weight="bold"))
parts.append(wrapped(box_ext[0] + box_ext[2] / 2, r1y + 46,
                      ["OpenWeather (ContextAgent)   ·   Groq / OpenAI (LLMAgent, PurchaseAgent)   ·   Hugging Face / Replicate (TryOnAgent)"],
                      size=12))

parts.append(arrow(box_user[0] + box_user[2], r1y + r1h / 2, box_front[0], r1y + r1h / 2))
parts.append(arrow(box_front[0] + box_front[2], r1y + r1h / 2, box_api[0], r1y + r1h / 2))
parts.append(arrow(box_api[0] + box_api[2], r1y + r1h / 2, box_ext[0], r1y + r1h / 2))

# Row 2: Orchestrator
r2y = r1y + r1h + 40
orch = (260, r2y, 980, 55)
parts.append(box(*orch, fill=RED, stroke=RED))
parts.append(text(orch[0] + orch[2] / 2, r2y + 35, "AgentOrchestrator  (backend/app/agents/orchestrator.py)", size=16, weight="bold", color="#ffffff"))
parts.append(arrow(box_api[0] + box_api[2] / 2, r1y + r1h, box_api[0] + box_api[2] / 2, r2y, sw=2))

# Row 3: 9 agents, 3x3 grid
agents = [
    ("VisionAgent", "Clothing attribute extraction", "+ embedding (FashionCLIP)"),
    ("MetadataAgent", "Digital wardrobe CRUD,", "search/filters, usage history"),
    ("StyleProfileAgent", "Learns favorite styles/colors", "from the user's wardrobe"),
    ("ContextAgent", "Occasion / weather / season", "context resolution"),
    ("RecommendationAgent", "Outfit generation, scored by", "compatibility + ranking model"),
    ("PackingAgent", "Suitcase list from trip", "length / type / season"),
    ("PurchaseAgent", "\"Should I buy this?\": LLM", "tool-calling over wardrobe/catalog"),
    ("TryOnAgent", "Virtual try-on", "(free HF Space, or Replicate)"),
    ("LLMAgent", "Conversation & explanations", "(Groq), optional by default"),
]

r3y = r2y + 55 + 45
cols, rows = 3, 3
gap = 24
grid_w = 1500 - 80
cell_w = (grid_w - gap * (cols - 1)) / cols
cell_h = 112
grid_x0 = 40

for idx, (name, l1, l2) in enumerate(agents):
    col = idx % cols
    row = idx // cols
    x = grid_x0 + col * (cell_w + gap)
    y = r3y + row * (cell_h + gap)
    parts.append(box(x, y, cell_w, cell_h, fill=AGENT_FILL, stroke=RED, sw=1.3))
    parts.append(text(x + cell_w / 2, y + 28, name, size=14.5, weight="bold", color=RED))
    parts.append(wrapped(x + cell_w / 2, y + 52, [l1, l2], size=12))
    # connector from orchestrator to each agent's top-row cell, and down the grid implicitly
    if row == 0:
        parts.append(arrow(x + cell_w / 2, r2y + 55, x + cell_w / 2, y, sw=1.3))

grid_bottom = r3y + rows * cell_h + (rows - 1) * gap

# vertical connectors between grid rows (left edge, just to show the grid is one coordinated block)
parts.append(f'<rect x="{grid_x0 - 14}" y="{r3y - 6}" width="{grid_w + 28}" height="{grid_bottom - r3y + 12}" '
             f'fill="none" stroke="{BORDER}" stroke-width="1" stroke-dasharray="4,4" rx="10"/>')
parts.append(text(grid_x0 - 2, r3y - 14, "Specialized agents (coordinated by the orchestrator)", size=12.5, color=GRAY, anchor="start", italic=True))

# Row 4: data stores
r4y = grid_bottom + 45
stores = [
    ("PostgreSQL", "Users, items, outfits,", "calendar, packing, wear log"),
    ("Pinecone", "Item embeddings", "for similarity search"),
    ("S3 / local storage", "Clothing and avatar", "photos"),
]
store_w = (grid_w - gap * 2) / 3
for i, (name, l1, l2) in enumerate(stores):
    x = grid_x0 + i * (store_w + gap)
    parts.append(box(x, r4y, store_w, 80, fill=LIGHT))
    parts.append(text(x + store_w / 2, r4y + 26, name, size=14, weight="bold"))
    parts.append(wrapped(x + store_w / 2, r4y + 48, [l1, l2], size=11.5))
    parts.append(arrow(x + store_w / 2, grid_bottom, x + store_w / 2, r4y, sw=1.3))

parts.append('</svg>')

OUT_SVG.write_text("\n".join(parts), encoding="utf-8")
cairosvg.svg2png(url=str(OUT_SVG), write_to=str(OUT_PNG), output_width=1700)
print("wrote", OUT_PNG)
