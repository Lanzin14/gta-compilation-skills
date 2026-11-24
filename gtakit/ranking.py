"""Ranking inteligente de clipes: 6 notas independentes, corte recomendado, alertas e justificativa.

Critérios (0–100 cada; documentação completa em docs/RANKING.md):
  viralidade  métricas do post (nota de viralidade do discovery) — NÃO é qualidade do conteúdo
  humor       risadas/reações na fala (transcrição), pistas no texto do post e, se houver, avaliação do Claude
  reacao      variação do volume (não o volume absoluto), palavras de reação, reação logo após a ação
  contexto    preparação antes da ação, desfecho depois dela, corte sem interromper fala
  qualidade   resolução, fps, nitidez, brilho, volume integrado, áudio estourado, silêncio
  retencao    gancho nos primeiros segundos, duração, ritmo (movimento), repetição, tempo morto

Regras: clipes de até 90 s entram inteiros (só aparando tempo morto das pontas); o corte nunca
começa/termina no meio de uma fala quando há transcrição; falta de pico de áudio não descarta ninguém.
"""
import copy
import json
import pathlib
import re
import statistics

from . import analysis

REPO_CONFIG = pathlib.Path(__file__).resolve().parent.parent / "config" / "ranking.json"
CRITERIA = ("viralidade", "humor", "reacao", "contexto", "qualidade", "retencao")


# ---------------------------------------------------------------- configuração
def load_config(project_dir=None):
    cfg = json.loads(REPO_CONFIG.read_text(encoding="utf-8"))
    if project_dir:
        local = pathlib.Path(project_dir) / "ranking.json"
        if local.exists():
            _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    return cfg


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def _lerp(x, lo, hi):
    """Mapeia x de [lo, hi] para [0, 100] (com trava)."""
    if hi == lo:
        return 100.0 if x >= hi else 0.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


def _clamp(x):
    return int(round(max(0.0, min(100.0, x))))


# ---------------------------------------------------------------- fala (transcrição)
def segments(transcript):
    return [s for s in (transcript or {}).get("segments", []) if s.get("text", "").strip() and s["end"] > s["start"]]


def _count_terms(text, terms):
    t = (text or "").lower()
    n = 0
    for term in terms:
        if re.fullmatch(r"[a-z]+", term):  # palavra: conta ocorrências como palavra ou prefixo (kkk -> kkkkk)
            n += len(re.findall(rf"\b{re.escape(term)}\w*", t))
        else:
            n += t.count(term)
    return n


def speech_events(transcript, cfg):
    """[(t, tipo)] para falas com risada ou reação forte (tempo do vídeo de origem)."""
    out = []
    for s in segments(transcript):
        if _count_terms(s["text"], cfg["humor_words"]["laugh"]):
            out.append((s["start"], "laugh"))
        elif _count_terms(s["text"], cfg["humor_words"]["reaction"]):
            out.append((s["start"], "reaction_word"))
    return out


def _inside(t, segs):
    return next((s for s in segs if s["start"] < t < s["end"]), None)


def snap_start(start, event_t, segs, cfg):
    """Não começa no meio de uma fala e inclui a conversa contínua que leva à ação (até max_setup_s)."""
    seg = _inside(start, segs)
    if seg:
        start = seg["start"]
    ordered = sorted(segs, key=lambda s: s["start"])
    while True:
        prev = [s for s in ordered if s["end"] <= start + 1e-6 and start - s["end"] <= cfg["cut"]["speech_gap_s"]]
        if not prev:
            return max(0.0, start)
        cand = prev[-1]["start"]
        if event_t - cand > cfg["cut"]["max_setup_s"]:
            return max(0.0, start)
        start = cand


def snap_end(end, segs):
    seg = _inside(end, segs)
    return seg["end"] if seg else end


