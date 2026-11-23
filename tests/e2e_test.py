"""Teste ponta a ponta das skills com vídeos sintéticos.

Executa as regras e os comandos ffmpeg descritos nos SKILL.md, do discovery ao
publisher, e falha (código 1) se alguma verificação não passar.

Simulado (não há rede do X nem Whisper no teste): metadados do yt-dlp e transcrição.
IMPORTANTE: ao mudar um comando ou regra em um SKILL.md, atualize este arquivo também.

Uso:  python3 tests/e2e_test.py [--keep]   (--keep mantém a pasta temporária)
Requer: ffmpeg/ffprobe com libx264, libass (subtitles) e drawtext.
"""
import json, math, os, pathlib, re, shutil, statistics as st, subprocess as sp, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
failures = []


def check(ok, msg):
    print(("  OK    " if ok else "  FALHA ") + msg)
    if not ok:
        failures.append(msg)


def sh(cmd, cwd):
    r = sp.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout + r.stderr


# Fonte para o drawtext: só é usada se o ffmpeg não achar uma sozinho (comum no Windows).
# É a mesma correção descrita na skill video-editor.
FONTFILE = None
FONT_CANDIDATES = {"nt": "C\\:/Windows/Fonts/arial.ttf",
                   "posix": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"}


def with_font(cmd):
    return cmd.replace("drawtext=", f"drawtext=fontfile='{FONTFILE}':") if FONTFILE else cmd


def sh_drawtext(cmd, cwd):
    """Roda um comando com drawtext; se faltar fonte, aplica o fontfile da skill e tenta de novo."""
    global FONTFILE
    rc, o = sh(with_font(cmd), cwd)
    if rc and FONTFILE is None and "font" in o.lower():
        FONTFILE = FONT_CANDIDATES.get(os.name)
        print(f"  (ffmpeg sem fonte padrão; usando fontfile={FONTFILE}, como manda a skill video-editor)")
        rc, o = sh(with_font(cmd), cwd)
    return rc, o


def probe(f, entries, cwd):
    return sh(f"ffprobe -v error {entries} -of csv=p=0 {f}", cwd)[1].strip()


# ---------------------------------------------------------------- skills
def test_frontmatter():
    print("== Cabeçalho das skills")
    skills = sorted((REPO / ".claude/skills").glob("*/SKILL.md"))
    check(len(skills) >= 6, f"{len(skills)} skills encontradas (esperado ≥ 6)")
    for f in skills:
        m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", f.read_text(encoding="utf-8"))
        check(bool(m) and m.group(1) == f.parent.name and len(m.group(2)) <= 1024,
              f"{f.parent.name}: name/description válidos")


# ---------------------------------------------------------------- vídeos sintéticos
VIDEO = {"t": "testsrc2", "r": "color=red", "g": "color=gray", "m": "mandelbrot"}
AUDIO = {"low": "sine=f=300:sample_rate=48000,volume=0.03",
         "loud": "sine=f=900:sample_rate=48000,volume=1",
         "mute": "anullsrc=r=48000:cl=mono"}


def make_video(out, segments, w=1280, h=720, keep_audio=True, cwd=None):
    """segments: lista de (padrão de vídeo, duração, tipo de áudio)."""
    inputs, labels = [], ""
    for i, (v, d, a) in enumerate(segments):
        sep = ":" if "=" in VIDEO[v] else "="  # "color=red:s=..." vs "testsrc2=s=..."
        inputs.append(f'-f lavfi -i "{VIDEO[v]}{sep}s={w}x{h}:r=30,trim=duration={d},format=yuv420p,setpts=PTS-STARTPTS"')
        # aformat: sem ele o anullsrc (8 bits) força o concat a 8 bits e o som baixo vira zero
        inputs.append(f'-f lavfi -i "{AUDIO[a]},atrim=duration={d},aformat=sample_fmts=fltp"')
        labels += f"[{2*i}:v][{2*i+1}:a]"
    n = len(segments)
    amap = '-map "[a]" -c:a aac -ac 2' if keep_audio else "-an"
    sink = "" if keep_audio else ";[a]anullsink"  # vídeo mudo: descarta o áudio do concat
    rc, o = sh(f'ffmpeg -v error -y {" ".join(inputs)} -filter_complex "{labels}concat=n={n}:v=1:a=1[v][a]{sink}" '
               f'-map "[v]" {amap} -c:v libx264 -preset ultrafast {out}', cwd)
    if rc:
        sys.exit(f"Falha ao gerar {out}: {o}")


# ---------------------------------------------------------------- pipeline
def run_pipeline(root):
    P = root / "projects/teste"
    for d in ("source", "subs", "clips", "output"):
        (P / d).mkdir(parents=True, exist_ok=True)
    src = "projects/teste/source"
    # v1: grito + cena aos 12 s | v2: vertical, 2 s de tempo morto, grito aos 9 s
    # v3: mudo, cena aos 10 s  | v4: curto (6 s) | v5: sem eventos, engajamento zero
    # v6: só silêncio + um grito aos 8 s
    make_video(f"{src}/v1.mp4", [("t", 12, "low"), ("r", 2, "loud"), ("m", 11, "low")], cwd=root)
    make_video(f"{src}/v2.mp4", [("g", 2, "mute"), ("t", 7, "low"), ("t", 1.5, "loud"), ("t", 5.5, "low")],
               w=720, h=1280, cwd=root)
    make_video(f"{src}/v3.mp4", [("t", 10, "low"), ("m", 10, "low")], keep_audio=False, cwd=root)
    make_video(f"{src}/v4.mp4", [("t", 3, "low"), ("r", 1, "loud"), ("t", 2, "low")], cwd=root)
    make_video(f"{src}/v5.mp4", [("t", 30, "low")], cwd=root)
    make_video(f"{src}/v6.mp4", [("t", 8, "mute"), ("t", 1, "loud"), ("t", 6, "mute")], cwd=root)

    # ---- 1. gta-video-discovery (metadados simulados) ----
    print("== 1. gta-video-discovery")
    fake = {"v1": ("Ana", "@ana_gta", 51000, 8200, 640, 48), "v2": ("Beto", "@beto_rp", 900, None, 30, 5),
            "v3": ("Caio", "@caio", 12000, 1500, None, 200), "v4": ("Dani", "@dani", 3000, 200, 50, 20),
            "v5": ("Edu", "@edu", 0, 0, 0, 3), "v6": ("Fê", "@fe", 500, 20, 10, 10)}
    vids = []
    for vid, (author, handle, likes, reposts, comments, hours) in fake.items():
        path = f"{src}/{vid}.mp4"
        eng = (likes or 0) + 2 * (reposts or 0) + (comments or 0)
        w, h = map(int, probe(path, "-select_streams v:0 -show_entries stream=width,height", root).split(","))
        vids.append(dict(id=vid, author=author, author_handle=handle, post_id=vid,
                         url=f"https://x.com/{handle[1:]}/status/{vid}", eng=eng, vel=eng / max(1, hours),
                         width=w, height=h, local_path=path,
                         duration_s=float(probe(path, "-show_entries format=duration", root)),
                         has_audio="audio" in probe(path, "-show_entries stream=codec_type", root)))
    for k in ("eng", "vel"):
        mx = max(v[k] for v in vids)
        for v in vids:
            v[k + "_n"] = 0 if mx == 0 else math.log10(v[k] + 1) / math.log10(mx + 1)
    for v in vids:
        v["viral_score"] = round(60 * v["eng_n"] + 40 * v["vel_n"])
    by = {v["id"]: v for v in vids}
    check(by["v5"]["viral_score"] == 0, "engajamento zero → nota 0 (sem divisão por zero)")
    check(by["v1"]["viral_score"] == 100, "vídeo mais engajado → nota 100")
    check(not by["v3"]["has_audio"] and by["v1"]["has_audio"], "has_audio detecta vídeo mudo")
    (P / "discovery.json").write_text(json.dumps({"videos": vids}, indent=1))

    # ---- 2. viral-moment-analyzer ----
    print("== 2. viral-moment-analyzer")
    moments = []
    for v in vids:
        path, sig, peaks, loudest = v["local_path"], [], [], None
        if v["has_audio"]:
            rms = f"projects/teste/subs/{v['id']}_rms.txt"
            sh(f'ffmpeg -v error -i {path} -af "aresample=48000,asetnsamples=n=24000:p=0,astats=metadata=1:reset=1,'
               f'ametadata=print:key=lavfi.astats.Overall.RMS_level:file={rms}" -f null -', root)
            t = (root / rms).read_text()
            win = [(float(a), float(b)) for a, b in zip(re.findall(r"pts_time:([\d.]+)", t),
                                                        re.findall(r"RMS_level=(\S+)", t))]
            win = [(a, max(b, -60.0)) for a, b in win]  # silêncio conta como -60 dB
            med = st.median(b for _, b in win) if win else 0
            peaks = [a for a, b in win if b > -60 and b >= med + 6]
            loudest = max(((b, a) for a, b in win if a in peaks), default=None)
        _, out = sh(f"ffmpeg -i {path} -vf \"select='gt(scene,0.4)',showinfo\" -f null - 2>&1", root)
        scenes = [float(x) for x in re.findall(r"pts_time:([\d.]+)", out)]
        rc, out = sh(f"ffmpeg -i {path} -af silencedetect=noise=-40dB:d=1 -vf freezedetect=n=0.003:d=1 "
                     f"-f null - 2>&1", root)
        check(rc == 0, f"{v['id']}: comando de tempo morto roda")
        sil_s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
        sil_e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
        frz_s = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
        frz_e = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", out)]
        dur, start = v["duration_s"], 0.0
        if sil_s and frz_s and sil_s[0] < 0.1 and frz_s[0] < 0.1:
            start = round(min(sil_e[0] if sil_e else dur, frz_e[0] if frz_e else dur), 2)
        if peaks: sig.append("audio_peak")
        if scenes: sig.append("scene_change")
        if any(0 < p - q <= 2 for p in peaks for q in peaks + scenes): sig.append("reaction")
        score = 30 * ("audio_peak" in sig) + 25 * ("scene_change" in sig) + 25 * ("reaction" in sig) + 20
        # peak_time: pico de áudio mais alto; senão 1ª mudança de cena; senão null (regra da skill)
        in_cut = [s_ for s_ in scenes if start <= s_ <= dur]
        peak_time = loudest[1] if loudest else (in_cut[0] if in_cut else None)
        moments.append(dict(id=f"m{len(moments)+1:02d}", video_id=v["id"], source=path, start=start,
                            end=round(dur, 2), score=score, signals=sig, peaks=peaks, peak_time=peak_time,
                            selected=bool({"audio_peak", "scene_change"} & set(sig)) and score >= 45))
    m = {x["video_id"]: x for x in moments}
    check(all(x["peak_time"] is not None and x["start"] <= x["peak_time"] <= x["end"]
              for x in moments if x["selected"]), "todo momento selecionado tem peak_time dentro do corte")
    check(11.5 <= m["v1"]["peak_time"] <= 14 and 9.5 <= m["v3"]["peak_time"] <= 10.5,
          "peak_time no grito (v1) e na mudança de cena do vídeo mudo (v3)")
    check(any(11.5 <= p <= 14 for p in m["v1"]["peaks"]), "v1: grito aos 12 s detectado")
    check(any(8.5 <= p <= 10.5 for p in m["v2"]["peaks"]), "v2: grito aos 9 s detectado mesmo com trecho mudo")
    check(not m["v5"]["peaks"], "v5: sem picos falsos em áudio constante")
    check(any(7.5 <= p <= 9 for p in m["v6"]["peaks"]), "v6: grito detectado em vídeo quase todo mudo")
    check(m["v2"]["start"] == 2.0, "v2: 2 s de tempo morto inicial cortados")
    check("scene_change" in m["v3"]["signals"], "v3 (mudo): mudança de cena detectada")
    check(not m["v5"]["selected"] and all(m[k]["selected"] for k in ("v1", "v2", "v3", "v4", "v6")),
          "nota mínima descarta só o vídeo sem eventos")

    # ---- 3. video-translator (Whisper simulado) ----
    print("== 3. video-translator")
    whisper = {"v1": ("en", "1\n00:00:11,500 --> 00:00:14,000\nNo way! Did you see that?\n"),
               "v2": ("pt", "1\n00:00:07,000 --> 00:00:09,000\nOlha isso mano\n"), "v4": ("en", "")}
    for x in moments:
        lang, srt = whisper.get(x["video_id"], (None, ""))
        words = len(re.findall(r"[A-Za-zÀ-ú]+", re.sub(r"\d|-->|:|,", " ", srt)))
        x["needs_translation"] = bool(lang and lang != "pt" and words >= 3)
        if x["needs_translation"]:
            (P / f"subs/{x['id']}.pt.srt").write_text(
                srt.replace("No way! Did you see that?", "Não acredito! Viu isso?"), encoding="utf-8")
            x["subtitle_pt"] = f"projects/teste/subs/{x['id']}.pt.srt"
    check([x["video_id"] for x in moments if x["needs_translation"]] == ["v1"],
          "só a fala em inglês com conteúdo recebe legenda")

    # ---- 4. video-editor ----
    print("== 4. video-editor")
    sel = sorted([x for x in moments if x["selected"]], key=lambda x: (-x["score"], -by[x["video_id"]]["viral_score"]))
    order = [sel[1]] + sel[2:] + [sel[0]] if len(sel) > 2 else sel
    lst = []
    for i, x in enumerate(order, 1):
        v = by[x["video_id"]]
        base = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=20:2[bg];"
                "[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,fps=30,") if v["height"] > v["width"] else \
               "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,"
        subs = (f"subtitles={x['subtitle_pt']}:force_style='FontSize=22,Outline=2,MarginV=40',"
                if x.get("subtitle_pt") else "")
        vf = base + subs + f"drawtext=text='{v['author_handle']}':x=w-tw-30:y=30:fontsize=28:fontcolor=white:borderw=2"
        silence = "" if v["has_audio"] else "-f lavfi -i anullsrc=r=48000:cl=stereo -map 0:v -map 1:a -shortest"
        loud = '-af "loudnorm=I=-14:TP=-1.5:LRA=11"' if v["has_audio"] else ""
        out = f"projects/teste/clips/{i:02d}_{x['id']}.mp4"
        rc, o = sh_drawtext(f'ffmpeg -v error -y -ss {x["start"]} -t {x["end"] - x["start"]:.3f} -i {x["source"]} {silence} '
                   f'-vf "{vf}" {loud} -ar 48000 -ac 2 -c:v libx264 -preset ultrafast -crf 20 -c:a aac -b:a 192k {out}',
                   root)
        check(rc == 0, f"clipe {x['id']} ({'vertical' if v['height'] > v['width'] else 'horizontal'}"
                       f"{', mudo' if not v['has_audio'] else ''}{', legenda' if subs else ''}) renderizado"
              + ("" if rc == 0 else f": {o.strip()[-300:]}"))
        if rc == 0:
            x["clip_dur"] = float(probe(out, "-show_entries format=duration", root))
            lst.append(f"file '{pathlib.Path(out).name}'")
    (P / "clips/list.txt").write_text("\n".join(lst) + "\n")
    final = "projects/teste/output/compilation.mp4"
    rc, o = sh(f"ffmpeg -v error -y -f concat -safe 0 -i projects/teste/clips/list.txt -c copy "
               f"-movflags +faststart {final}", root)
    check(rc == 0, "concatenação sem recodificar" + ("" if rc == 0 else f": {o[-300:]}"))
    if rc:
        return
    chap, t, pend = [], 0.0, None
    t_clip = 0.0
    for x in order:  # clip_start: onde cada clipe começa no compilado (regra da video-editor)
        if "clip_dur" in x:
            x["clip_start"] = round(t_clip, 3); t_clip += x["clip_dur"]
    for x in order:
        if "clip_dur" not in x: continue
        if pend: pend["moment_ids"].append(x["id"]); pend["dur"] += x["clip_dur"]
        else: pend = dict(start=round(t, 2), moment_ids=[x["id"]], dur=x["clip_dur"])
        t += x["clip_dur"]
        if pend["dur"] >= 10: chap.append(pend); pend = None
    if pend:  # último clipe < 10 s → junta ao capítulo anterior
        if chap: chap[-1]["moment_ids"] += pend["moment_ids"]; chap[-1]["dur"] += pend["dur"]
        else: chap.append(pend)

    info = json.loads(sh(f"ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,duration "
                         f"-show_entries format=duration -of json {final}", root)[1])
    s = {x["codec_type"]: x for x in info["streams"]}
    fd, soma = float(info["format"]["duration"]), sum(x.get("clip_dur", 0) for x in order)
    check(s.get("video", {}).get("codec_name") == "h264" and s["video"]["width"] == 1920
          and s["video"]["height"] == 1080, "vídeo final h264 1920x1080")
    check(s.get("audio", {}).get("codec_name") == "aac", "áudio final aac presente")
    check(abs(fd - soma) < 1, f"duração {fd:.2f}s ≈ soma dos clipes {soma:.2f}s")
    check(abs(float(s["video"]["duration"]) - float(s["audio"]["duration"])) < 0.2, "áudio e vídeo sincronizados")
    check(chap and chap[0]["start"] == 0 and len(chap) >= 3 and all(c["dur"] >= 10 for c in chap),
          f"capítulos válidos para o YouTube ({len(chap)}, todos ≥ 10 s, 1º em 00:00)")

    # ---- 5. youtube-publisher ----
    print("== 5. youtube-publisher")
    used = {x["video_id"] for x in order if "clip_dur" in x}
    fmt = lambda sec: f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"
    desc = ["⏱️ Capítulos"] + [f"{fmt(c['start'])} Momento {' + '.join(c['moment_ids'])}" for c in chap]
    desc += ["", "🎮 Créditos"] + [f"{v['author']} ({v['author_handle']}) — {v['url']}" for v in vids if v["id"] in used]
    text = "\n".join(desc)
    (P / "output/description.txt").write_text(text + "\n", encoding="utf-8")
    check(text.splitlines()[1].startswith("00:00"), "descrição começa os capítulos em 00:00")
    check(all(by[k]["author_handle"] in text for k in used), "todos os autores usados estão nos créditos")

    # thumbnail: quadro do pico do melhor momento (o que fecha o compilado), texto via textfile
    best = order[-1]
    t_best = best["clip_start"] + (best["peak_time"] - best["start"])  # fórmula da youtube-publisher
    check(best["clip_start"] <= t_best <= best["clip_start"] + best["clip_dur"], "quadro da thumbnail cai dentro do clipe certo")
    (P / "output/thumb_text.txt").write_text("NÃO ACREDITO:\nCAPOTOU!", encoding="utf-8")  # acento, ':' e '!'
    thumb = "projects/teste/output/thumbnail.jpg"
    rc, o = sh_drawtext(
        f'ffmpeg -v error -y -ss {t_best:.2f} -i {final} -frames:v 1 -vf "scale=1280:720:force_original_aspect_ratio=increase,'
        f'crop=1280:720,eq=saturation=1.3:contrast=1.1,drawbox=y=ih*0.55:w=iw:h=ih*0.45:color=black@0.45:t=fill,'
        f'drawtext=textfile=projects/teste/output/thumb_text.txt:fontsize=120:fontcolor=yellow:borderw=8:'
        f'bordercolor=black:line_spacing=10:x=50:y=h-th-50" -q:v 2 {thumb}', root)
    check(rc == 0, "thumbnail gerada" + ("" if rc == 0 else f": {o.strip()[-300:]}"))
    if rc == 0:
        check(probe(thumb, "-show_entries stream=width,height", root) == "1280,720", "thumbnail em 1280x720")
        check((root / thumb).stat().st_size < 2 * 1024 * 1024, "thumbnail com menos de 2 MB (limite do YouTube)")

    # ---- 6. youtube-shorts ----
    print("== 6. youtube-shorts")
    (P / "output/shorts").mkdir(parents=True, exist_ok=True)
    # um horizontal com legenda (v1), um vertical (v2) e um mudo (v3): cobre todos os caminhos da skill
    for n, vid in enumerate(("v1", "v2", "v3"), 1):
        x = next(m for m in moments if m["video_id"] == vid)
        v = by[vid]
        start = x["start"]
        dur = min(x["end"] - x["start"], 60.0)
        base = ("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,"
                if v["height"] > v["width"] else
                "split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
                "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,")
        subs = (f"subtitles={x['subtitle_pt']}:force_style='FontSize=13,Bold=1,Outline=3,MarginV=70,Alignment=2',"
                if x.get("subtitle_pt") else "")
        vf = base + subs + f"drawtext=text='{v['author_handle']}':x=(w-tw)/2:y=160:fontsize=48:fontcolor=white:borderw=3"
        silence = "" if v["has_audio"] else "-f lavfi -i anullsrc=r=48000:cl=stereo -map 0:v -map 1:a -shortest"
        loud = '-af "loudnorm=I=-14:TP=-1.5:LRA=11"' if v["has_audio"] else ""
        out = f"projects/teste/output/shorts/{n:02d}_{x['id']}.mp4"
        rc, o = sh_drawtext(f'ffmpeg -v error -y -ss {start} -t {dur:.3f} -i {x["source"]} {silence} -vf "{vf}" {loud} '
                            f'-ar 48000 -ac 2 -c:v libx264 -preset ultrafast -crf 20 -c:a aac -b:a 192k '
                            f'-movflags +faststart {out}', root)
        tipo = ("vertical" if v["height"] > v["width"] else "horizontal") + \
               (", mudo" if not v["has_audio"] else "") + (", legenda" if subs else "")
        check(rc == 0, f"short {x['id']} ({tipo}) renderizado" + ("" if rc == 0 else f": {o.strip()[-300:]}"))
        if rc:
            continue
        info = json.loads(sh(f"ffprobe -v error -show_entries stream=codec_type,width,height "
                             f"-show_entries format=duration -of json {out}", root)[1])
        st_ = {s_["codec_type"]: s_ for s_ in info["streams"]}
        check(st_.get("video", {}).get("width") == 1080 and st_["video"].get("height") == 1920
              and "audio" in st_ and float(info["format"]["duration"]) <= 60.5,
              f"short {x['id']}: 1080x1920, com áudio, {float(info['format']['duration']):.1f}s ≤ 60 s")


