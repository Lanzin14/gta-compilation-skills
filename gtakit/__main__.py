"""Linha de comando do gtakit. Rode a partir da raiz do repositório:

    py -3 -m gtakit <comando> projects/<slug> [opções]     (Windows)
    python3 -m gtakit <comando> projects/<slug> [opções]   (Linux/macOS)

Comandos (na ordem do fluxo):
  init       cria a pasta do projeto
  discovery  lê raw_meta.jsonl (saída do yt-dlp --dump-json) e gera discovery.json com a nota de viralidade
  approve    marca vídeos aprovados/recusados pelo usuário
  probe      confere os vídeos baixados em source/ (duração, tamanho, áudio)
  audio      --full: áudio do vídeo inteiro (subs/<video_id>.full.wav) para transcrever ANTES do ranking;
             sem --full: áudio de cada momento (subs/<id>.wav) para a legenda
  analyze    mede tudo (cache em analysis/) e gera moments.json com o ranking dos clipes + ranking.md
  rank       refaz só o ranking (sem medir de novo), após transcrições ou avaliações em judgments.json
  render     corta, padroniza e junta os clipes; gera output/compilation.mp4 e output/timeline.json
  thumbnail  gera output/thumbnail.jpg no pico do melhor momento
  thumbnails gera 3–5 candidatas (2 estilos) + folha de comparação output/thumbs/escolha.jpg
  thumbnail-pick  copia a candidata escolhida para output/thumbnail.jpg
  shorts     gera os Shorts verticais em output/shorts/ (--layout auto|crop|split|blur)
  facecam    marca a região da câmera do streamer num vídeo (para Shorts "dividido")
  credit     define o criador original de um vídeo (ex.: o streamer do clipe)
  permissions  gera permissions.md com as mensagens de pedido de permissão
  rights-set / rights-list / rights-sync   registro de permissões (data/permissions.json)
  ready      confere se o compilado pode ser publicado (direitos) — bloqueia sem permissão
  history-record  grava/atualiza o compilado no histórico (data/history.jsonl) — o render já faz isso
  published  registra o link do YouTube depois que o usuário publicou (manualmente)
  metrics-import  importa o CSV exportado do YouTube Studio para o histórico
  report     desempenho por compilado e por criador
  validate   confere os contratos JSON entre as etapas
  status     mostra o estado das etapas
"""
import argparse
import datetime
import pathlib
import re
import sys
import time

import shutil

from .project import now_iso as now_iso_str

from . import analysis, brand as brandmod, ff, framing, history, ranking, render, rights, thumbs, timeline, viral
from .project import Project, load_json, save_json