# ---------------------------------------------------------------- medições derivadas
def trailing_dead_time(dead, duration):
    """Início do tempo morto encostado no fim (silêncio E imagem parada até o fim), ou a duração."""
    ss, fs = dead["silence_start"], dead["freeze_start"]
    if not ss or not fs:
        return duration
    s_last, f_last = ss[-1], fs[-1]
    s_open = len(dead["silence_end"]) < len(ss) or (dead["silence_end"] and dead["silence_end"][-1] >= duration - 0.2)
    f_open = len(dead["freeze_end"]) < len(fs) or (dead["freeze_end"] and dead["freeze_end"][-1] >= duration - 0.2)
    return round(max(s_last, f_last), 2) if s_open and f_open else duration


def _windows_in(rms, a, b):
    return [db for t, db in rms if a <= t < b]


def _motion_in(visual, a, b):
    return [m for t, m, _, _ in visual if a <= t < b]


def events(meas, transcript, cfg):
    """Eventos do vídeo: picos de áudio, cortes de cena, risadas/reações na fala e picos de movimento."""
    peaks, _ = analysis.find_peaks(meas["rms"])
    ev = [(t, "audio_peak") for t in peaks] + [(t, "scene_change") for t in meas["scenes"]]
    ev += speech_events(transcript, cfg)
    motion = [m for _, m, _, _ in meas["visual"]]
    if motion:
        thr = max(20.0, sorted(motion)[int(len(motion) * 0.95)] if len(motion) > 20 else 20.0)
        ev += [(t, "motion_spike") for t, m, _, _ in meas["visual"] if m >= thr]
    return sorted(ev)


def main_event_time(meas, transcript, a, b, cfg):
    """Instante da ação dentro do corte (peak_time): janela de áudio mais alta; sem áudio, maior movimento."""
    win = [(t, db) for t, db in meas["rms"] if a <= t < b and db > analysis.SILENCE_FLOOR_DB]
    if win:
        return max(win, key=lambda w: w[1])[0]
    mot = [(t, m) for t, m, _, _ in meas["visual"] if a <= t < b]
    if mot and max(m for _, m in mot) > 0:
        return max(mot, key=lambda w: w[1])[0]
    laughs = [t for t, _ in speech_events(transcript, cfg) if a <= t < b]
    return laughs[0] if laughs else round((a + b) / 2, 2)


def reaction_tail_end(rms, t_last, cfg):
    """Fim da reação: quando o volume volta perto da mediana por 1,5 s (limite: reaction_tail_max_s)."""
    if not rms:
        return t_last + 2.5
    med = statistics.median(max(db, analysis.SILENCE_FLOOR_DB) for _, db in rms)
    calm = 0
    for t, db in rms:
        if t <= t_last:
            continue
        if t > t_last + cfg["cut"]["reaction_tail_max_s"]:
            return t
        calm = calm + 1 if db <= med + 3 else 0
        if calm >= 3:
            return t + 0.5
    return t_last + cfg["cut"]["reaction_tail_max_s"]


