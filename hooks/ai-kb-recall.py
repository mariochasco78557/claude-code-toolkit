#!/usr/bin/env python3
"""UserPromptSubmit hook: route the prompt through a curated ROUTER.md (topic -> pages / KB ids).

Order: (a) score ROUTER.md lines by keyword overlap (ES/EN), inject the best 1-2 as
[ROUTER] (<=820 chars); (b) only if no line reaches THRESHOLD, fall back to a knowledge-base
search (<=1 vault index line + 2 kb hits, <=700 chars); (c) total <=1200 chars;
(d) short prompts / slash commands / notifications get nothing.
Hard wall-clock budget ~2.6 s; any failure -> silent (never blocks the prompt).
Light ES/EN stemming on prompt + keywords; synonyms and overflow keywords in
$FLOWARA_AI_OS_ROOT/ops/router_synonyms.json (inline fallback); money synonyms need a money word;
each prompt stem counts once per line; IDF-like rarity tie-break; threshold on raw evidence.
A sole line with a single weak keyword is injected as tentative "[ROUTER~]".
Every real (non --dry-run) prompt appends one JSON line to ~/.cache/ai-kb-recall/decisions.jsonl
(local only, 0600, rotated at 2 MB to .1).

Env: FLOWARA_AI_OS_ROOT (vault with ROUTER.md, default $HOME/vault),
     AI_KB_ROOT (knowledge-feeds checkout, default $HOME/ai-knowledge-feeds).

CLI: ai-kb-recall.py --dry-run "<prompt>" [--json]   (prints what would be injected; never logs)
"""
from __future__ import annotations
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
import unicodedata

VERSION = "2.3"


def _root(env: str, default: str) -> str:
    """Env var first, then the generic default under $HOME ("" if neither exists)."""
    for cand in (os.environ.get(env, ""), os.path.join(str(pathlib.Path.home()), default)):
        if cand and os.path.isdir(cand):
            return cand
    return ""


def _uv() -> str:
    import shutil
    for cand in (shutil.which("uv"), str(pathlib.Path.home() / ".local/bin/uv"),
                 "/opt/homebrew/bin/uv", "/usr/local/bin/uv"):
        if cand and os.access(cand, os.X_OK):
            return cand
    return ""


FLOWARA_DIR = _root("FLOWARA_AI_OS_ROOT", "vault")
KB_DIR = _root("AI_KB_ROOT", "ai-knowledge-feeds")
UV = _uv()
KB_OK = bool(KB_DIR and UV)  # no KB CLI (e.g. Mac without the KB) -> router lines only
ROUTER_MD = os.path.join(FLOWARA_DIR, "ROUTER.md") if FLOWARA_DIR else ""
CACHE = pathlib.Path.home() / ".cache/ai-kb-recall/router.json"
# Decision log (local only, never synced; ~/.cache is outside every rsync/rclone job). Env override for tests.
LOG = pathlib.Path(os.environ.get("AI_KB_RECALL_LOG", "") or pathlib.Path.home() / ".cache/ai-kb-recall/decisions.jsonl")
LOG_MAX = 2 * 1024 * 1024

SYN_JSON = os.path.join(FLOWARA_DIR, "ops/router_synonyms.json") if FLOWARA_DIR else ""

# Inline fallback, used only if ops/router_synonyms.json is missing or unreadable (keep roughly in
# sync; the JSON is the curated source). No generic verbs (pedir, editar) and money targets gated.
SYN_FALLBACK = {
    "money_targets": ["pricing"],
    "money_prefixes": ["euro", "eur", "price", "pricing", "cost", "usd", "precio", "coste", "cuesta"],
    "words": {
        "bot": "agent", "chatbot": "agent", "assistant": "agent", "asistente": "agent",
        "remember": "memory", "recordar": "memory", "olvida": "memory",
        "connect": "mcp", "conectar": "mcp", "integrar": "mcp",
        "enganchar": "hook", "testear": "eval", "probarlo": "eval", "fallar": "failure",
    },
    "phrases": {
        "inicio de sesion": "sessionstart", "at session start": "sessionstart",
        "responde bien": "eval", "funciona bien": "eval",
    },
    "extra_keywords": {},
}
SYN_W = 0.75             # a synonym hit scores this fraction of the keyword it names
IDF_TIE = 0.2            # rarity bonus: a keyword found in df router lines adds w*IDF_TIE/df (tie-break only)
# THRESHOLD is on the raw evidence (sum of keyword weights x synonym/ES-EN factors, before the IDF
# bonus). 2.0 = one !strong keyword, one phrase, or two plain keywords. Below it the router line is
# a guess, so nothing from the router is injected and the kb fallback (limit 2) decides instead.
THRESHOLD = 2.0
TIE_RATIO = 0.70         # near-tie: the 2nd line is injected too if its (IDF-adjusted) score >= this x best
TENT_MIN = 0.75          # tentative line: its one keyword must be direct or a synonym (ES->EN-only 0.5 is too weak)
TENT_MIN_LEN = 40        # ... and the prompt at least this long (short prompts stay silent)
ROUTER_MAX, KB_MAX, TOTAL_MAX = 820, 700, 1200  # head ~150 + 2 lines <= 2x320
BUDGET_S = 2.6
ABBR = {"cc:": "docs:anthropic-claude-code-docs:", "pf:": "docs:anthropic-platform-docs:"}