def _err(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    return 1


def _videos(proj):
    disc = load_json(proj.p("discovery.json"))
    if disc is None:
        raise SystemExit(_err("discovery.json não existe; rode o comando discovery antes"))
    return disc


def _credit_file(proj, v):
    """Grava o texto do crédito em credits/<id>.txt (lido pelo drawtext como texto literal)."""
    rel = f"credits/{v['id']}.txt"
    proj.p("credits").mkdir(exist_ok=True)
    proj.p(rel).write_text(rights.credit_text(v), encoding="utf-8")  # sem quebra de linha no fim
    return rel


def _brand_assets(proj, brand):
    """Grava os textos da marca e copia o logo para brand/ no projeto. Devolve (watermark, logo) relativos."""
    if not brand["active"]:
        return None, None
    proj.p("brand").mkdir(exist_ok=True)
    proj.p("brand", "watermark.txt").write_text(brand["channel_handle"], encoding="utf-8")
    for kind in ("intro", "outro"):
        proj.p("brand", f"{kind}.txt").write_text(brandmod.card_text(brand, kind), encoding="utf-8")
    logo = None
    if brand.get("logo"):
        src = pathlib.Path(brand["logo"])
        src = src if src.is_absolute() else pathlib.Path(__file__).resolve().parent.parent / src
        if not src.exists():
            raise SystemExit(_err(f"logo da marca não encontrado: {src}"))
        shutil.copyfile(src, proj.p("brand", "logo" + src.suffix.lower()))
        logo = f"brand/logo{src.suffix.lower()}"
    return "brand/watermark.txt", logo


def _encode_moment(proj, m, v, out, vf_fn, brand, preset, start=None, dur=None, faststart=False, base=None):
    start = m["start"] if start is None else start
    dur = m["end"] - m["start"] if dur is None else dur
    fade = brand["transition"]["seconds"] if brand["transition"]["type"] == "fade" else None
    wm, logo = _brand_assets(proj, brand)
    extra = {"base": base} if base else {}
    vf = vf_fn(v, m.get("subtitle_pt"), _credit_file(proj, v), fps=brand["fps"], brand=brand, wm_file=wm,
               logo_rel=logo, duration=dur, fade=fade, **extra)
    af = None
    if v["has_audio"]:
        meas = ff.loudnorm_measure(m["source"], start, dur, cwd=proj.dir) if brand["audio_two_pass"] else None
        af = render.audio_filter(meas, dur, fade)
    return ff.run_drawtext(render.encode_args(m["source"], start, dur, v["has_audio"], vf, out,
                                              preset=preset, faststart=faststart, af=af), cwd=proj.dir)


def _history_entry(proj, render_s=None):
    disc = _videos(proj)
    by = {v["id"]: v for v in disc["videos"]}
    mom = {m["id"]: m for m in load_json(proj.p("moments.json"), {"moments": []})["moments"]}
    tl = load_json(proj.p("output", "timeline.json"), {"clips": []})
    clips = []
    for e in tl["clips"]:
        m = mom.get(e["moment_id"])
        if not m:
            continue  # abertura/tela final
        v = by[m["video_id"]]
        clips.append({"moment_id": m["id"], "video_id": v["id"], "post_id": v.get("post_id"), "url": v.get("url"),
                      "author_handle": v.get("author_handle"),
                      "original_creator": (v.get("original_creator") or {}).get("name"),
                      "start": m["start"], "end": m["end"], "score": m["score"]})
    pc = load_json(proj.p("output", "publish_check.json"), {})
    entry = {"slug": proj.dir.name, "theme": disc.get("theme"), "recorded_at": now_iso_str(),
             "duration_s": round(sum(e["clip_dur"] for e in tl["clips"]), 2), "clips": clips,
             "shorts": len(load_json(proj.p("output", "shorts", "shorts.json"), [])),
             "publish_ready": pc.get("publish_ready"), "youtube": None, "metrics": None}
    if render_s is not None:
        entry["render_s"] = round(render_s, 1)
    return entry


def _record(proj, path, render_s=None):
    entries = history.load(path)
    entry = _history_entry(proj, render_s)
    old = next((e for e in entries if e["slug"] == entry["slug"]), {})
    if render_s is None and old.get("render_s") is not None:
        entry["render_s"] = old["render_s"]
    history.save(history.upsert(entries, entry), path)
    return entry


def _used_videos(proj):
    by = {v["id"]: v for v in _videos(proj)["videos"]}
    tl = load_json(proj.p("output", "timeline.json"))
    mom = load_json(proj.p("moments.json"), {"moments": []})
    mids = {e["moment_id"] for e in tl["clips"]} if tl else {m["id"] for m in mom["moments"] if m.get("selected")}
    shorts = load_json(proj.p("output", "shorts", "shorts.json"), [])
    mids |= {s["moment_id"] for s in shorts}
    vids = {m["video_id"] for m in mom["moments"] if m["id"] in mids}
    return [by[i] for i in sorted(vids)]


# ---------------------------------------------------------------- comandos
def cmd_init(proj, a):
    for d in ("source", "subs", "clips", "output"):
        proj.p(d).mkdir(parents=True, exist_ok=True)
    if not proj.p("project.json").exists():
        save_json(proj.p("project.json"), {"theme": a.theme, "created_at": datetime.date.today().isoformat(), "stages": {}})
    print(f"projeto pronto em {proj.dir}")
    return 0


def _from_ytdlp(d):
    url = d.get("webpage_url") or d.get("original_url") or ""
    post = re.search(r"/status/(\d+)", url)
    handle = d.get("uploader_id") or ""
    ts = d.get("timestamp")
    return {
        "id": str(d["id"]),
        "platform": "x" if "twitter" in (d.get("extractor") or "twitter").lower() or "x.com" in url else "youtube",
        "post_id": post.group(1) if post else None,
        "url": url,
        "author": d.get("uploader"),
        "author_handle": f"@{handle}" if handle and not handle.startswith("@") else handle,
        "author_url": f"https://x.com/{handle.lstrip('@')}" if handle else None,
        "text": d.get("description") or d.get("title"),
        "timestamp": ts,
        "posted_at": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat() if ts else None,
        "duration_s": d.get("duration"),
        "width": d.get("width"), "height": d.get("height"),
        "likes": d.get("like_count"), "reposts": d.get("repost_count"),
        "comments": d.get("comment_count"), "views": d.get("view_count"),
    }


def cmd_discovery(proj, a):
    raw = proj.p("raw_meta.jsonl")
    if not raw.exists():
        return _err(f"{raw} não existe (rode o yt-dlp --dump-json antes)")
    import json
    vids = [_from_ytdlp(json.loads(line)) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    old = {v["id"]: v for v in (load_json(proj.p("discovery.json"), {"videos": []})["videos"])}
    scores = viral.viral_scores(vids, a.now or time.time())
    for v in vids:
        v["viral_score"] = scores[v["id"]]
        prev = old.get(v["id"], {})
        # decisões do usuário e dados já medidos são preservados ao refazer o discovery
        for k, default in (("approved", False), ("rights", "unknown"), ("category", None), ("game", None),
                           ("local_path", None), ("has_audio", None), ("error", None)):
            v[k] = prev.get(k, default)
    vids.sort(key=lambda v: -v["viral_score"])
    past = history.load(a.history)
    for v in vids:
        v["used_before"] = history.used_before(past, v, exclude_slug=proj.dir.name)
        if v["used_before"]:
            print(f"aviso: {v['author_handle']} ({v['url']}) já foi usado em: {', '.join(v['used_before'])}")
    disc = load_json(proj.p("discovery.json"), {}) or {}
    disc.update({"theme": disc.get("theme") or proj.state().get("theme"), "videos": vids})
    save_json(proj.p("discovery.json"), disc)
    proj.mark("discovery", "listed", videos=len(vids))
    print(f"{'nota':>4}  {'autor':<22} {'curtidas':>9} {'reposts':>8} {'views':>10}  texto")
    for v in vids:
        print(f"{v['viral_score']:>4}  {v['author_handle'] or '?':<22} {v['likes'] or 0:>9} {v['reposts'] or 0:>8} "
              f"{v['views'] if v['views'] is not None else '-':>10}  {(v['text'] or '')[:60]!r}")
    return 0


def cmd_approve(proj, a):
    disc = _videos(proj)
    ids = {v["id"] for v in disc["videos"]}
    unknown = [i for i in a.ids if i not in ids]
    if unknown:
        return _err(f"ids desconhecidos: {', '.join(unknown)}")
    for v in disc["videos"]:
        if a.all or v["id"] in a.ids:
            v["approved"] = not a.reject
    save_json(proj.p("discovery.json"), disc)
    print(f"aprovados: {sum(v['approved'] for v in disc['videos'])} de {len(disc['videos'])}")
    return 0


def cmd_probe(proj, a):
    disc = _videos(proj)
    missing = []
    for v in disc["videos"]:
        if not v.get("approved"):
            continue
        files = sorted(proj.p("source").glob(f"{v['id']}.*"))
        if not files:
            missing.append(v["id"])
            v["error"] = "arquivo não baixado"
            continue
        v["local_path"] = files[0].relative_to(proj.dir).as_posix()
        v.update(ff.media_info(v["local_path"], cwd=proj.dir))
        v["error"] = None
    save_json(proj.p("discovery.json"), disc)
    for v in disc["videos"]:
        if v.get("approved") and v.get("local_path"):
            print(f"{v['id']}: {v['duration_s']}s {v['width']}x{v['height']} {v['fps']}fps áudio={'sim' if v['has_audio'] else 'NÃO'}")
    if missing:
        return _err(f"aprovados sem arquivo em source/: {', '.join(missing)}")
    proj.mark("discovery", "done")
    return 0


def _measure_all(proj, vids, refresh=False):
    """Medições de cada vídeo, com cache em analysis/<id>.json (medir é a parte lenta)."""
    out = {}
    for v in vids:
        cache = proj.p("analysis", f"{v['id']}.json")
        data = None if refresh else load_json(cache)
        if data is None or data.get("_source") != v["local_path"]:
            info = ff.media_info(v["local_path"], cwd=proj.dir)
            data = ranking.measurements(v["local_path"], v["has_audio"], info, proj.dir, ff)
            data["_source"] = v["local_path"]
            save_json(cache, data)
        out[v["id"]] = data
    return out


def _ranked(proj, refresh=False):
    disc = _videos(proj)
    vids = [v for v in disc["videos"] if v.get("approved") and v.get("local_path")]
    meas = _measure_all(proj, vids, refresh)
    transcripts = {v["id"]: load_json(proj.p("subs", f"{v['id']}.full.json")) for v in vids}
    transcripts = {k: x for k, x in transcripts.items() if x is not None}
    judgments = load_json(proj.p("judgments.json"), {})
    cfg = ranking.load_config(proj.dir)
    moments = analysis.number_moments(ranking.rank(vids, meas, transcripts, judgments, cfg))
    save_json(proj.p("moments.json"), {"moments": moments, "ranking_config": cfg["weights"]})
    proj.p("ranking.md").write_text(ranking.report_markdown(moments, {v["id"]: v for v in vids}), encoding="utf-8")
    proj.mark("analyze", "done", moments=len(moments), selected=sum(m["selected"] for m in moments),
              transcripts=len(transcripts), judgments=len(judgments))
    print(f"{'#':>3} {'id':<4} {'vídeo':<22} {'final':>5}  V  H  R  C  Q  T  corte            situação")
    for i, m in enumerate(moments, 1):
        c = m["ranking"]["criteria"]
        print(f"{i:>3} {m['id']:<4} {m['video_id'][:22]:<22} {m['ranking']['final']:>5} "
              f"{c['viralidade']:>2} {c['humor']:>2} {c['reacao']:>2} {c['contexto']:>2} {c['qualidade']:>2} {c['retencao']:>2} "
              f"{m['start']:>6.1f}–{m['end']:<6.1f}s  {m['ranking']['selection_reason']}")
    print(f"transcrições usadas: {len(transcripts)} | avaliações (judgments.json): {len(judgments)} | detalhes: ranking.md")
    return 0


def cmd_analyze(proj, a):
    disc = _videos(proj)
    if proj.p("moments.json").exists() and not a.force:
        return _err("moments.json já existe; use --force para refazer (apaga edições manuais)")
    if not a.legacy:
        return _ranked(proj, refresh=a.refresh)
    moments = []
    for v in disc["videos"]:
        if not (v.get("approved") and v.get("local_path")):
            continue
        windows = ff.rms_windows(v["local_path"], cwd=proj.dir) if v["has_audio"] else []
        scenes = ff.scene_changes(v["local_path"], cwd=proj.dir)
        dead = ff.dead_time(v["local_path"], cwd=proj.dir)
        moments += analysis.analyze_video(v, windows, scenes, dead)
    analysis.number_moments(moments)
    save_json(proj.p("moments.json"), {"moments": moments})
    proj.mark("analyze", "done", moments=len(moments), selected=sum(m["selected"] for m in moments))
    for m in moments:
        print(f"{m['id']} {m['video_id']} {m['start']:.1f}–{m['end']:.1f}s nota {m['score']} "
              f"{'+'.join(m['signals']) or 'sem sinais'} pico={m['peak_time']} {'✔' if m['selected'] else '✘'}")
    return 0


def cmd_rank(proj, a):
    if not proj.p("analysis").exists():
        return _err("rode o analyze antes (não há medições em analysis/)")
    return _ranked(proj)


def cmd_audio(proj, a):
    by = {v["id"]: v for v in _videos(proj)["videos"]}
    if a.full:  # vídeo inteiro: transcrição antes do ranking (contexto/humor)
        for v in by.values():
            if not (v.get("approved") and v.get("local_path")):
                continue
            if not v.get("has_audio"):
                print(f"{v['id']}: vídeo mudo, nada para transcrever")
                continue
            out = f"subs/{v['id']}.full.wav"
            proj.p("subs").mkdir(exist_ok=True)
            rc, o = ff.run(["ffmpeg", "-v", "error", "-y", "-i", v["local_path"], "-vn", "-ac", "1", "-ar", "16000", out],
                           cwd=proj.dir)
            if rc:
                return _err(f"áudio de {v['id']}: {o.strip()[-300:]}")
            print(f"{v['id']} -> {out}")
        return 0
    mom = load_json(proj.p("moments.json"))
    for m in mom["moments"]:
        if not m.get("selected"):
            continue
        if not by[m["video_id"]].get("has_audio"):
            print(f"{m['id']}: vídeo mudo, nada para transcrever")
            continue
        out = f"subs/{m['id']}.wav"
        rc, o = ff.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m['start']:.3f}", "-t", f"{m['end'] - m['start']:.3f}",
                        "-i", m["source"], "-vn", "-ac", "1", "-ar", "16000", out], cwd=proj.dir)
        if rc:
            return _err(f"áudio de {m['id']}: {o.strip()[-300:]}")
        print(f"{m['id']} -> {out}")
    return 0