# ---------------------------------------------------------------- cortes recomendados
def candidate_cuts(video, meas, transcript, cfg):
    """[(início, fim, eventos_no_corte, alertas)] — clipe inteiro até whole_clip_max_s; senão, em volta dos eventos."""
    dur = meas["duration_s"]
    segs = segments(transcript)
    ev = events(meas, transcript, cfg)
    c = cfg["cut"]
    if dur <= c["whole_clip_max_s"]:
        a = analysis.leading_dead_time(meas["dead"], dur)
        b = trailing_dead_time(meas["dead"], dur)
        if b - a < 1:
            a, b = 0.0, dur
        a, b = snap_start(a, a, segs, dict(cfg, cut=dict(c, max_setup_s=0))), snap_end(b, segs)
        return [(round(max(0.0, a), 2), round(min(dur, b), 2), [e for e in ev if a <= e[0] <= b], [])]
    cuts, used_until = [], -1.0
    groups = []
    for t, kind in ev:
        if groups and t - groups[-1][-1][0] < c["event_group_gap_s"]:
            groups[-1].append((t, kind))
        else:
            groups.append([(t, kind)])
    for g in groups:
        first, last = g[0][0], g[-1][0]
        a = snap_start(max(0.0, first - c["setup_s"]), first, segs, cfg)
        b = snap_end(min(dur, reaction_tail_end(meas["rms"], last, cfg)), segs)
        if b - a < c["min_cut_s"]:
            b = min(dur, a + c["min_cut_s"])
            a = max(0.0, b - c["min_cut_s"])
        alerts = []
        if b - a > c["max_cut_s"]:
            b = a + c["max_cut_s"]
            alerts.append(f"momento maior que {c['max_cut_s']:.0f} s: corte limitado — confira se não cortou o desfecho")
        if cuts and a < used_until:
            # sobrepõe o corte anterior do mesmo vídeo: funde os dois (é a mesma cena), em vez de perder um deles
            pa, pb, _, pal = cuts[-1]
            na, nb = pa, max(pb, b)
            if nb - na > c["max_cut_s"]:
                nb = na + c["max_cut_s"]
                alerts.append(f"momento maior que {c['max_cut_s']:.0f} s: corte limitado — confira se não cortou o desfecho")
            cuts[-1] = (round(na, 2), round(nb, 2), [e for e in ev if na <= e[0] <= nb], pal + alerts)
            used_until = nb
            continue
        cuts.append((round(a, 2), round(b, 2), [e for e in ev if a <= e[0] <= b], alerts))
        used_until = b
    if not cuts:
        cuts.append((0.0, round(min(dur, c["max_cut_s"]), 2), [], ["nenhum evento detectado: corte do início do vídeo"]))
    return cuts


# ---------------------------------------------------------------- critérios
def score_humor(video, transcript, a, b, cfg, judgment=None):
    words = cfg["humor_words"]
    post_cues = _count_terms(video.get("text"), words["post_funny"])
    segs = [s for s in segments(transcript) if a <= s["start"] < b]
    laughs = sum(_count_terms(s["text"], words["laugh"]) for s in segs)
    reacts = sum(_count_terms(s["text"], words["reaction"]) for s in segs)
    why, alerts = [], []
    post_s = {0: 0.0, 1: 70.0, 2: 85.0}.get(post_cues, 100.0)  # quem postou disse que é engraçado: pista forte
    if post_cues:
        why.append(f"texto do post indica humor ({post_cues} pista(s))")
    if transcript is not None:
        density = (2 * laughs + reacts) / max(1.0, (b - a) / 30)
        speech_s = min(100.0, 22.0 * density)
        if laughs:
            why.append(f"risada na fala ({laughs}×)")
        if reacts:
            why.append(f"reações na fala ({reacts}×)")
        score = max(speech_s, 0.8 * post_s)
    elif post_cues:
        score = 0.9 * post_s
        alerts.append("sem transcrição: humor estimado só pelo texto do post")
    else:
        score = 50.0
        alerts.append("humor não medido (sem transcrição e sem pistas no post): nota neutra 50")
    src = "medido"
    if judgment and judgment.get("reason"):
        score, src = float(judgment["score"]), "avaliação do Claude"
        why.append(f"avaliação: {judgment['reason']}")
    return _clamp(score), why, alerts, src


def score_reaction(meas, transcript, a, b, ev, cfg):
    why, alerts = [], []
    if not meas["has_audio"]:
        return 30, why, ["sem áudio: reação não medida (nota 30)"]
    win = sorted(max(db, analysis.SILENCE_FLOOR_DB) for db in _windows_in(meas["rms"], a, b))
    if not win:
        return 30, why, ["corte sem janelas de áudio"]
    med = statistics.median(win)
    p95 = win[min(len(win) - 1, int(len(win) * 0.95))]
    rng = p95 - med
    s = 0.7 * _lerp(rng, cfg["reaction"]["range_db_min"], cfg["reaction"]["range_db_max"])
    if rng >= 8:
        why.append(f"variação de volume de {rng:.0f} dB (grito/explosão acima do normal do clipe)")
    elif rng >= cfg["reaction"]["range_db_min"]:
        why.append(f"variação de volume pequena ({rng:.0f} dB)")
    kinds = [k for t, k in ev]
    words = sum(1 for k in kinds if k in ("laugh", "reaction_word"))
    if words:
        s += min(30.0, 12.0 * words)
        why.append("reação falada logo na ação")
    times = [t for t, k in ev]
    if any(0 < t2 - t1 <= 2 for t1 in times for t2 in times if t1 != t2):
        s += 15
        why.append("reação logo depois da ação")
    if rng < cfg["reaction"]["range_db_min"] and not words:
        alerts.append("áudio sem variação (alto ou baixo constante): reação não aparece no volume")
    return _clamp(s), why, alerts