GATE = re.compile(
    r"\b(claude|codex|anthropic|opus|sonnet|haiku|fable|gpt|llm|mcp|hooks?|subagent\w*|agent\w*|"
    r"agente\w*|skills?|plugins?|prompt\w*|context\w*|contexto|memor\w+|n8n|automat\w+|"
    r"workflow\w*|playbook\w*|headless|token\w*|sdk|api|rag|embedding\w*|vector\w*|cron|routine\w*|/goal|"
    r"cli|eval\w*|segundo\s+cerebro|second\s+brain|ai\s+os|sistema\s+operativo|operating\s+system|"
    r"subagente\w*|equipos?\s+de\s+agentes|plantilla\w*|templates?|integraci\w+|integrations?|"
    r"fiabilidad|reliab\w+|confianza|trust\w*|seguridad|security|rgpd|gdpr|guardrail\w*|"
    r"contenido\w*|content|guion\w*|guiones|script\w*|v[ií]deos?|marketing|marca|brand\w*|"
    r"ventas|sales|funnel|crm|atenci[oó]n\s+al\s+cliente|customer\s+(?:support|service)|soporte|support|reclutamiento|recruit\w*|"
    r"voz|voice|tts|clonaci[oó]n|clon\w*|interfaz|dashboard\w*|"
    r"agencia|agency|clientes?|clients?|precios?|pricing|oferta|offer|pymes?|negocios?|business|onboarding|"
    r"engine|booking|reservas?|whatsapp)\b",
    re.I,
)
STOP = set("""
the and for with that this from what how can does into your have about when then them they
there their would could should will just like want need make using used use are was were
que los las del por para con una uno unos unas como pero sus esta este esto estos estas
hay ser son muy mas más cuando donde quiero quieres puedes puede hacer hace haz dime sobre
tambien también porque cual cuál todo toda todos todas algo alguna alguno mismo misma cada
entre desde hasta bien aqui aquí ahora vale okay please gracias entonces tengo tiene tienes
tenemos siempre través traves forma manera esto eso esa ese hemos habiamos habíamos estaba
podriamos podríamos sin ver veas dejar listo poco etc
""".split())

# The corpus is English; Spanish prompts are mapped to English keywords.
ES_EN = {
    "sesion": "session", "sesiones": "session", "memoria": "memory", "herramienta": "tool",
    "herramientas": "tool", "automatica": "automatic", "automatico": "automatic",
    "automatizacion": "automation", "automatizar": "automate", "automatizamos": "automation",
    "agente": "agent", "agentes": "agents", "busqueda": "search", "buscar": "search",
    "resumen": "summary", "resumenes": "summary", "base": "knowledge", "datos": "data",
    "conocimiento": "knowledge", "indice": "index", "contexto": "context", "seguridad": "security",
    "permisos": "permissions", "ganchos": "hooks", "flujo": "workflow", "coste": "cost",
    "costes": "cost", "tokens": "token", "modelo": "model", "modelos": "models",
    "informacion": "information", "actualizar": "update", "actualizacion": "update",
    "segundo": "second", "cerebro": "brain", "evaluacion": "evals", "evaluaciones": "evals",
    "fiabilidad": "reliability", "confianza": "trust", "plantilla": "template", "plantillas": "templates",
    "integracion": "integration", "integraciones": "integrations", "contenido": "content",
    "contenidos": "content", "guion": "script", "guiones": "script", "video": "video", "videos": "video",
    "vídeo": "video", "vídeos": "video", "marca": "brand", "ventas": "sales", "venta": "sales",
    "atencion": "support", "soporte": "support", "reclutamiento": "recruiting", "voz": "voice",
    "clonacion": "voice-cloning", "interfaz": "interface", "agencia": "agency", "cliente": "client",
    "clientes": "client", "precio": "pricing", "precios": "pricing", "oferta": "offer",
    "pyme": "smallbusiness", "negocio": "business", "negocios": "business", "reservas": "booking",
    "reserva": "booking", "subagente": "subagent", "subagentes": "subagents", "sistema": "system",
    "operativo": "operating", "equipos": "teams", "equipo": "team",
    "programar": "schedule", "programado": "scheduled", "tarea": "task", "tareas": "tasks",
}
GENERIC = {"claude", "code", "codex", "anthropic", "chatgpt", "openai"}

