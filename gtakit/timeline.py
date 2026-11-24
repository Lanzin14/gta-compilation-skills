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
