"""Linha de comando do gtakit. Rode a partir da raiz do repositório:

    py -3 -m gtakit <comando> projects/<slug> [opções]     (Windows)
    python3 -m gtakit <comando> projects/<slug> [opções]   (Linux/macOS)

Comandos (na ordem do fluxo):
  init       cria a pasta do projeto
  discovery  lê raw_meta.jsonl (saída do yt-dlp --dump-json) e gera discovery.json com a nota de viralidade
  approve    marca vídeos aprovados/recusados pelo usuário
  probe      confere os vídeos baixados em source/ (duração, tamanho, áudio)
  analyze    mede áudio/cenas/tempo morto e gera moments.json
  audio      extrai o áudio de cada momento (subs/<id>.wav) para a transcrição
  render     corta, padroniza e junta os clipes; gera output/compilation.mp4 e output/timeline.json
  thumbnail  gera output/thumbnail.jpg no pico do melhor momento
  shorts     gera os Shorts verticais em output/shorts/
  validate   confere os contratos JSON entre as etapas
  status     mostra o estado das etapas
"""
import argparse
import datetime
import pathlib
import re
import sys
import time

from . import analysis, ff, render, timeline, viral
from .project import Project, load_json, save_json


def _err(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    return 1


def _videos(proj):
    disc = load_json(proj.p("discovery.json"))
    if disc is None:
        raise SystemExit(_err("discovery.json não existe; rode o comando discovery antes"))
    return disc


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


def cmd_analyze(proj, a):
    disc = _videos(proj)
    if proj.p("moments.json").exists() and not a.force:
        return _err("moments.json já existe; use --force para refazer (apaga edições manuais)")
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


def cmd_audio(proj, a):
    mom = load_json(proj.p("moments.json"))
    by = {v["id"]: v for v in _videos(proj)["videos"]}
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
    disc = _videos(proj)
    by = {v["id"]: v for v in disc["videos"]}
    mom = load_json(proj.p("moments.json"))
    order = timeline.legacy_order(mom["moments"], {i: v["viral_score"] for i, v in by.items()})
    if not order:
        return _err("nenhum momento selecionado")
    entries, lines = [], []
    for n, m in enumerate(order, 1):
        v = by[m["video_id"]]
        clip = f"clips/{n:02d}_{m['id']}.mp4"
        vf = render.compilation_filter(v, m.get("subtitle_pt"), v.get("author_handle"))
        rc, o = ff.run_drawtext(render.encode_args(m["source"], m["start"], m["end"] - m["start"], v["has_audio"],
                                                   vf, clip, preset=a.preset), cwd=proj.dir)
        if rc:
            return _err(f"clipe {m['id']}: {o.strip()[-400:]}")
        entries.append({"moment_id": m["id"], "clip": clip, "clip_dur": ff.media_info(clip, cwd=proj.dir)["duration_s"]})
        lines.append(f"file '{pathlib.Path(clip).name}'")
        print(f"clipe {n}: {clip} ({entries[-1]['clip_dur']}s)")
    proj.p("clips", "list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, o = ff.run(render.concat_args("clips/list.txt", "output/compilation.mp4"), cwd=proj.dir)
    if rc:
        return _err(f"concatenação: {o.strip()[-400:]}")
    timeline.clip_starts(entries)
    chap = timeline.chapters(entries)
    save_json(proj.p("output", "timeline.json"), {"clips": entries, "chapters": chap})
    save_json(proj.p("output", "chapters.json"), [{"start": c["start"], "moment_ids": c["moment_ids"], "title": None} for c in chap])
    info = ff.media_info("output/compilation.mp4", cwd=proj.dir)
    total = sum(e["clip_dur"] for e in entries)
    problems = []
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


def cmd_shorts(proj, a):
    disc = _videos(proj)
    by = {v["id"]: v for v in disc["videos"]}
    mom = load_json(proj.p("moments.json"))
    cands = sorted([m for m in mom["moments"] if m.get("selected") and m["end"] - m["start"] >= 8],
                   key=lambda m: (-m["score"], -by[m["video_id"]]["viral_score"]))[:a.count]
    proj.p("output", "shorts").mkdir(parents=True, exist_ok=True)
    items = []
    for n, m in enumerate(cands, 1):
        v = by[m["video_id"]]
        start, dur = render.short_window(m)
        out = f"output/shorts/{n:02d}_{m['id']}.mp4"
        vf = render.short_filter(v, m.get("subtitle_pt"), v.get("author_handle"))
        rc, o = ff.run_drawtext(render.encode_args(m["source"], start, dur, v["has_audio"], vf, out,
                                                   preset=a.preset, faststart=True), cwd=proj.dir)
        if rc:
            return _err(f"short {m['id']}: {o.strip()[-400:]}")
        info = ff.media_info(out, cwd=proj.dir)
        ok = (info["width"], info["height"]) == (1080, 1920) and info["has_audio"] and info["duration_s"] <= 60.5
        items.append({"file": pathlib.Path(out).name, "moment_id": m["id"], "title": None,
                      "description": f"Clipe original: {v.get('author')} ({v.get('author_handle')}) — {v.get('url')}\n#GTA5 #GTARP #Shorts",
                      "duration_s": info["duration_s"]})
        print(f"{out}: {info['width']}x{info['height']} {info['duration_s']}s {'ok' if ok else 'FORA DO PADRÃO'}")
        if not ok:
            return _err(f"short {m['id']} fora do padrão (1080x1920, com áudio, ≤ 60 s)")
    save_json(proj.p("output", "shorts", "shorts.json"), items)
    proj.mark("shorts", "done", shorts=len(items))
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
    add("discovery", cmd_discovery).add_argument("--now", type=float, default=None, help="(testes) horário atual em epoch")
    s = add("approve", cmd_approve)
    s.add_argument("ids", nargs="*")
    s.add_argument("--all", action="store_true")
    s.add_argument("--reject", action="store_true")
    add("probe", cmd_probe)
    add("analyze", cmd_analyze).add_argument("--force", action="store_true")
    add("audio", cmd_audio)
    add("render", cmd_render).add_argument("--preset", default="medium")
    add("thumbnail", cmd_thumbnail).add_argument("--line", action="append", required=True, help="uma linha do texto (repita para 2 linhas)")
    s = add("shorts", cmd_shorts)
    s.add_argument("--count", type=int, default=3)
    s.add_argument("--preset", default="medium")
    add("validate", cmd_validate)
    add("status", cmd_status)
    a = ap.parse_args(argv)
    proj = Project(a.project)
    try:
        ff.require_tools()
        return a.fn(proj, a)
    except ff.FFmpegError as e:
        return _err(str(e))


if __name__ == "__main__":
    sys.exit(main())