def score_context(a, b, peak, segs, cfg):
    why, alerts = [], []
    setup, after = peak - a, b - peak
    s = 50 * min(1.0, setup / cfg["cut"]["setup_s"]) + 30 * min(1.0, after / 2.0)
    if setup >= cfg["cut"]["setup_s"]:
        why.append(f"{setup:.0f} s de preparação antes da ação")
    elif setup < 1.5:
        alerts.append("ação logo no início: pode faltar contexto/preparação")
    if after < 1.5:
        alerts.append("termina logo depois da ação: reação/desfecho pode ter sido cortado")
    cut_speech = _inside(a, segs) or _inside(b, segs)
    if segs and not cut_speech:
        s += 20
        why.append("não corta nenhuma fala no meio")
    elif segs:
        alerts.append("o corte interrompe uma fala")
    else:
        s += 10  # sem transcrição: não dá para saber se corta fala
    return _clamp(s), why, alerts


def score_quality(video, meas, a, b, cfg):
    q = cfg["quality"]
    why, alerts = [], []
    h = meas.get("height") or 0
    w = meas.get("width") or 0
    short_side = min(h, w) if h and w else h
    s = 100 if short_side >= 1080 else 85 if short_side >= 720 else 65 if short_side >= 480 else 40
    why.append(f"resolução {w}x{h}")
    if short_side < 480:
        alerts.append(f"resolução baixa ({w}x{h})")
    if meas.get("fps") and meas["fps"] < 24:
        s -= 10
        alerts.append(f"fps baixo ({meas['fps']})")
    vis = [(y, bl) for t, _, y, bl in meas["visual"] if a <= t < b]
    if vis:
        yavg = statistics.mean(y for y, _ in vis)
        blur = statistics.mean(bl for _, bl in vis)
        if yavg < q["dark_yavg"]:
            s -= 25
            alerts.append(f"imagem escura (brilho médio {yavg:.0f}/255)")
        if blur > q["blurry"]:
            s -= 20
            alerts.append(f"imagem borrada (índice {blur:.1f})")
    if not meas["has_audio"]:
        s -= 15
        alerts.append("vídeo sem áudio")
    else:
        lo = meas.get("loudness") or {}
        if lo.get("lufs") is not None and lo["lufs"] < q["quiet_lufs"]:
            s -= 15
            alerts.append(f"áudio muito baixo ({lo['lufs']:.0f} LUFS)")
        if lo.get("true_peak_dbfs") is not None and lo["true_peak_dbfs"] >= q["clip_true_peak_dbfs"]:
            s -= 10
            alerts.append("áudio estourado (pico no máximo)")
        win = _windows_in(meas["rms"], a, b)
        if win:
            silent = sum(db <= -50 for db in win) / len(win)
            if silent >= q["silence_ratio_alert"]:
                s -= 15
                alerts.append(f"áudio quase todo em silêncio ({silent:.0%} do corte)")
    return _clamp(s), why, alerts