def test_transcribe_script():
    print("== scripts/transcribe.py")
    import importlib.util
    spec = importlib.util.spec_from_file_location("transcribe", REPO / "scripts/transcribe.py")
    tr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tr)
    srt = tr.format_srt([{"start": 0.0, "end": 1.2, "text": " No way! "},
                         {"start": 1.5, "end": 1.5, "text": "tempo inválido"},
                         {"start": 2.0, "end": 3.0, "text": "   "},
                         {"start": 3661.25, "end": 3662.0, "text": "Did you see that?"}])
    check(srt == "1\n00:00:00,000 --> 00:00:01,200\nNo way!\n\n2\n01:01:01,250 --> 01:01:02,000\nDid you see that?\n",
          "format_srt: numera em sequência, descarta vazios/tempo inválido, formata horas e ms")
    engine = tr.available_engine("auto")
    if engine is None:
        rc = sp.run([sys.executable, str(REPO / "scripts/transcribe.py"), "x.wav", "--out-dir", "x"],
                    capture_output=True, text=True, encoding="utf-8")
        check(rc.returncode == 2 and "pip install" in rc.stderr,
              "sem motor de transcrição: sai com código 2 e explica como instalar")
    else:
        print(f"  (motor instalado: {engine}-whisper; transcrição real não é testada aqui)")


