"""Teste ponta a ponta das skills com vídeos sintéticos.

Roda o fluxo inteiro pela linha de comando do gtakit (o mesmo código que as skills usam),
do discovery aos Shorts, e falha (código 1) se alguma verificação não passar.

Simulado (não há rede do X nem Whisper no teste): metadados do yt-dlp e transcrição.

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


# ---------------------------------------------------------------- pipeline (pela linha de comando do gtakit)
NOW = 1_800_000_000  # horário fixo: a nota de viralidade não depende do relógio da máquina


def gtakit(*args):
    """Roda `python -m gtakit ...` como as skills fazem; devolve (código, saída)."""
    r = sp.run([sys.executable, "-m", "gtakit", *map(str, args)], cwd=REPO, capture_output=True,
               text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def run_pipeline(root):
    P = root / "projects/teste"
    rc, o = gtakit("init", P, "--theme", "teste")
    check(rc == 0, "gtakit init" + ("" if rc == 0 else f": {o}"))
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

    # ---- 1. gta-video-discovery (metadados simulados no formato do yt-dlp --dump-json) ----
    print("== 1. gta-video-discovery")
    fake = {"v1": ("Ana", "ana_gta", 51000, 8200, 640, 48), "v2": ("Beto", "beto_rp", 900, None, 30, 5),
            "v3": ("Caio", "caio", 12000, 1500, None, 200), "v4": ("Dani", "dani", 3000, 200, 50, 20),
            "v5": ("Edu", "edu", 0, 0, 0, 3), "v6": ("Fê", "fe", 500, 20, 10, 10)}
    lines = [json.dumps({"id": vid, "extractor": "twitter", "webpage_url": f"https://x.com/{h}/status/9{i}",
                         "uploader": a, "uploader_id": h, "timestamp": NOW - hours * 3600, "duration": 10,
                         "like_count": l, "repost_count": r, "comment_count": c, "view_count": None,
                         "description": f"clipe {vid}"}, ensure_ascii=False)
             for i, (vid, (a, h, l, r, c, hours)) in enumerate(fake.items())]
    (P / "raw_meta.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, o = gtakit("discovery", P, "--now", NOW)
    check(rc == 0, "gtakit discovery" + ("" if rc == 0 else f": {o}"))
    rc, o = gtakit("approve", P, "--all")
    check(rc == 0, "gtakit approve --all")
    rc, o = gtakit("probe", P)
    check(rc == 0, "gtakit probe (vídeos baixados conferidos)" + ("" if rc == 0 else f": {o}"))
    vids = json.loads((P / "discovery.json").read_text(encoding="utf-8"))["videos"]
    by = {v["id"]: v for v in vids}
    check(by["v5"]["viral_score"] == 0, "engajamento zero → nota 0 (sem divisão por zero)")
    check(by["v1"]["viral_score"] == 100, "vídeo mais engajado → nota 100")
    check(not by["v3"]["has_audio"] and by["v1"]["has_audio"], "has_audio detecta vídeo mudo")
    check(by["v1"]["post_id"] == "90" and by["v1"]["author_handle"] == "@ana_gta", "post_id e @ extraídos do yt-dlp")

    # ---- 2. viral-moment-analyzer ----
    print("== 2. viral-moment-analyzer")
    rc, o = gtakit("analyze", P)
    check(rc == 0, "gtakit analyze" + ("" if rc == 0 else f": {o}"))
    moments = json.loads((P / "moments.json").read_text(encoding="utf-8"))["moments"]
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
    rc, o = gtakit("analyze", P)
    check(rc != 0 and "--force" in o, "analyze não apaga moments.json existente sem --force")

    # ---- 3. video-translator (Whisper e tradução simulados; o Claude faz isso de verdade) ----
    print("== 3. video-translator")
    rc, o = gtakit("audio", P)
    check(rc == 0 and (P / f"subs/{m['v1']['id']}.wav").exists(), "gtakit audio extrai o áudio de cada momento")
    whisper = {"v1": ("en", "1\n00:00:11,500 --> 00:00:14,000\nNo way! Did you see that?\n"),
               "v2": ("pt", "1\n00:00:07,000 --> 00:00:09,000\nOlha isso mano\n"), "v4": ("en", "")}
    for x in moments:
        lang, srt = whisper.get(x["video_id"], (None, ""))
        words = len(re.findall(r"[A-Za-zÀ-ú]+", re.sub(r"\d|-->|:|,", " ", srt)))
        x["needs_translation"] = bool(lang and lang != "pt" and words >= 3)
        if x["needs_translation"]:
            (P / f"subs/{x['id']}.pt.srt").write_text(
                srt.replace("No way! Did you see that?", "Não acredito! Viu isso?"), encoding="utf-8")
            x["subtitle_pt"] = f"subs/{x['id']}.pt.srt"
    (P / "moments.json").write_text(json.dumps({"moments": moments}, ensure_ascii=False, indent=1), encoding="utf-8")
    check([x["video_id"] for x in moments if x["needs_translation"]] == ["v1"],
          "só a fala em inglês com conteúdo recebe legenda")

    # ---- 4. video-editor ----
    print("== 4. video-editor")
    rc, o = gtakit("render", P, "--preset", "ultrafast")
    check(rc == 0, "gtakit render (clipes + concatenação + capítulos)" + ("" if rc == 0 else f": {o[-600:]}"))
    if rc:
        return
    tl = json.loads((P / "output/timeline.json").read_text(encoding="utf-8"))
    chap, clips = tl["chapters"], tl["clips"]
    info = json.loads(sh("ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,duration "
                         "-show_entries format=duration -of json output/compilation.mp4", P)[1])
    s = {x["codec_type"]: x for x in info["streams"]}
    fd, soma = float(info["format"]["duration"]), sum(c["clip_dur"] for c in clips)
    check(s.get("video", {}).get("codec_name") == "h264" and s["video"]["width"] == 1920
          and s["video"]["height"] == 1080, "vídeo final h264 1920x1080")
    check(s.get("audio", {}).get("codec_name") == "aac", "áudio final aac presente")
    check(abs(fd - soma) < 1, f"duração {fd:.2f}s ≈ soma dos clipes {soma:.2f}s")
    check(abs(float(s["video"]["duration"]) - float(s["audio"]["duration"])) < 0.2, "áudio e vídeo sincronizados")
    check(chap and chap[0]["start"] == 0 and len(chap) >= 3 and all(c["dur"] >= 10 for c in chap),
          f"capítulos válidos para o YouTube ({len(chap)}, todos ≥ 10 s, 1º em 00:00)")
    check([c["moment_id"] for c in clips][-1] == m["v1"]["id"], "compilado fecha com o melhor momento")
    check("clip_start" not in json.dumps(json.loads((P / "moments.json").read_text(encoding="utf-8"))),
          "render não escreve no moments.json (clip_start fica no timeline.json)")

    # ---- 5. youtube-publisher ----
    print("== 5. youtube-publisher")
    used = {x["video_id"] for x in moments if x["id"] in {c["moment_id"] for c in clips}}
    fmt = lambda sec: f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"
    desc = ["⏱️ Capítulos"] + [f"{fmt(c['start'])} Momento {' + '.join(c['moment_ids'])}" for c in chap]
    desc += ["", "🎮 Créditos"] + [f"{v['author']} ({v['author_handle']}) — {v['url']}" for v in vids if v["id"] in used]
    text = "\n".join(desc)
    check(text.splitlines()[1].startswith("00:00"), "descrição começa os capítulos em 00:00")
    check(all(by[k]["author_handle"] in text for k in used), "todos os autores usados estão nos créditos")
    rc, o = gtakit("thumbnail", P, "--line", "NÃO ACREDITO:", "--line", "CAPOTOU!")  # acento, ':' e '!'
    check(rc == 0, "thumbnail gerada" + ("" if rc == 0 else f": {o[-400:]}"))
    if rc == 0:
        best = next(c for c in clips if c["moment_id"] == m["v1"]["id"])
        t_best = float(re.search(r"quadro em ([\d.]+)s", o).group(1))
        check(best["clip_start"] <= t_best <= best["clip_start"] + best["clip_dur"], "quadro da thumbnail cai dentro do clipe certo")
        check(probe("output/thumbnail.jpg", "-show_entries stream=width,height", P) == "1280,720", "thumbnail em 1280x720")
        check((P / "output/thumbnail.jpg").stat().st_size < 2 * 1024 * 1024, "thumbnail com menos de 2 MB (limite do YouTube)")

    # ---- 6. youtube-shorts ----
    print("== 6. youtube-shorts")
    rc, o = gtakit("shorts", P, "--count", "6", "--preset", "ultrafast")
    check(rc == 0, "gtakit shorts" + ("" if rc == 0 else f": {o[-600:]}"))
    shorts = json.loads((P / "output/shorts/shorts.json").read_text(encoding="utf-8")) if rc == 0 else []
    made = {x["moment_id"] for x in shorts}
    check(m["v4"]["id"] not in made, "momento com menos de 8 s não vira Short")
    for vid, tipo in (("v1", "horizontal, legenda"), ("v2", "vertical"), ("v3", "horizontal, mudo")):
        f = next((x["file"] for x in shorts if x["moment_id"] == m[vid]["id"]), None)
        check(f is not None, f"short {m[vid]['id']} ({tipo}) renderizado")
        if f:
            info = json.loads(sh(f"ffprobe -v error -show_entries stream=codec_type,width,height "
                                 f"-show_entries format=duration -of json output/shorts/{f}", P)[1])
            st_ = {s_["codec_type"]: s_ for s_ in info["streams"]}
            check(st_.get("video", {}).get("width") == 1080 and st_["video"].get("height") == 1920
                  and "audio" in st_ and float(info["format"]["duration"]) <= 60.5,
                  f"short {m[vid]['id']}: 1080x1920, com áudio, {float(info['format']['duration']):.1f}s ≤ 60 s")
    check(all(x["description"].startswith("Clipe original:") for x in shorts), "todo Short tem crédito na descrição")

    # ---- contratos e estado ----
    print("== contratos entre etapas")
    rc, o = gtakit("validate", P)
    check(rc == 0, "gtakit validate: contratos ok" + ("" if rc == 0 else f": {o}"))
    rc, o = gtakit("status", P)
    check(rc == 0 and "render" in o and "done" in o, "gtakit status mostra as etapas concluídas")
    (P / "subs" / f"{m['v1']['id']}.pt.srt").unlink()
    rc, o = gtakit("validate", P)
    check(rc != 0 and "legenda" in o, "validate acusa legenda apagada")


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
