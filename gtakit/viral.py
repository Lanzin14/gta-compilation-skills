"""Nota de viralidade (0–100) dos posts — regra da skill gta-video-discovery."""
import math


def engagement(likes, reposts, comments):
    """curtidas + 2×reposts + comentários; campos null contam 0."""
    return (likes or 0) + 2 * (reposts or 0) + (comments or 0)


def _norm(value, maximum):
    # Escala log entre os candidatos; max 0 (ninguém com engajamento) -> 0, sem divisão por zero.
    return 0.0 if maximum == 0 else math.log10(value + 1) / math.log10(maximum + 1)


def viral_scores(videos, now):
    """videos: dicts com likes, reposts, comments, timestamp (s, UTC). Devolve {id: nota}.

    nota = 60 × engajamento_norm + 40 × velocidade_norm, onde velocidade = engajamento / horas
    desde a postagem (mínimo 1 h).
    """
    eng = {v["id"]: engagement(v.get("likes"), v.get("reposts"), v.get("comments")) for v in videos}
    vel = {}
    for v in videos:
        hours = max(1.0, (now - (v.get("timestamp") or now)) / 3600)
        vel[v["id"]] = eng[v["id"]] / hours
    me, mv = max(eng.values(), default=0), max(vel.values(), default=0)
    return {i: round(60 * _norm(eng[i], me) + 40 * _norm(vel[i], mv)) for i in eng}
