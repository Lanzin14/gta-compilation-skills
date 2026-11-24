"""Ordem dos clipes, posição de cada um no compilado (clip_start) e capítulos do YouTube."""

MIN_CHAPTER_S = 10.0  # regra do YouTube


def legacy_order(moments, viral):
    """Regra da skill video-editor: abre com o 2º melhor, fecha com o melhor (desempate: viralidade)."""
    sel = sorted([m for m in moments if m.get("selected")],
                 key=lambda m: (-m["score"], -viral.get(m["video_id"], 0)))
    return [sel[1]] + sel[2:] + [sel[0]] if len(sel) > 2 else sel


def clip_starts(entries):
    """entries: [{moment_id, clip_dur}] na ordem. Preenche clip_start (soma das durações anteriores)."""
    t = 0.0
    for e in entries:
        e["clip_start"] = round(t, 3)
        t += e["clip_dur"]
    return entries


def chapters(entries):
    """Capítulos de ≥10 s: clipe curto junta ao seguinte; o último curto junta ao anterior."""
    chap, t, pend = [], 0.0, None
    for e in entries:
        if pend:
            pend["moment_ids"].append(e["moment_id"])
            pend["dur"] += e["clip_dur"]
        else:
            pend = {"start": round(t, 2), "moment_ids": [e["moment_id"]], "dur": e["clip_dur"]}
        t += e["clip_dur"]
        if pend["dur"] >= MIN_CHAPTER_S:
            chap.append(pend)
            pend = None
    if pend:
        if chap:
            chap[-1]["moment_ids"] += pend["moment_ids"]
            chap[-1]["dur"] += pend["dur"]
        else:
            chap.append(pend)
    for c in chap:
        c["dur"] = round(c["dur"], 3)
    return chap


def fmt_ts(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------- ordem otimizada
def _creator(video):
    """Quem 'aparece' no clipe: o criador original (streamer) ou o autor do post."""
    c = (video.get("original_creator") or {}).get("name") or video.get("author_handle") or video.get("id")
    return c.strip().lstrip("@").lower()


def _energy(m):
    crit = (m.get("ranking") or {}).get("criteria")
    if crit:
        return 0.5 * crit["reacao"] + 0.5 * crit["retencao"]
    return float(m.get("score", 0))


def smart_order(moments, videos, max_backtrack=40):
    """Ordem do compilado. Devolve (ordem, notas).

    1. Fecha com o melhor (maior nota; desempate: viralidade, depois id).
    2. Abre com um gancho: maior 0,6×energia + 0,4×nota entre os de nota ≥ mediana, preferindo ≤ 30 s.
    3. Meio: nunca o mesmo criador em sequência (se houver ordem possível); alterna energia
       (bônus quando a energia muda ≥ 15 pontos); evita repetir categoria em sequência.
    Determinístico: mesmas entradas -> mesma ordem, independente da ordem de entrada.
    """
    by = {v["id"]: v for v in videos}
    sel = sorted((m for m in moments if m.get("selected")), key=lambda m: m["id"])
    notes = []
    if len(sel) <= 1:
        return sel, notes
    viral = lambda m: by.get(m["video_id"], {}).get("viral_score") or 0
    who = lambda m: _creator(by.get(m["video_id"], {"id": m["video_id"]}))
    cat = lambda m: by.get(m["video_id"], {}).get("category")
    last = max(sel, key=lambda m: (m["score"], viral(m), m["id"]))
    rest = [m for m in sel if m is not last]
    med = sorted(m["score"] for m in rest)[len(rest) // 2]
    def hook_value(m):
        short = 1 if (m["end"] - m["start"]) <= 30 else 0
        return (m["score"] >= med, short, 0.6 * _energy(m) + 0.4 * m["score"], m["id"])
    first_choices = sorted(rest, key=hook_value, reverse=True)
    if len(sel) == 2:
        notes.append(f"abre com {rest[0]['id']}, fecha com o melhor ({last['id']}, nota {last['score']})")
        return [rest[0], last], notes

    def pick_score(m, prev):
        s = m["score"]
        if abs(_energy(m) - _energy(prev)) >= 15:
            s += 10
        if cat(m) and cat(m) == cat(prev):
            s -= 30
        return (s, m["id"])

    def build(first):
        order, pool = [first], [m for m in rest if m is not first]
        steps = [0]

        def rec(order, pool):
            steps[0] += 1
            if not pool:
                return who(order[-1]) != who(last) or len({who(m) for m in sel}) == 1
            if steps[0] > max_backtrack * len(sel):
                return False
            prev = order[-1]
            for m in sorted(pool, key=lambda x: pick_score(x, prev), reverse=True):
                if who(m) == who(prev):
                    continue
                order.append(m)
                if rec(order, [x for x in pool if x is not m]):
                    return True
                order.pop()
            return False
        if rec(order, pool):
            return order
        return None

    for first in first_choices:
        order = build(first)
        if order:
            notes.append(f"abre com {first['id']} (gancho: energia {_energy(first):.0f}, nota {first['score']})")
            notes.append(f"fecha com o melhor: {last['id']} (nota {last['score']})")
            notes.append("nenhum criador aparece duas vezes seguidas")
            return order + [last], notes
    # Impossível separar (ex.: quase tudo do mesmo criador): ordem gulosa e aviso.
    order, pool = [first_choices[0]], [m for m in rest if m is not first_choices[0]]
    while pool:
        nxt = max(pool, key=lambda m: (who(m) != who(order[-1]),) + pick_score(m, order[-1]))
        order.append(nxt)
        pool.remove(nxt)
    notes.append(f"fecha com o melhor: {last['id']} (nota {last['score']})")
    notes.append("aviso: não há como evitar o mesmo criador em sequência (poucos criadores diferentes)")
    return order + [last], notes