def repetition_ratio(hashes, a, b, cfg, fps=2):
    """Fração dos quadros do corte quase iguais a um quadro ≥ repeat_lag_s antes (replay, loop, tela parada)."""
    seg = hashes[int(a * fps):int(b * fps)]
    lag = int(cfg["duplicates"]["repeat_lag_s"] * fps)
    if len(seg) <= lag:
        return 0.0
    thr = cfg["duplicates"]["hash_distance"]
    rep = sum(1 for i in range(lag, len(seg)) if any(bin(seg[i] ^ seg[j]).count("1") <= thr for j in range(0, i - lag + 1)))
    return rep / (len(seg) - lag)


def score_retention(meas, a, b, ev, cfg):
    r = cfg["retention"]
    why, alerts = [], []
    dur = b - a
    s = 15.0
    if any(a <= t <= a + r["hook_s"] for t, _ in ev):
        s += 35
        why.append(f"algo acontece nos primeiros {r['hook_s']} s (gancho)")
    else:
        s += 10
        alerts.append(f"começo fraco: nada acontece nos primeiros {r['hook_s']} s")
    if r["ideal_min_s"] <= dur <= r["ideal_max_s"]:
        s += 30
    elif dur < 8:
        s += 10
        alerts.append(f"muito curto ({dur:.0f} s)")
    elif dur <= cfg["cut"]["whole_clip_max_s"]:
        s += 20
    else:
        s += 10
        alerts.append(f"longo ({dur:.0f} s): risco de o espectador sair")
    mot = _motion_in(meas["visual"], a, b)
    if mot:
        s += 0.2 * _lerp(statistics.mean(mot), 1, 15)
    rep = repetition_ratio(meas.get("hashes", []), a, b, cfg)
    if rep >= cfg["duplicates"]["repeat_ratio_alert"]:
        s -= 20
        alerts.append(f"trecho repetitivo ({rep:.0%} dos quadros repetem cenas anteriores)")
    return _clamp(s), why, alerts


# ---------------------------------------------------------------- duplicados
def _hash_match(h1, h2, cfg):
    """Fração de quadros do clipe menor que batem com o maior, no melhor alinhamento."""
    if not h1 or not h2:
        return 0.0
    short, long_ = (h1, h2) if len(h1) <= len(h2) else (h2, h1)
    thr = cfg["duplicates"]["hash_distance"]
    best = 0.0
    for off in range(0, len(long_) - len(short) + 1):
        hits = sum(bin(x ^ long_[off + i]).count("1") <= thr for i, x in enumerate(short))
        best = max(best, hits / len(short))
    return best


def _corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return None if sx == 0 or sy == 0 else sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def _audio_same(r1, r2):
    """Mesmo áudio? Compara o FORMATO do volume ao longo do tempo (correlação) no melhor alinhamento;
    se os dois forem quase constantes, compara o nível (diferença média ≤ 2,5 dB)."""
    a = [max(db, -60.0) for _, db in r1]
    b = [max(db, -60.0) for _, db in r2]
    if len(a) < 4 or len(b) < 4:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    flat = statistics.pstdev(short) < 1.5 and statistics.pstdev(long_) < 1.5
    for off in range(0, len(long_) - len(short) + 1):
        seg = long_[off:off + len(short)]
        if flat:
            if statistics.mean(abs(x - y) for x, y in zip(short, seg)) <= 2.5:
                return True
        else:
            c = _corr(short, seg)
            if c is not None and c >= 0.85:
                return True
    return False


def duplicate_pairs(meas_by_video, cfg):
    """[(vídeo_a, vídeo_b, semelhança)] para vídeos praticamente iguais: imagem parecida, duração parecida
    (≥ 75%) e mesmo áudio. Entre um vídeo mudo e um com áudio, exige imagem e duração quase idênticas."""
    ids = sorted(meas_by_video)
    pairs = []
    min_vis = cfg["duplicates"]["min_match_ratio"]
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            mx, my = meas_by_video[x], meas_by_video[y]
            dx, dy = mx["duration_s"], my["duration_s"]
            ratio = min(dx, dy) / max(dx, dy) if max(dx, dy) else 0
            if ratio < 0.75:
                continue
            vis = _hash_match(mx.get("hashes", []), my.get("hashes", []), cfg)
            if mx["has_audio"] and my["has_audio"]:
                dup = vis >= min_vis and _audio_same(mx["rms"], my["rms"])
            elif mx["has_audio"] != my["has_audio"]:
                dup = vis >= 0.9 and ratio >= 0.9
            else:
                dup = vis >= max(0.8, min_vis)
            if dup:
                pairs.append((x, y, round(vis, 2)))
    return pairs


