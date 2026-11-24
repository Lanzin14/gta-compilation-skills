"""Regras do viral-moment-analyzer: picos de áudio, tempo morto, cortes, peak_time e nota.

Funções puras (recebem medições já feitas pelo ff.py) para poderem ser testadas sem vídeo.
"""
import statistics

SILENCE_FLOOR_DB = -60.0   # janelas abaixo disso contam como -60 dB e nunca são pico
PEAK_OVER_MEDIAN_DB = 6.0  # pico = janela >= mediana + 6 dB
SHORT_VIDEO_S = 40.0       # vídeos até isso entram inteiros (menos tempo morto nas pontas)
GROUP_GAP_S = 3.0          # sinais a menos de 3 s viram o mesmo momento
CUT_BEFORE_S = 4.0         # contexto antes do 1º sinal (skill: 3–5 s)
CUT_AFTER_S = 2.5          # reação depois do último sinal (skill: 2–3 s)
MIN_CUT_S, MAX_CUT_S = 10.0, 30.0
MAX_MOMENTS_PER_VIDEO = 3
MIN_SCORE = 45


def find_peaks(windows):
    """windows: [(t, dB)]. Devolve (picos [t], janela mais alta entre os picos (t, dB) ou None)."""
    if not windows:
        return [], None
    clamped = [(t, max(db, SILENCE_FLOOR_DB)) for t, db in windows]
    med = statistics.median(db for _, db in clamped)
    peaks = [(t, db) for t, db in clamped if db > SILENCE_FLOOR_DB and db >= med + PEAK_OVER_MEDIAN_DB]
    loudest = max(peaks, key=lambda p: p[1]) if peaks else None
    return [t for t, _ in peaks], loudest


def leading_dead_time(dead, duration):
    """Fim do tempo morto encostado no início (silêncio E imagem parada a partir de ~0 s), ou 0."""
    if dead["silence_start"] and dead["freeze_start"] and dead["silence_start"][0] < 0.1 and dead["freeze_start"][0] < 0.1:
        sil_end = dead["silence_end"][0] if dead["silence_end"] else duration
        frz_end = dead["freeze_end"][0] if dead["freeze_end"] else duration
        return round(min(sil_end, frz_end), 2)
    return 0.0


def signals_of(peaks, scenes):
    sig = []
    if peaks:
        sig.append("audio_peak")
    if scenes:
        sig.append("scene_change")
    if any(0 < p - q <= 2 for p in peaks for q in peaks + scenes):
        sig.append("reaction")
    return sig


def legacy_score(sig):
    """30 pico + 25 cena + 25 reação + 20 (compreensível); penalidades visuais ficam a cargo do Claude."""
    return 30 * ("audio_peak" in sig) + 25 * ("scene_change" in sig) + 25 * ("reaction" in sig) + 20


def peak_time_of(loudest, scenes, start, end):
    """Pico de áudio mais alto dentro do corte; senão 1ª mudança de cena dentro do corte; senão None."""
    if loudest and start <= loudest[0] <= end:
        return loudest[0]
    inside = [s for s in scenes if start <= s <= end]
    return inside[0] if inside else None


def _moment(video_id, source, start, end, peaks, scenes, loudest):
    p_in = [p for p in peaks if start <= p <= end]
    s_in = [s for s in scenes if start <= s <= end]
    sig = signals_of(p_in, s_in)
    score = legacy_score(sig)
    return {
        "video_id": video_id, "source": source, "start": round(start, 3), "end": round(end, 3),
        "score": score, "signals": sig, "peaks": p_in,
        "peak_time": peak_time_of(loudest, scenes, start, end),
        "summary": None, "language": None, "needs_translation": None,
        "selected": bool({"audio_peak", "scene_change"} & set(sig)) and score >= MIN_SCORE,
    }


def _groups(times):
    groups = []
    for t in sorted(times):
        if groups and t - groups[-1][-1] < GROUP_GAP_S:
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def analyze_video(video, windows, scenes, dead):
    """Gera os momentos de um vídeo (sem ids). video: dict com id, local_path, duration_s."""
    duration = video["duration_s"]
    peaks, loudest = find_peaks(windows)
    if duration <= SHORT_VIDEO_S:
        start = leading_dead_time(dead, duration)
        return [_moment(video["id"], video["local_path"], start, round(duration, 2), peaks, scenes, loudest)]
    moments = []
    for g in _groups(peaks + scenes):
        start = max(0.0, g[0] - CUT_BEFORE_S)
        end = min(duration, g[-1] + CUT_AFTER_S)
        if end - start < MIN_CUT_S:
            end = min(duration, start + MIN_CUT_S)
            start = max(0.0, end - MIN_CUT_S)
        if end - start > MAX_CUT_S:
            end = start + MAX_CUT_S
        g_loud = find_peaks([(t, db) for t, db in windows if start <= t <= end])[1] if windows else None
        moments.append(_moment(video["id"], video["local_path"], start, end, peaks, scenes, g_loud or loudest))
    moments.sort(key=lambda m: -m["score"])
    return moments[:MAX_MOMENTS_PER_VIDEO] or [
        _moment(video["id"], video["local_path"], 0.0, min(duration, MAX_CUT_S), peaks, scenes, loudest)]


def number_moments(moments):
    for i, m in enumerate(moments, 1):
        m["id"] = f"m{i:02d}"
    return moments