class Budget(Exception):
    pass


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens_of(text: str) -> list[str]:
    return [t.strip(".-/") or t for t in re.findall(r"[a-z0-9/][a-z0-9._\-/]*", text)]


# Light ES/EN stemmer, applied to prompt tokens, router keywords and synonym keys alike: strip the
# longest listed suffix that leaves >= MIN_STEM letters (one pass; words <= MIN_STEM untouched, so
# api/mcp/vps/ram stay intact). Covers plurals, -ción/-ciones, infinitives, common verb endings, -ing/-ed.
MIN_STEM = 4
SUFFIXES = sorted("""
aciones iciones amientos imientos amiento imiento ariamos eriamos iriamos aremos eremos iremos
ciones acion icion cion mente ando iendo arlos arlas arles arlo arla arle erlo erle irlo irle
ados adas idos idas aron ieron amos emos imos aria eria iria ores ado ada ido ida
ar er ir or es os as a o e s ations ation ings ing ed ers
""".split(), key=len, reverse=True)


def stem(w: str) -> str:
    if len(w) <= MIN_STEM or not w.isalpha():
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= MIN_STEM:
            return w[:-len(suf)]
    return w


def stem_phrase(p: str) -> str:
    return " ".join(stem(x) for x in p.split())


def load_synonyms() -> dict:
    try:
        d = json.loads(pathlib.Path(SYN_JSON).read_text(encoding="utf-8"))
        assert isinstance(d.get("words"), dict) and isinstance(d.get("phrases"), dict)
    except Exception:
        d = SYN_FALLBACK
    words = {}
    for k, v in d["words"].items():
        k, v = norm(k), norm(v)
        words[k] = v
        words.setdefault(stem(k), v)
    phrases = {}
    for k, v in d["phrases"].items():
        phrases[norm(k)] = norm(v)
        phrases.setdefault(stem_phrase(norm(k)), norm(v))
    return {"words": words, "phrases": phrases,
            "money_targets": {norm(x) for x in d.get("money_targets", [])},
            "money_prefixes": tuple(norm(x) for x in d.get("money_prefixes", [])) or ("\0",),
            "extra": d.get("extra_keywords", {}) or {}}


# ---------------------------------------------------------------- router parsing + cache
def parse_kws(kwcol: str) -> list[list]:
    kws = []
    for k in kwcol.split(","):
        k = norm(k.strip())
        if not k:
            continue
        w = 2.0 if k.startswith("!") else 1.0
        k = k.lstrip("!")
        if " " in k:
            kind, w = "phrase", w + 1.0  # phrase 2, !phrase 3
        elif k.endswith("*"):
            kind, k = "prefix", k[:-1]
        else:
            kind = "word"
        kws.append([k, w, kind, stem_phrase(k) if kind == "phrase" else (k if kind == "prefix" else stem(k))])
    return kws