def cmd_render(proj, a):
    t0 = time.time()
    rc = _render(proj, a)
    if rc == 0:
        e = _record(proj, a.history, time.time() - t0)
        print(f"histórico: {e['slug']} gravado em {a.history} ({len(e['clips'])} clipes, render {e['render_s']}s)")
    return rc


def _render(proj, a):
    disc = _videos(proj)
    by = {v["id"]: v for v in disc["videos"]}
    mom = load_json(proj.p("moments.json"))
    if a.order == "legacy":
        order, notes = timeline.legacy_order(mom["moments"], {i: v["viral_score"] for i, v in by.items()}), ["ordem antiga (legacy)"]
    else:
        order, notes = timeline.smart_order(mom["moments"], list(by.values()))
    if not order:
        return _err("nenhum momento selecionado")
    brand = brandmod.load_brand(proj.dir)
    if not brand["active"]:
        print("aviso: marca do canal desligada (config/brand.json sem channel_handle): sem marca d'água, abertura e tela final")
    entries, lines = [], []

    def add_card(kind, name):
        if not (brand["active"] and brand[kind]["enabled"]):
            return
        _, logo = _brand_assets(proj, brand)
        rc, o = ff.run_drawtext(render.card_args(brand, kind, f"brand/{kind}.txt", f"clips/{name}", brand["fps"],
                                                 preset=a.preset, logo_rel=logo), cwd=proj.dir)
        if rc:
            raise SystemExit(_err(f"{kind}: {o.strip()[-400:]}"))
        entries.append({"moment_id": kind, "clip": f"clips/{name}", "clip_dur": ff.media_info(f"clips/{name}", cwd=proj.dir)["duration_s"]})
        lines.append(f"file '{name}'")
        print(f"{kind}: clips/{name}")

    add_card("intro", "00_intro.mp4")
    for n, m in enumerate(order, 1):
        v = by[m["video_id"]]
        clip = f"clips/{n:02d}_{m['id']}.mp4"
        rc, o = _encode_moment(proj, m, v, clip, render.compilation_filter, brand, a.preset)
        if rc:
            return _err(f"clipe {m['id']}: {o.strip()[-400:]}")
        entries.append({"moment_id": m["id"], "clip": clip, "clip_dur": ff.media_info(clip, cwd=proj.dir)["duration_s"]})
        lines.append(f"file '{pathlib.Path(clip).name}'")
        print(f"clipe {n}: {clip} ({entries[-1]['clip_dur']}s)")
    add_card("outro", "99_outro.mp4")
    proj.p("clips", "list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, o = ff.run(render.concat_args("clips/list.txt", "output/compilation.mp4"), cwd=proj.dir)
    if rc:
        return _err(f"concatenação: {o.strip()[-400:]}")
    timeline.clip_starts(entries)
    chap = timeline.chapters(entries)
    save_json(proj.p("output", "timeline.json"), {"clips": entries, "chapters": chap, "order_notes": notes})
    for n in notes:
        print(f"ordem: {n}")
    save_json(proj.p("output", "chapters.json"), [{"start": c["start"], "moment_ids": c["moment_ids"], "title": None} for c in chap])
    save_json(proj.p("output", "brand_used.json"), {k: brand[k] for k in ("active", "channel_handle", "fps", "transition", "audio_two_pass")})
    info = ff.media_info("output/compilation.mp4", cwd=proj.dir)
    total = sum(e["clip_dur"] for e in entries)
    problems = []
    if round(info["fps"]) != brand["fps"]:
        problems.append(f"fps {info['fps']} ≠ {brand['fps']}")
    if (info["width"], info["height"]) != (1920, 1080):
        problems.append(f"resolução {info['width']}x{info['height']}")
    if not info["has_audio"]:
        problems.append("sem áudio")
    if abs(info["duration_s"] - total) >= 1:
        problems.append(f"duração {info['duration_s']}s ≠ soma {total:.2f}s")
    proj.mark("render", "error" if problems else "done", duration_s=info["duration_s"])
    print(f"output/compilation.mp4: {info['duration_s']}s {info['width']}x{info['height']} | {len(chap)} capítulos")
    return _err("; ".join(problems)) if problems else 0


def _best_frame_time(mom, tl):
    # Momento de maior nota que tenha peak_time; no empate, o mais perto do fim (o compilado fecha com o melhor).
    pos = {e["moment_id"]: i for i, e in enumerate(tl["clips"])}
    starts = {e["moment_id"]: e for e in tl["clips"]}
    with_peak = [m for m in mom["moments"] if m["id"] in pos and m.get("peak_time") is not None]
    if with_peak:
        best = max(with_peak, key=lambda m: (m["score"], pos[m["id"]]))
        return starts[best["id"]]["clip_start"] + (best["peak_time"] - best["start"]), True
    last = tl["clips"][-1]
    return last["clip_start"] + last["clip_dur"] / 2, False


def cmd_thumbnail(proj, a):
    mom = load_json(proj.p("moments.json"))
    tl = load_json(proj.p("output", "timeline.json"))
    if tl is None:
        return _err("rode o render antes (falta output/timeline.json)")
    t, from_peak = _best_frame_time(mom, tl)
    if not from_peak:
        print("aviso: nenhum momento com peak_time; usando o meio do último clipe")
    # sem quebra de linha no final (senão o drawtext desenha uma linha vazia)
    proj.p("output", "thumb_text.txt").write_text("\n".join(a.line), encoding="utf-8")
    rc, o = ff.run_drawtext(render.thumbnail_args("output/compilation.mp4", t, "output/thumb_text.txt",
                                                  "output/thumbnail.jpg"), cwd=proj.dir)
    if rc:
        return _err(f"thumbnail: {o.strip()[-400:]}")
    info = ff.media_info("output/thumbnail.jpg", cwd=proj.dir)
    size = proj.p("output", "thumbnail.jpg").stat().st_size
    print(f"output/thumbnail.jpg: {info['width']}x{info['height']}, {size // 1024} KB, quadro em {t:.2f}s")
    if (info["width"], info["height"]) != (1280, 720) or size >= 2 * 1024 * 1024:
        return _err("thumbnail fora do padrão do YouTube (1280x720, < 2 MB)")
    return 0


def cmd_thumbnails(proj, a):
    mom = load_json(proj.p("moments.json"))
    tl = load_json(proj.p("output", "timeline.json"))
    if tl is None:
        return _err("rode o render antes (falta output/timeline.json)")
    brand = brandmod.load_brand(proj.dir)
    accent = brandmod.ff_color(brand["colors"]["accent"]) if brand["active"] else "yellow"
    out_dir = proj.p("output", "thumbs")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    proj.p("output", "thumb_text.txt").write_text("\n".join(a.line), encoding="utf-8")
    cands = thumbs.candidate_times(mom["moments"], tl, a.count)
    chosen, rejected = thumbs.choose(cands, lambda t: ff.frame_probe("output/compilation.mp4", t, cwd=proj.dir), a.count)
    for mid, t, why in rejected:
        print(f"  descartado {mid} em {t:.2f}s: {why}")
    if not chosen:
        return _err("nenhum quadro passou no filtro de qualidade (todos escuros, borrados ou repetidos)")
    files, items = [], []
    for i, c in enumerate(chosen, 1):
        for style in ("faixa", "topo"):
            name = f"output/thumbs/{len(files) + 1:02d}_{c['moment_id']}_{style}.jpg"
            vf = thumbs.layout_filter(style, "output/thumb_text.txt", accent, brandmod.font_opt(brand))
            rc, o = ff.run_drawtext(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['t']:.2f}", "-i", "output/compilation.mp4",
                                     "-frames:v", "1", "-vf", vf, "-q:v", "2", name], cwd=proj.dir)
            if rc:
                return _err(f"candidata {name}: {o.strip()[-300:]}")
            size = proj.p(name).stat().st_size
            info = ff.media_info(name, cwd=proj.dir)
            if (info["width"], info["height"]) != (1280, 720) or size >= 2 * 1024 * 1024:
                return _err(f"{name} fora do padrão do YouTube (1280x720, < 2 MB)")
            files.append(name)
            items.append({"n": len(files), "file": name, "moment_id": c["moment_id"], "t": c["t"], "style": style,
                          "yavg": c["yavg"], "blur": c["blur"], "kb": size // 1024})
            print(f"{len(files)}: {name} (quadro {c['t']}s, brilho {c['yavg']}, borrão {c['blur']}, {size // 1024} KB)")
    rc, o = ff.run(thumbs.sheet_args(files, "output/thumbs/escolha.jpg"), cwd=proj.dir)
    if rc:
        return _err(f"folha de comparação: {o.strip()[-300:]}")
    save_json(proj.p("output", "thumbs", "candidatas.json"), items)
    print(f"folha de comparação: output/thumbs/escolha.jpg — escolha com: gtakit thumbnail-pick {proj.dir} <número>")
    return 0


def cmd_thumbnail_pick(proj, a):
    items = load_json(proj.p("output", "thumbs", "candidatas.json"))
    if not items:
        return _err("rode o comando thumbnails antes")
    item = next((x for x in items if x["n"] == a.n), None)
    if item is None:
        return _err(f"candidata {a.n} não existe (1 a {len(items)})")
    shutil.copyfile(proj.p(item["file"]), proj.p("output", "thumbnail.jpg"))
    save_json(proj.p("output", "thumbnail_choice.json"), item)
    print(f"output/thumbnail.jpg = candidata {a.n} ({item['style']}, momento {item['moment_id']})")
    return 0


def cmd_shorts(proj, a):
    disc = _videos(proj)
    by = {v["id"]: v for v in disc["videos"]}
    mom = load_json(proj.p("moments.json"))
    cands = sorted([m for m in mom["moments"] if m.get("selected") and m["end"] - m["start"] >= 8],
                   key=lambda m: (-m["score"], -by[m["video_id"]]["viral_score"]))[:a.count]
    proj.p("output", "shorts").mkdir(parents=True, exist_ok=True)
    brand = brandmod.load_brand(proj.dir)
    items = []
    for n, m in enumerate(cands, 1):
        v = by[m["video_id"]]
        start, dur = render.short_window(m)
        out = f"output/shorts/{n:02d}_{m['id']}.mp4"
        keys, conc = [(0.0, 0.5)], 0.0
        if not render.is_vertical(v):
            prof = framing.column_motion(ff.motion_frames(m["source"], start, dur, fps=framing.FPS, cwd=proj.dir))
            path, conc = framing.track(prof)
            keys = framing.keyframes(path)
        try:
            layout, why = framing.choose_layout(v, conc, a.layout)
        except ValueError as exc:
            return _err(str(exc))
        base = framing.base_filter(layout, v, keys, brand["fps"])
        print(f"{m['id']}: enquadramento {layout} — {why}")
        rc, o = _encode_moment(proj, m, v, out, render.short_filter, brand, a.preset, start=start, dur=dur,
                               faststart=True, base=base)
        if rc:
            return _err(f"short {m['id']}: {o.strip()[-400:]}")
        info = ff.media_info(out, cwd=proj.dir)
        ok = (info["width"], info["height"]) == (1080, 1920) and info["has_audio"] and info["duration_s"] <= 60.5
        creator = (v.get("original_creator") or {}).get("name")
        origin = f"{creator} — clipe de {v.get('author_handle')}" if creator else f"{v.get('author')} ({v.get('author_handle')})"
        items.append({"file": pathlib.Path(out).name, "moment_id": m["id"], "title": None,
                      "layout": layout, "layout_reason": why,
                      "description": f"Clipe original: {origin} — {v.get('url')}\n#GTA5 #GTARP #Shorts",
                      "duration_s": info["duration_s"]})
        print(f"{out}: {info['width']}x{info['height']} {info['duration_s']}s {'ok' if ok else 'FORA DO PADRÃO'}")
        if not ok:
            return _err(f"short {m['id']} fora do padrão (1080x1920, com áudio, ≤ 60 s)")
    save_json(proj.p("output", "shorts", "shorts.json"), items)
    proj.mark("shorts", "done", shorts=len(items))
    return 0


def cmd_credit(proj, a):
    disc = _videos(proj)
    v = next((v for v in disc["videos"] if v["id"] == a.video_id), None)
    if v is None:
        return _err(f"vídeo {a.video_id} não está no discovery.json")
    v["original_creator"] = None if a.clear else {"name": a.creator, "url": a.creator_url}
    save_json(proj.p("discovery.json"), disc)
    print(f"{v['id']}: crédito no vídeo = {rights.credit_text(v)!r}; quem autoriza = {rights.owner_of(v)}")
    return 0


def cmd_permissions(proj, a):
    disc = _videos(proj)
    tpl_path = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/gta-video-discovery/permission-template.md"
    templates = rights.parse_templates(tpl_path.read_text(encoding="utf-8"))
    ledger = rights.Ledger(a.ledger)
    channel = a.channel or "<nome do canal>"
    out = ["# Pedidos de permissão", "",
           "Envie você mesmo (DM ou resposta ao post). Depois registre a resposta com `gtakit rights-set`.",
           "Créditos e marca d'água **não** substituem a autorização.", ""]
    seen, problems = set(), []
    for v in disc["videos"]:
        if not v.get("approved"):
            continue
        owner = rights.owner_of(v)
        if ledger.status_for(v) == "granted" or rights.key(owner) in seen:
            continue
        seen.add(rights.key(owner))
        lang = a.lang if a.lang != "auto" else rights.guess_lang(v.get("text"))
        target = dict(v)
        creator = (v.get("original_creator") or {}).get("name")
        if creator:  # o conteúdo é do criador original: o pedido vai para ele
            target["author_handle"] = creator
        out += [f"## {owner}", f"- Post: {v.get('url')}",
                f"- Clipador: {v.get('author_handle')}" if creator else "- Autor do post",
                f"- Idioma: {lang}", ""]
        for kind in ("dm", "reply"):
            tpl = templates.get(lang, templates["pt"]).get(kind)
            if not tpl:
                continue
            msg = rights.fill(tpl, target, channel)
            n = rights.x_length(msg)
            if n > 280:
                problems.append(f"{owner} ({kind}): {n} caracteres")
            out += [f"**{'DM' if kind == 'dm' else 'Resposta ao post'}** ({n}/280)", "```", msg, "```", ""]
    proj.p("permissions.md").write_text("\n".join(out), encoding="utf-8")
    print(f"permissions.md: {len(seen)} pedido(s)")
    if not a.channel:
        print("aviso: nome do canal não informado (--channel); as mensagens ficaram com <nome do canal>")
    return _err("mensagem acima de 280 caracteres: " + "; ".join(problems)) if problems else 0


def cmd_rights_set(a):
    led = rights.Ledger(a.ledger)
    try:
        e = led.set(a.name, a.status, evidence=a.evidence, post_id=a.post, notes=a.notes)
    except ValueError as exc:
        return _err(str(exc))
    print(f"{a.name}: {a.status}{' (post ' + a.post + ')' if a.post else ''} registrado em {led.path}")
    return 0


def cmd_rights_list(a):
    led = rights.Ledger(a.ledger)
    people = led.data["people"]
    if not people:
        print("nenhuma permissão registrada")
    for k, e in sorted(people.items()):
        posts = ", ".join(f"{p}={x['status']}" for p, x in e.get("posts", {}).items())
        print(f"{e['name']:<24} {e.get('status', '-'):<10} {e.get('evidence') or ''} {('posts: ' + posts) if posts else ''}")
    return 0


def cmd_rights_sync(proj, a):
    disc = _videos(proj)
    changes = rights.sync_project(disc, rights.Ledger(a.ledger))
    save_json(proj.p("discovery.json"), disc)
    for c in changes:
        print(f"{c[0]}: {c[1]} -> {c[2]}")
    print(f"{len(changes)} alteração(ões)")
    return 0


def cmd_ready(proj, a):
    disc = _videos(proj)
    rights.sync_project(disc, rights.Ledger(a.ledger))
    save_json(proj.p("discovery.json"), disc)
    used = _used_videos(proj)
    if not used:
        return _err("nenhum vídeo usado ainda (rode o render ou o shorts antes)")
    res = rights.publish_check(used, {"reason": a.accept_risk} if a.accept_risk else None)
    save_json(proj.p("output", "publish_check.json"), res)
    for p in res["pending"]:
        print(f"  sem permissão: {p['id']} — falta autorização de {p['owner']} ({p['rights']})")
    if res["override"]:
        print(f"RISCO ACEITO PELO USUÁRIO: {res['override']['reason']}")
    print("PRONTO PARA PUBLICAR" if res["publish_ready"] else "BLOQUEADO: faltam permissões (veja acima)")
    proj.mark("publish", "ready" if res["publish_ready"] else "blocked")
    return 0 if res["publish_ready"] else 3


def cmd_facecam(proj, a):
    disc = _videos(proj)
    v = next((v for v in disc["videos"] if v["id"] == a.video_id), None)
    if v is None:
        return _err(f"vídeo {a.video_id} não está no discovery.json")
    if a.clear:
        v["facecam"] = None
    else:
        try:
            x, y, w, h = (float(n) for n in a.box.split(","))
        except ValueError:
            return _err("--box precisa de 4 números entre 0 e 1: x,y,largura,altura (ex.: 0.75,0.70,0.25,0.30)")
        if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-6 and 0 < h <= 1 - y + 1e-6):
            return _err("a região precisa caber na imagem (frações de 0 a 1)")
        v["facecam"] = {"x": x, "y": y, "w": w, "h": h}
    save_json(proj.p("discovery.json"), disc)
    print(f"{v['id']}: câmera do streamer = {v['facecam']}")
    return 0


def cmd_history_record(proj, a):
    e = _record(proj, a.history)
    print(f"histórico: {e['slug']} ({len(e['clips'])} clipes, {e['duration_s']}s) em {a.history}")
    return 0


def cmd_published(proj, a):
    yid = history.youtube_id(a.url)
    if not yid:
        return _err("link do YouTube inválido (use o link do vídeo ou do Short)")
    entries = history.load(a.history)
    if not any(e["slug"] == proj.dir.name for e in entries):
        entries = history.upsert(entries, _history_entry(proj))
    for e in entries:
        if e["slug"] == proj.dir.name:
            e["youtube"] = {"video_id": yid, "url": a.url, "title": a.title, "published_at": a.at or now_iso_str()}
    history.save(entries, a.history)
    proj.mark("publish", "published", youtube=yid)
    print(f"{proj.dir.name}: publicado em {a.url}")
    return 0


def cmd_metrics_import(a):
    try:
        rows = history.parse_studio_csv(a.csv)
    except (OSError, ValueError) as exc:
        return _err(f"CSV do YouTube Studio: {exc}")
    entries = history.load(a.history)
    unmatched = history.apply_metrics(entries, rows, now_iso_str())
    history.save(entries, a.history)
    print(f"{len(rows) - len(unmatched)} vídeo(s) associados a compilados do histórico")
    for u in unmatched:
        print(f"  não associado (publique com `gtakit published` para ligar o link): {u}")
    return 0


def cmd_report(a):
    print(history.report(history.load(a.history)))
    return 0


def cmd_validate(proj, a):
    errors = proj.validate()
    for e in errors:
        print(f"  ✘ {e}")
    print("contratos ok" if not errors else f"{len(errors)} problema(s)")
    return 1 if errors else 0


def cmd_status(proj, a):
    st = proj.state()
    for s in ("discovery", "analyze", "translate", "render", "publish", "shorts"):
        info = st.get("stages", {}).get(s)
        print(f"{s:<10} {info['status'] + ' em ' + info['at'] if info else 'pendente'}")
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # o console do Windows não é UTF-8 por padrão
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="gtakit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("project", help="pasta do projeto, ex.: projects/fails-gta-20261124")
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init).add_argument("--theme", default=None)
    s = add("discovery", cmd_discovery)
    s.add_argument("--now", type=float, default=None, help="(testes) horário atual em epoch")
    s.add_argument("--history", default=history.DEFAULT_HISTORY)
    s = add("approve", cmd_approve)
    s.add_argument("ids", nargs="*")
    s.add_argument("--all", action="store_true")
    s.add_argument("--reject", action="store_true")
    add("probe", cmd_probe)
    s = add("analyze", cmd_analyze)
    s.add_argument("--force", action="store_true")
    s.add_argument("--legacy", action="store_true", help="regras antigas (picos de volume), sem ranking")
    s.add_argument("--refresh", action="store_true", help="ignora o cache de medições")
    add("rank", cmd_rank)
    add("audio", cmd_audio).add_argument("--full", action="store_true")
    s = add("render", cmd_render)
    s.add_argument("--preset", default="medium")
    s.add_argument("--history", default=history.DEFAULT_HISTORY)
    s.add_argument("--order", default="smart", choices=["smart", "legacy"],
                   help="smart: gancho no início, melhor no fim, sem criador repetido em sequência")
    add("thumbnail", cmd_thumbnail).add_argument("--line", action="append", required=True, help="uma linha do texto (repita para 2 linhas)")
    s = add("thumbnails", cmd_thumbnails)
    s.add_argument("--line", action="append", required=True, help="uma linha do texto (repita para 2 linhas)")
    s.add_argument("--count", type=int, default=4, help="quantos momentos diferentes (3–5)")
    add("thumbnail-pick", cmd_thumbnail_pick).add_argument("n", type=int)
    s = add("shorts", cmd_shorts)
    s.add_argument("--count", type=int, default=3)
    s.add_argument("--layout", default="auto", choices=["auto", "crop", "split", "blur"],
                   help="auto: escolhe por vídeo (vertical, câmera marcada, ação concentrada ou espalhada)")
    s.add_argument("--preset", default="medium")
    s = add("credit", cmd_credit)
    s.add_argument("video_id")
    s.add_argument("--creator", help="nome do criador original, ex.: alanzoka")
    s.add_argument("--creator-url", default=None)
    s.add_argument("--clear", action="store_true")
    s = add("permissions", cmd_permissions)
    s.add_argument("--channel", default=None, help="nome do seu canal (vai nas mensagens)")
    s.add_argument("--lang", default="auto", choices=["auto", "pt", "en", "es"])
    s.add_argument("--ledger", default=rights.DEFAULT_LEDGER)
    s = add("rights-sync", cmd_rights_sync)
    s.add_argument("--ledger", default=rights.DEFAULT_LEDGER)
    s = add("ready", cmd_ready)
    s.add_argument("--accept-risk", default=None, metavar="MOTIVO",
                   help="só com decisão explícita do usuário: publica mesmo sem permissão, registrando o motivo")
    s.add_argument("--ledger", default=rights.DEFAULT_LEDGER)
    # comandos do registro de permissões (não dependem de um projeto)
    s = sub.add_parser("rights-set")
    s.add_argument("name", help="@handle ou nome de quem autorizou/negou")
    s.add_argument("--status", required=True, choices=rights.STATUSES)
    s.add_argument("--evidence", default=None, help="link da resposta ou caminho do print (obrigatório para granted)")
    s.add_argument("--post", default=None, help="post_id, se a permissão vale só para um post")
    s.add_argument("--notes", default=None)
    s.add_argument("--ledger", default=rights.DEFAULT_LEDGER)
    s.set_defaults(fn=cmd_rights_set, project=None)
    s = sub.add_parser("rights-list")
    s.add_argument("--ledger", default=rights.DEFAULT_LEDGER)
    s.set_defaults(fn=cmd_rights_list, project=None)
    s = add("facecam", cmd_facecam)
    s.add_argument("video_id")
    s.add_argument("--box", help="x,y,largura,altura em frações da imagem (0 a 1)")
    s.add_argument("--clear", action="store_true")
    add("history-record", cmd_history_record).add_argument("--history", default=history.DEFAULT_HISTORY)
    s = add("published", cmd_published)
    s.add_argument("--url", required=True, help="link do vídeo publicado no YouTube")
    s.add_argument("--title", default=None)
    s.add_argument("--at", default=None, help="data/hora da publicação (padrão: agora)")
    s.add_argument("--history", default=history.DEFAULT_HISTORY)
    s = sub.add_parser("metrics-import")
    s.add_argument("csv", help="CSV exportado do YouTube Studio (Análises > Modo avançado > Exportar)")
    s.add_argument("--history", default=history.DEFAULT_HISTORY)
    s.set_defaults(fn=cmd_metrics_import, project=None)
    s = sub.add_parser("report")
    s.add_argument("--history", default=history.DEFAULT_HISTORY)
    s.set_defaults(fn=cmd_report, project=None)
    add("validate", cmd_validate)
    add("status", cmd_status)
    a = ap.parse_args(argv)
    if a.project is None:  # comandos do registro de permissões
        return a.fn(a)
    proj = Project(a.project)
    try:
        ff.require_tools()
        return a.fn(proj, a)
    except ff.FFmpegError as e:
        return _err(str(e))


if __name__ == "__main__":
    sys.exit(main())