# ---------------------------------------------------------------- ranking
def rank(videos, meas_by_video, transcripts, judgments, cfg):
    """Gera os momentos ranqueados. videos: entradas do discovery aprovadas e baixadas."""
    w = cfg["weights"]
    moments = []
    for v in videos:
        meas = meas_by_video[v["id"]]
        tr = transcripts.get(v["id"])
        segs = segments(tr)
        for a, b, ev, cut_alerts in candidate_cuts(v, meas, tr, cfg):
            jd = (judgments.get(v["id"]) or {})
            peak = main_event_time(meas, tr, a, b, cfg)
            crit, why, alerts = {}, [], list(cut_alerts)
            crit["viralidade"] = int(v.get("viral_score") or 0)
            why.append(f"viralidade {crit['viralidade']} (métricas do post — não mede o conteúdo)")
            hs, hw, ha, hsrc = score_humor(v, tr, a, b, cfg, jd.get("humor"))
            crit["humor"] = hs
            for name, (sc, wy, al) in (("reacao", score_reaction(meas, tr, a, b, ev, cfg)),
                                       ("contexto", score_context(a, b, peak, segs, cfg)),
                                       ("qualidade", score_quality(v, meas, a, b, cfg)),
                                       ("retencao", score_retention(meas, a, b, ev, cfg))):
                crit[name] = sc
                why += wy
                alerts += al
            why += hw
            alerts += ha
            for name in CRITERIA:  # avaliação do Claude em outros critérios, sempre com motivo
                j = jd.get(name)
                if name != "humor" and j and j.get("reason"):
                    crit[name] = _clamp(float(j["score"]))
                    why.append(f"{name} ajustado na avaliação: {j['reason']}")
            if v.get("used_before"):
                alerts.append(f"já usado em compilado anterior: {', '.join(v['used_before'])}")
            final = sum(w[k] * crit[k] for k in CRITERIA) / sum(w.values())
            p_in = [t for t, k in ev if k == "audio_peak"]
            s_in = [t for t, k in ev if k == "scene_change"]
            sig = analysis.signals_of(p_in, s_in)
            if any(k in ("laugh", "reaction_word") for _, k in ev):
                sig.append("speech_reaction")
            moments.append({
                "video_id": v["id"], "source": v["local_path"], "start": a, "end": b,
                "score": int(round(final)), "legacy_score": analysis.legacy_score(sig),
                "signals": sig, "peaks": p_in, "peak_time": round(peak, 2),
                "summary": None, "language": None, "needs_translation": None, "selected": False,
                "ranking": {"criteria": crit, "final": round(final, 1), "humor_source": hsrc,
                            "justification": why, "alerts": alerts, "duplicate_of": None,
                            "recommended": {"start": a, "end": b, "duration_s": round(b - a, 2)},
                            "selection_reason": None},
            })
    _mark_duplicates(moments, duplicate_pairs({v["id"]: meas_by_video[v["id"]] for v in videos}, cfg),
                     {v["id"]: v for v in videos})
    _select(moments, cfg)
    moments.sort(key=lambda m: (-m["ranking"]["final"], m["video_id"], m["start"]))
    return moments


def _mark_duplicates(moments, pairs, by):
    """Em cada par de vídeos iguais, fica o de maior nota final (desempate: viralidade); o outro vira duplicado."""
    def best(vid):
        ms = [m["ranking"]["final"] for m in moments if m["video_id"] == vid]
        return (max(ms) if ms else 0, by[vid].get("viral_score") or 0)
    for x, y, sim in pairs:
        keep, drop = (x, y) if best(x) >= best(y) else (y, x)
        for m in moments:
            if m["video_id"] == drop and m["ranking"]["duplicate_of"] is None:
                m["ranking"]["duplicate_of"] = keep
                m["ranking"]["alerts"].append(f"praticamente igual ao vídeo {keep} ({sim:.0%} dos quadros iguais)")