def parse_router(extra: dict | None = None) -> list[dict]:
    if extra is None:
        extra = load_synonyms()["extra"]
    pages = {}
    root = pathlib.Path(FLOWARA_DIR)
    for f in root.rglob("*.md"):
        if ".git" not in f.parts:
            rel = f.relative_to(root)
            pages.setdefault(f.stem, str(rel)[5:] if rel.parts[0] == "wiki" else str(rel))
    routes = []
    for ln in pathlib.Path(ROUTER_MD).read_text(encoding="utf-8").splitlines():
        if not re.match(r"^R\d+ \|", ln):
            continue
        cols = [c.strip() for c in ln.split(" | ")]
        if len(cols) != 7:
            continue
        rid, topic, kwcol, vault, kb, owner, auth = cols
        kws = parse_kws(kwcol + "," + extra.get(rid, ""))
        links = re.findall(r"\[\[([^\]|#]+)", vault)
        for a, full in ABBR.items():
            kb = re.sub(r"(?<![\w:])" + re.escape(a), full, kb)
        routes.append({
            "id": rid, "topic": topic, "kws": kws,
            "paths": [pages.get(x.strip(), x.strip() + ".md") for x in links],
            "kb": "" if kb == "-" else kb, "owner": "" if owner == "-" else owner,
            "auth": auth,
        })
    # IDF-like rarity, computed once here and cached: df = number of router lines whose keywords
    # (including the words inside phrases) contain this stem. Strongest keywords are tried first.
    df: dict[str, int] = {}
    for r in routes:
        seen = set()
        for k, w, kind, sk in r["kws"]:
            seen.add(sk)
            if kind == "phrase":
                seen.update(x for x in sk.split() if len(x) >= MIN_STEM)
        for x in seen:
            df[x] = df.get(x, 0) + 1
    for r in routes:
        r["kws"] = sorted(([k, w, kind, sk, round(1.0 / df.get(sk, 1), 3)] for k, w, kind, sk in r["kws"]),
                          key=lambda x: (-x[1], x[2] != "phrase"))
    return routes


def load_routes() -> list[dict]:
    st = os.stat(ROUTER_MD)
    try:
        sj = os.stat(SYN_JSON)
        sj_key = f"{sj.st_mtime_ns}:{sj.st_size}"
    except OSError:
        sj_key = "-"
    key = f"{VERSION}:{FLOWARA_DIR}:{st.st_mtime_ns}:{st.st_size}:{sj_key}"
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if data.get("key") == key:
            return data["routes"]
    except Exception:
        pass
    routes = parse_router()
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"key": key, "routes": routes}), encoding="utf-8")
        os.replace(tmp, CACHE)
    except Exception:
        pass
    return routes


# ---------------------------------------------------------------- scoring
def score_routes(prompt: str, routes: list[dict], syn: dict | None = None) -> list[tuple[float, float, dict, int]]:
    """-> [(adjusted score, raw evidence, route, n keyword hits)] sorted best first. Each prompt stem counts at most
    once per route (strongest keyword wins), so 'agente' cannot score twice via agente+agent."""
    syn = syn or load_synonyms()
    text = norm(prompt[:2000])
    toks = set(tokens_of(text))
    st = {t: stem(t) for t in toks}
    stems = set(st.values())
    fw = re.findall(r"[a-z0-9._\-/]+", text)
    flat = " " + " ".join(fw) + " "
    sflat = " " + " ".join(stem(x) for x in fw) + " "
    mapped = {norm(ES_EN[t]) for t in toks if t in ES_EN} - toks
    mstems = {stem(m) for m in mapped}
    money = bool(re.search(r"[€$]", prompt)) or any(t.startswith(syn["money_prefixes"]) for t in toks)

    hits: dict[str, str] = {}  # synonym target keyword -> the prompt stem/phrase that produced it
    for t in toks:
        v = syn["words"].get(t) or syn["words"].get(st[t])
        if v and (money or v not in syn["money_targets"]):
            hits.setdefault(v, st[t])
    for p, v in syn["phrases"].items():
        if (f" {p} " in flat or f" {p} " in sflat) and (money or v not in syn["money_targets"]):
            hits.setdefault(v, "p:" + p)

    out = []
    for r in routes:
        used: set = set()
        raw = adj = 0.0
        n = 0
        for k, w, kind, sk, idf in r["kws"]:
            f, cons = 1.0, None
            if kind == "phrase":
                if f" {k} " in flat or f" {sk} " in sflat:
                    cons = {"p:" + sk} | set(sk.split())
            elif kind == "prefix":
                cons = {st[t] for t in toks if t.startswith(k)} or None
            elif k in toks or sk in stems:
                cons = {sk}
            elif len(k) >= 5:
                cons = {st[t] for t in toks if t.startswith(k) and len(t) - len(k) <= 3} or None
            if cons is None:
                src = hits.get(k)
                if src is None and kind == "prefix":
                    src = next((s for x, s in hits.items() if x.startswith(k)), None)
                if src is not None:
                    f, cons = SYN_W, {src}
                elif kind != "phrase" and mstems and (
                        sk in mstems or (kind == "prefix" and any(m.startswith(k) for m in mapped))):
                    f, cons = 0.5, {"m:" + sk}
            if cons is None or cons <= used:
                continue
            used |= cons
            raw += w * f
            adj += w * f * (1 + IDF_TIE * idf)
            n += 1
        if raw > 0:
            out.append((adj + 0.01 * n, raw, r, n))
    out.sort(key=lambda x: -x[0])
    return out


