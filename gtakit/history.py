"""Histórico de produção (data/history.jsonl, fora do Git) e métricas do YouTube Studio (CSV, sem API).

Cada compilado vira uma linha: clipes usados (post, autor, criador original), duração, tempo de render,
link do YouTube (quando o usuário publica) e métricas importadas do CSV exportado do YouTube Studio.
"""
import csv
import json
import os
import pathlib
import re

# GTAKIT_HISTORY permite trocar o arquivo (os testes usam um temporário para não sujar o histórico real)
DEFAULT_HISTORY = pathlib.Path(os.environ.get("GTAKIT_HISTORY") or pathlib.Path("data") / "history.jsonl")

# Colunas do CSV do YouTube Studio (português e inglês) -> chave interna
COLUMNS = {
    "video_id": ("conteúdo", "conteudo", "content", "video"),
    "title": ("título do vídeo", "titulo do video", "video title", "título", "title"),
    "views": ("visualizações", "visualizacoes", "views"),
    "watch_hours": ("tempo de exibição (horas)", "tempo de exibicao (horas)", "watch time (hours)"),
    "subscribers": ("inscritos", "subscribers"),
    "impressions": ("impressões", "impressoes", "impressions"),
    "ctr": ("taxa de cliques de impressões (%)", "taxa de cliques de impressoes (%)",
            "impressions click-through rate (%)"),
    "avg_view_duration": ("duração média da visualização", "duracao media da visualizacao", "average view duration"),
}


def load(path=DEFAULT_HISTORY):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def save(entries, path=DEFAULT_HISTORY):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")


def upsert(entries, entry):
    """Substitui a linha do mesmo projeto (slug) ou acrescenta, preservando o link e as métricas já gravados."""
    for i, e in enumerate(entries):
        if e["slug"] == entry["slug"]:
            entry["youtube"] = e.get("youtube") or entry.get("youtube")
            entry["metrics"] = e.get("metrics") or entry.get("metrics")
            entries[i] = entry
            return entries
    entries.append(entry)
    return entries


def _keys(video):
    keys = set()
    if video.get("post_id"):
        keys.add(("post", str(video["post_id"])))
    if video.get("url"):
        keys.add(("url", video["url"].split("?")[0].rstrip("/").lower()))
    if video.get("id"):
        keys.add(("media", str(video["id"])))
    return keys


def used_before(entries, video, exclude_slug=None):
    """Projetos anteriores que já usaram o mesmo post/vídeo."""
    mine = _keys(video)
    out = []
    for e in entries:
        if e["slug"] == exclude_slug:
            continue
        for c in e.get("clips", []):
            if mine & _keys({"post_id": c.get("post_id"), "url": c.get("url"), "id": c.get("video_id")}):
                out.append(e["slug"])
                break
    return out


def youtube_id(url_or_id):
    """ID de 11 caracteres de um link do YouTube (watch?v=, youtu.be/, shorts/) ou do próprio ID."""
    s = (url_or_id or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s) else None


def _num(text):
    """'1.234' / '1,234' / '4,5' / '4.5%' / '0:01:23' -> número (segundos para duração)."""
    s = (text or "").strip().replace("%", "").replace(" ", "")
    if not s or s in ("-", "—"):
        return None
    if re.fullmatch(r"\d+:\d{2}(:\d{2})?", s):
        parts = [int(x) for x in s.split(":")]
        return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
    if "," in s and "." in s:   # o separador que aparece por último é o decimal
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.fullmatch(r"-?\d+,\d{1,2}", s) else s.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):  # 1.234.567 (milhar com ponto)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_studio_csv(path):
    """Linhas do CSV exportado do YouTube Studio (Análises > Avançado > Exportar), PT ou EN."""
    raw = pathlib.Path(path).read_text(encoding="utf-8-sig")
    rows = list(csv.reader(raw.splitlines()))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    idx = {}
    for key, names in COLUMNS.items():          # 1º: nome exato
        for i, h in enumerate(header):
            if h in names and i not in idx.values():
                idx.setdefault(key, i)
    for key, names in COLUMNS.items():          # 2º: começo do nome, só para o que faltou e sem reusar coluna
        if key in idx:                          # (evita ler "Impressions click-through rate" como impressões)
            continue
        for i, h in enumerate(header):
            if i not in idx.values() and any(h.startswith(n) for n in names if len(n) > 8):
                idx[key] = i
                break
    if "video_id" not in idx and "title" not in idx:
        raise ValueError("CSV sem coluna de vídeo ('Conteúdo'/'Content') nem de título")
    out = []
    for r in rows[1:]:
        if not r or (r[0].strip().lower() in ("total", "")):
            continue
        item = {}
        for key, i in idx.items():
            val = r[i] if i < len(r) else ""
            item[key] = val.strip() if key in ("video_id", "title") else _num(val)
        out.append(item)
    return out


def apply_metrics(entries, rows, imported_at):
    """Associa cada linha do CSV a um compilado (pelo ID do YouTube; senão, pelo título). Devolve as não associadas."""
    unmatched = []
    for row in rows:
        target = None
        yid = youtube_id(row.get("video_id"))
        for e in entries:
            y = e.get("youtube") or {}
            if yid and y.get("video_id") == yid:
                target = e
            elif not target and row.get("title") and (y.get("title") or "").strip().lower() == row["title"].strip().lower():
                target = e
        if target is None:
            unmatched.append(row.get("title") or row.get("video_id"))
            continue
        target["metrics"] = {k: v for k, v in row.items() if k not in ("video_id", "title")}
        target["metrics"]["imported_at"] = imported_at
    return unmatched


def report(entries):
    """Texto com o desempenho por compilado e por criador (só com métricas importadas)."""
    lines = [f"{'compilado':<34} {'duração':>8} {'clipes':>6} {'views':>9} {'CTR %':>6} {'h assist.':>9}  link"]
    for e in entries:
        m = e.get("metrics") or {}
        fmt = lambda v, d=0: "-" if v is None else f"{v:,.{d}f}".replace(",", ".")
        lines.append(f"{e['slug'][:34]:<34} {e.get('duration_s', 0) / 60:>7.1f}m {len(e.get('clips', [])):>6} "
                     f"{fmt(m.get('views')):>9} {fmt(m.get('ctr'), 1):>6} {fmt(m.get('watch_hours'), 1):>9}  "
                     f"{(e.get('youtube') or {}).get('url') or 'não publicado'}")
    with_views = [e for e in entries if (e.get("metrics") or {}).get("views") is not None]
    if with_views:
        per = {}
        for e in with_views:
            for c in e.get("clips", []):
                who = c.get("original_creator") or c.get("author_handle") or "?"
                agg = per.setdefault(who, {"compilados": set(), "views": 0.0})
                if e["slug"] not in agg["compilados"]:
                    agg["compilados"].add(e["slug"])
                    agg["views"] += e["metrics"]["views"]
        lines += ["", "Criadores (média de views dos compilados em que aparecem):"]
        for who, agg in sorted(per.items(), key=lambda kv: -kv[1]["views"] / len(kv[1]["compilados"])):
            n = len(agg["compilados"])
            lines.append(f"  {who:<28} {agg['views'] / n:>10,.0f} views em média ({n} compilado(s))".replace(",", "."))
    else:
        lines += ["", "Sem métricas ainda: exporte o CSV do YouTube Studio e rode `gtakit metrics-import <arquivo.csv>`."]
    return "\n".join(lines)