def _select(moments, cfg):
    sel = cfg["selection"]
    per_video, total = {}, 0.0
    for m in sorted(moments, key=lambda m: -m["ranking"]["final"]):
        r = m["ranking"]
        dur = m["end"] - m["start"]
        if r["duplicate_of"]:
            r["selection_reason"] = f"fora: duplicado de {r['duplicate_of']}"
        elif r["final"] < sel["min_final"]:
            r["selection_reason"] = f"fora: nota final {r['final']} abaixo de {sel['min_final']}"
        elif per_video.get(m["video_id"], 0) >= sel["max_per_video"]:
            r["selection_reason"] = f"fora: já há {sel['max_per_video']} momentos deste vídeo"
        elif total >= sel["target_duration_s"]:
            r["selection_reason"] = "reserva: a duração alvo já foi atingida"
        else:
            m["selected"] = True
            per_video[m["video_id"]] = per_video.get(m["video_id"], 0) + 1
            total += dur
            r["selection_reason"] = "selecionado"


def report_markdown(moments, by_video):
    """Ranking legível (output/ranking.md)."""
    fmt = lambda s: f"{int(s) // 60:02d}:{s % 60:04.1f}"
    lines = ["# Ranking de clipes", "",
             "Notas de 0 a 100. **Viralidade** mede o post (curtidas/reposts), não o conteúdo.", "",
             "| # | Criador | Final | Viral. | Humor | Reação | Contexto | Qualid. | Reten. | Corte recomendado | Duração | Situação |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, m in enumerate(moments, 1):
        v, c = by_video[m["video_id"]], m["ranking"]["criteria"]
        who = (v.get("original_creator") or {}).get("name")
        who = f"{who} (clipe {v.get('author_handle')})" if who else v.get("author_handle")
        lines.append(f"| {i} | {who} | **{m['ranking']['final']}** | {c['viralidade']} | {c['humor']} | {c['reacao']} | "
                     f"{c['contexto']} | {c['qualidade']} | {c['retencao']} | {fmt(m['start'])}–{fmt(m['end'])} | "
                     f"{m['end'] - m['start']:.1f} s | {m['ranking']['selection_reason']} |")
    lines.append("")
    for i, m in enumerate(moments, 1):
        v = by_video[m["video_id"]]
        lines += [f"## {i}. {m.get('id', '')} — {v.get('author_handle')} — nota {m['ranking']['final']}",
                  f"- URL original: {v.get('url')}",
                  f"- Ação principal (peak_time): {m['peak_time']} s",
                  "- Por quê: " + "; ".join(m["ranking"]["justification"])]
        if m["ranking"]["alerts"]:
            lines.append("- ⚠️ Alertas: " + "; ".join(m["ranking"]["alerts"]))
        lines.append("")
    return "\n".join(lines)


def measurements(path, has_audio, info, cwd, ff):
    """Faz todas as medições de um vídeo (usado pelo comando analyze; o resultado vai para o cache)."""
    return {
        "duration_s": info["duration_s"], "width": info["width"], "height": info["height"],
        "fps": info["fps"], "has_audio": has_audio,
        "rms": ff.rms_windows(path, cwd=cwd) if has_audio else [],
        "scenes": ff.scene_changes(path, cwd=cwd),
        "dead": ff.dead_time(path, cwd=cwd),
        "visual": ff.visual_stats(path, cwd=cwd),
        "loudness": ff.loudness(path, cwd=cwd) if has_audio else None,
        "hashes": ff.frame_hashes(path, cwd=cwd),
    }


def clone_config(cfg, **changes):
    c = copy.deepcopy(cfg)
    _merge(c, changes)
    return c