def fmt_route(r: dict, tentative: bool = False) -> str:
    parts = [f"[ROUTER~ tentative, weak match] {r['id']} {r['topic']}" if tentative
             else f"[ROUTER] {r['id']} {r['topic']}"]
    if r["paths"]:
        parts.append("→ " + ", ".join(r["paths"]))
    if r["kb"]:
        parts.append("| kb " + r["kb"])
    if r["owner"]:
        parts.append("| owner " + r["owner"])
    parts.append("| " + r["auth"])
    return " ".join(parts)


ROUTER_HEAD = (f"Knowledge router (paths under {FLOWARA_DIR}/wiki/; open ONLY what a line names; "
               "kb ids → ai-kb kb_get):")


# ---------------------------------------------------------------- kb fallback helpers
def prompt_terms(prompt: str) -> list[str]:
    terms, seen = [], set()
    for w in re.findall(r"[\wáéíóúñ][\w\-áéíóúñ]{3,}", prompt.lower()):
        if w not in STOP and w not in seen and not w.isdigit():
            seen.add(w)
            terms.append(w)
    terms = list(dict.fromkeys(ES_EN.get(w, w) for w in terms))
    terms.sort(key=lambda w: 0 if GATE.fullmatch(w) else 1)
    strong = [t for t in terms if GATE.fullmatch(t) or t in set(ES_EN.values())]
    return strong if len(strong) >= 2 else terms


def flowara_hits(terms: list[str], limit: int = 1) -> list[str]:
    root = pathlib.Path(FLOWARA_DIR)
    lines = []
    for ln in (root / "index.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \[\[([^\]|]+)\]\]\s*(.*)", ln)
        if m:
            lines.append((ln.lower(), m.group(1), m.group(2)))
    terms = [t for t in terms if t not in GENERIC]
    df = {t: sum(1 for low, _, _ in lines if t in low) for t in terms}
    scored = []
    for low, page, summ in lines:
        hit = [t for t in terms if t in low]
        w = sum(1 if df[t] <= 3 else 0.5 for t in hit)
        if w >= 1.5 or any(df[t] <= 3 and len(t) >= 6 for t in hit):
            scored.append((w, page, summ))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, page, summ in scored[:limit]:
        f = next(root.glob(f"wiki/**/{page}.md"), None)
        where = str(f.relative_to(root)) if f else page
        out.append(f"- {where} {summ.lstrip('— ').strip()}"[:200])
    return out


def kb_search(q: list[str], deadline: float, source: str | None = None, limit: int = 2) -> list[str]:
    left = deadline - time.monotonic()
    if not KB_OK or left < 0.3 or not q:
        return []
    cmd = [UV, "run", "--quiet", "--directory", KB_DIR, "kb", "search", *q, "--limit", str(limit + 1)]
    if source:
        cmd += ["--source", source]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=min(1.5, left)).stdout
    except Budget:
        raise
    except Exception:
        return []
    return [ln.strip() for ln in out.splitlines()
            if re.match(r"\s*\d+\.\s", ln) and "(same item" not in ln][:limit]


def widen(terms: list[str], deadline: float, source: str | None, limit: int):
    for q in (terms[:5], terms[:2], terms[:1]):
        if q:
            h = kb_search(q, deadline, source, limit)
            if h:
                return q, h
    return [], []


def fit(lines: list[str], cap: int) -> str:
    """Keep whole lines while they fit under cap."""
    out, n = [], 0
    for ln in lines:
        add = len(ln) + (1 if out else 0)
        if n + add > cap:
            break
        out.append(ln)
        n += add
    return "\n".join(out)