def test_permission_template():
    print("== Modelos de pedido de permissão")
    t = (REPO / ".claude/skills/gta-video-discovery/permission-template.md").read_text(encoding="utf-8")
    msgs = re.findall(r"```\n(.*?)\n```", t, re.S)
    check(len(msgs) >= 4, f"{len(msgs)} mensagens no modelo")
    link = "https://x.com/usuario_gta_rp/status/1858000000000000000"
    fill = {"<@autor>": "@usuario_gta_rp", "<@author>": "@usuario_gta_rp", "<link do post>": link,
            "<post link>": link, "<enlace>": link, "<nome do canal>": "Canal GTA Brasil",
            "<channel name>": "Canal GTA Brasil", "<nombre del canal>": "Canal GTA Brasil"}
    for i, m in enumerate(msgs, 1):
        for k, v in fill.items():
            m = m.replace(k, v)
        n = len(re.sub(r"https://\S+", "x" * 23, m))  # o X conta todo link como 23 caracteres
        check(n <= 280 and "<" not in m, f"mensagem {i}: {n} caracteres (limite 280), sem campo sem preencher")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # o console do Windows não é UTF-8 por padrão
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ffmpeg/ffprobe não encontrados no PATH")
    test_frontmatter()
    test_permission_template()
    test_transcribe_script()
    root = pathlib.Path(tempfile.mkdtemp(prefix="gta-e2e-"))
    try:
        run_pipeline(root)
    finally:
        if "--keep" in sys.argv:
            print(f"Arquivos mantidos em {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{'TODOS OS TESTES PASSARAM' if not failures else f'{len(failures)} FALHA(S)'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