# ---------------------------------------------------------------- main logic
def build(prompt: str, info: dict) -> str:
    deadline = time.monotonic() + BUDGET_S - 0.2
    if ("<task-notification>" in prompt or "[SYSTEM NOTIFICATION" in prompt
            or len(prompt) < 15 or prompt.lstrip().startswith("/")):
        info["path"] = "gate"
        return ""
    blocks: list[str] = []
    try:
        ranked = score_routes(prompt, load_routes())
    except Exception:
        ranked = []
    info["scores"] = [(r["id"], round(s, 2)) for s, _, r, _ in ranked[:5]]
    tentative = (len(ranked) == 1 and ranked[0][3] == 1 and TENT_MIN <= ranked[0][1] < THRESHOLD
                 and len(prompt.strip()) >= TENT_MIN_LEN)
    if ranked and ranked[0][1] >= THRESHOLD:
        top = ranked[0][0]
        # Best line always; the 2nd only on a near-tie. Never a 3rd (cost > benefit on the eval sets).
        picked = [ranked[0]] + [x for x in ranked[1:2] if x[0] >= TIE_RATIO * top]
        chosen = [r for _, _, r, _ in picked]
        router_txt = fit([ROUTER_HEAD] + [fmt_route(r) for r in chosen], ROUTER_MAX)
        chosen = [r for r in chosen if r["id"] + " " in router_txt]
        info["routes"] = [r["id"] for r in chosen]
        info["chosen"] = [(r["id"], round(s, 2)) for s, _, r, _ in picked if r in chosen]
        info["path"] = "router"
        blocks.append(router_txt)
    elif tentative or GATE.search(prompt):
        lines: list[str] = []
        if tentative:  # one weak keyword on one line: show it, marked "~"; the kb fallback may follow
            s0, _, r0, _ = ranked[0]
            blocks.append(fit([ROUTER_HEAD, fmt_route(r0, True)], ROUTER_MAX))
            info.update(routes=[r0["id"]], chosen=[(r0["id"], round(s0, 2))], tentative=True, path="tentative")
        if not GATE.search(prompt):
            return fit("\n".join(blocks).split("\n"), TOTAL_MAX)
        info["path"] = "tentative+kb" if tentative else "kb"
        terms = prompt_terms(prompt)
        try:
            wiki = flowara_hits(terms[:10], 1)
        except Exception:
            wiki = []
        if wiki:
            lines += ["Vault wiki (curated, read first; under " + FLOWARA_DIR + "):"] + wiki
        try:
            q, hits = widen(terms, deadline, None, 2)
        except Budget:
            q, hits = [], []
        if hits:
            lines += [f"Knowledge feeds (MCP ai-kb) [{' '.join(q)}]; kb_get(id, chunk=N); "
                      "canonical outranks practice:"] + [h[:200] for h in hits]
        if lines:
            blocks.append(fit(lines, KB_MAX))
            info["fallback"] = True
    else:
        info["path"] = "none"
    return fit("\n".join(b for b in blocks if b).split("\n"), TOTAL_MAX)


def on_alarm(signum, frame):
    raise Budget()


def log_decision(prompt: str, info: dict, text: str, t0: float) -> None:
    """Append one JSON line per prompt (local only, 0600). Rotate to .1 above LOG_MAX. Never raises."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            if LOG.stat().st_size > LOG_MAX:
                os.replace(LOG, LOG.with_name(LOG.name + ".1"))
        except FileNotFoundError:
            pass
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "v": VERSION, "prompt_len": len(prompt),
               "prompt": " ".join(prompt[:120].split()), "path": info.get("path", "error"),
               "lines": [{"id": i, "score": sc} for i, sc in info.get("chosen", [])],
               "tentative": bool(info.get("tentative")), "fallback": bool(info.get("fallback")),
               "injected_chars": len(text), "ms": round((time.monotonic() - t0) * 1000)}
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main() -> None:
    if "--dry-run" in sys.argv:
        i = sys.argv.index("--dry-run")
        prompt = sys.argv[i + 1] if len(sys.argv) > i + 1 else ""
        info: dict = {"routes": [], "scores": [], "path": ""}
        t0 = time.monotonic()
        text = build(prompt, info)
        info.update(text=text, chars=len(text), tokens_est=round(len(text) / 4),
                    ms=round((time.monotonic() - t0) * 1000))
        if "--json" in sys.argv:
            print(json.dumps(info, ensure_ascii=False))
        else:
            print(text or "(nothing injected)")
            print(f"--- path={info['path']} routes={info['routes']} chars={info['chars']} "
                  f"tokens≈{info['tokens_est']} ms={info['ms']} top={info['scores'][:3]}")
        return
    t0 = time.monotonic()
    signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, BUDGET_S)
    text, prompt, info = "", None, {}
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
        text = build(prompt, info)
    except BaseException:
        text = ""
        info.setdefault("path", "error")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if isinstance(prompt, str):
        log_decision(prompt, info, text, t0)
    if text:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
