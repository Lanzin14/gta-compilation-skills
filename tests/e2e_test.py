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
    # v7: repost do v1 (mesmo vídeo recodificado com outra qualidade, postado por outra pessoa)
    rc, o = sh(f"ffmpeg -v error -y -i {src}/v1.mp4 -c:v libx264 -preset ultrafast -crf 35 -c:a aac -b:a 96k {src}/v7.mp4", root)
    if rc:
        sys.exit(f"Falha ao gerar v7: {o}")

    # ---- 1. gta-video-discovery (metadados simulados no formato do yt-dlp --dump-json) ----
    print("== 1. gta-video-discovery")
    fake = {"v1": ("Ana", "ana_gta", 51000, 8200, 640, 48), "v2": ("Beto", "beto_rp", 900, None, 30, 5),
            "v3": ("Caio", "caio", 12000, 1500, None, 200), "v4": ("Dani", "dani", 3000, 200, 50, 20),
            "v5": ("Edu", "edu", 0, 0, 0, 3), "v6": ("Fê", "fe", 500, 20, 10, 10),
            "v7": ("Repost", "repostador", 300, 5, 2, 30)}
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
    # crédito difícil de propósito: apóstrofo, dois-pontos, %, chaves e emoji (drawtext costuma quebrar com eles)
    tricky = "d'Ana: 100% {x} 😂"
    rc, o = gtakit("credit", P, "v2", "--creator", tricky)
    check(rc == 0 and "clipe @beto_rp" in o, "gtakit credit define o criador original (crédito duplo)")

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
    check(not m["v5"]["selected"] and "nota final" in m["v5"]["ranking"]["selection_reason"]
          and all(m[k]["selected"] for k in ("v1", "v2", "v3", "v4", "v6")),
          "só fica fora o vídeo de nota final baixa (sem viralidade, reação ou contexto) — não por falta de pico")
    check(m["v7"]["ranking"]["duplicate_of"] == "v1" and not m["v7"]["selected"],
          "repost recodificado do v1 detectado como duplicado (fica o mais viral)")
    check(all(set(x["ranking"]["criteria"]) == {"viralidade", "humor", "reacao", "contexto", "qualidade", "retencao"}
              and x["ranking"]["justification"] for x in moments), "todo momento tem as 6 notas e justificativa")
    rk = (P / "ranking.md").read_text(encoding="utf-8")
    check("| 1 |" in rk and "URL original:" in rk, "ranking.md gerado com tabela e detalhes")
    # avaliação do Claude (com motivo) muda só o critério avaliado, sem medir de novo
    (P / "judgments.json").write_text(json.dumps({"v4": {"humor": {"score": 95, "reason": "fail absurdo da física"}}}), encoding="utf-8")
    rc, o = gtakit("rank", P)
    m4 = next(x for x in json.loads((P / "moments.json").read_text(encoding="utf-8"))["moments"] if x["video_id"] == "v4")
    check(rc == 0 and m4["ranking"]["criteria"]["humor"] == 95 and m4["ranking"]["humor_source"] == "avaliação do Claude",
          "gtakit rank aplica a avaliação do Claude (judgments.json) com motivo")
    moments = json.loads((P / "moments.json").read_text(encoding="utf-8"))["moments"]
    m = {x["video_id"]: x for x in moments}
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
    best_id = max((x for x in moments if x["selected"]), key=lambda x: (x["score"], by[x["video_id"]]["viral_score"]))["id"]
    vid_of = {x["id"]: x["video_id"] for x in moments}
    seq = [by[vid_of[c["moment_id"]]]["author_handle"] for c in clips]
    check(all(x != y for x, y in zip(seq, seq[1:])) and tl.get("order_notes"),
          "ordem otimizada: nenhum criador em sequência e explicação no timeline.json")
    check([c["moment_id"] for c in clips][-1] == best_id, "compilado fecha com o melhor momento (maior nota final)")
    check("clip_start" not in json.dumps(json.loads((P / "moments.json").read_text(encoding="utf-8"))),
          "render não escreve no moments.json (clip_start fica no timeline.json)")
    check((P / "credits/v2.txt").read_text(encoding="utf-8") == "d'Ana: 100% {x} | clipe @beto_rp",
          "crédito com ' : % { } renderizado via arquivo, sem quebrar o ffmpeg (emoji removido do vídeo)")

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
        best = next(c for c in clips if c["moment_id"] == best_id)
        t_best = float(re.search(r"quadro em ([\d.]+)s", o).group(1))
        check(best["clip_start"] <= t_best <= best["clip_start"] + best["clip_dur"], "quadro da thumbnail cai dentro do clipe certo")
        check(probe("output/thumbnail.jpg", "-show_entries stream=width,height", P) == "1280,720", "thumbnail em 1280x720")
        check((P / "output/thumbnail.jpg").stat().st_size < 2 * 1024 * 1024, "thumbnail com menos de 2 MB (limite do YouTube)")
    rc, o = gtakit("thumbnails", P, "--line", "QUE ISSO", "--line", "MANO!", "--count", "3")
    cands = json.loads((P / "output/thumbs/candidatas.json").read_text(encoding="utf-8")) if rc == 0 else []
    check(rc == 0 and len({c["moment_id"] for c in cands}) >= 2 and {c["style"] for c in cands} == {"faixa", "topo"},
          f"thumbnails: {len(cands)} candidatas de {len({c['moment_id'] for c in cands})} momentos, 2 estilos"
          + ("" if rc == 0 else f": {o[-400:]}"))
    check(all(probe(c["file"], "-show_entries stream=width,height", P) == "1280,720" and c["kb"] < 2048 for c in cands),
          "todas as candidatas em 1280x720 e < 2 MB")
    check((P / "output/thumbs/escolha.jpg").exists(), "folha de comparação numerada gerada")
    rc, o = gtakit("thumbnail-pick", P, "2")
    check(rc == 0 and (P / "output/thumbnail.jpg").read_bytes() == (P / cands[1]["file"]).read_bytes(),
          "thumbnail-pick copia a candidata escolhida")

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

    # ---- direitos: créditos não substituem autorização ----
    print("== direitos e permissões")
    L = root / "data/permissions.json"
    rc, o = gtakit("permissions", P, "--channel", "Canal Teste", "--ledger", L)
    pm = (P / "permissions.md").read_text(encoding="utf-8") if rc == 0 else ""
    check(rc == 0 and f"## {tricky}" in pm and "## @ana_gta" in pm and "<nome do canal>" not in pm,
          "permissions.md com um pedido por dono do conteúdo (criador original, não o clipador)")
    check(all(int(n) <= 280 for n in re.findall(r"\((\d+)/280\)", pm)), "mensagens geradas cabem em 280 caracteres")
    rc, o = gtakit("ready", P, "--ledger", L)
    check(rc == 3 and "BLOQUEADO" in o, "ready bloqueia a publicação sem permissões")
    rc, o = gtakit("rights-set", "@beto_rp", "--status", "granted", "--ledger", L)
    check(rc != 0 and "prova" in o, "permissão concedida exige prova (--evidence)")
    owners = ["@ana_gta", tricky, "@caio", "@dani", "@fe"]
    for who in owners:
        gtakit("rights-set", who, "--status", "granted", "--evidence", f"https://x.com/print/{len(who)}", "--ledger", L)
    rc, o = gtakit("ready", P, "--ledger", L)
    pc = json.loads((P / "output/publish_check.json").read_text(encoding="utf-8"))
    check(rc == 0 and pc["publish_ready"] and pc["override"] is None, "com todas as permissões registradas, ready libera")
    L2 = root / "data/vazio.json"
    rc, o = gtakit("ready", P, "--ledger", L2, "--accept-risk", "decisão do usuário: uso transformativo")
    pc = json.loads((P / "output/publish_check.json").read_text(encoding="utf-8"))
    check(rc == 0 and pc["override"]["reason"].startswith("decisão do usuário") and pc["pending"],
          "sem permissões, só libera com aceite explícito do risco (motivo registrado, pendências mantidas)")
    gtakit("rights-set", "@fe", "--status", "denied", "--ledger", L)
    rc, o = gtakit("rights-sync", P, "--ledger", L)
    v6 = next(v for v in json.loads((P / "discovery.json").read_text(encoding="utf-8"))["videos"] if v["id"] == "v6")
    check(rc == 0 and v6["rights"] == "denied" and not v6["approved"], "permissão negada tira o vídeo do compilado")

    # ---- contratos e estado ----
    print("== contratos entre etapas")
    rc, o = gtakit("validate", P)
    check(rc == 0, "gtakit validate: contratos ok" + ("" if rc == 0 else f": {o}"))
    rc, o = gtakit("status", P)
    check(rc == 0 and "render" in o and "done" in o, "gtakit status mostra as etapas concluídas")
    (P / "subs" / f"{m['v1']['id']}.pt.srt").unlink()
    rc, o = gtakit("validate", P)
    check(rc != 0 and "legenda" in o, "validate acusa legenda apagada")

    # ---- identidade visual (marca do canal) ----
    print("== identidade visual")
    for x in moments:  # a legenda foi apagada acima; o render com marca segue sem ela
        x.pop("subtitle_pt", None)
    (P / "moments.json").write_text(json.dumps({"moments": moments}, ensure_ascii=False, indent=1), encoding="utf-8")
    sh('ffmpeg -v error -y -f lavfi -i "color=c=0xF2B72C:s=200x200,drawbox=x=50:y=50:w=100:h=100:color=black:t=fill" '
       '-frames:v 1 logo.png', root)
    (P / "brand.json").write_text(json.dumps({"channel_handle": "CanalTeste", "logo": str(root / "logo.png"), "fps": 60,
                                              "transition": {"type": "fade", "seconds": 0.25}}), encoding="utf-8")
    rc, o = gtakit("render", P, "--preset", "ultrafast")
    check(rc == 0, "render com marca (abertura, marca d'água, logo, tela final, 60 fps)" + ("" if rc == 0 else f": {o[-600:]}"))
    if rc == 0:
        tl = json.loads((P / "output/timeline.json").read_text(encoding="utf-8"))
        ids = [c["moment_id"] for c in tl["clips"]]
        info = json.loads(sh("ffprobe -v error -show_entries stream=codec_type,r_frame_rate:format=duration -of json "
                             "output/compilation.mp4", P)[1])
        vs = next(s_ for s_ in info["streams"] if s_["codec_type"] == "video")
        total = sum(c["clip_dur"] for c in tl["clips"])
        check(ids[0] == "intro" and ids[-1] == "outro", "abertura no início e tela final no fim")
        check(vs["r_frame_rate"] == "60/1" and abs(float(info["format"]["duration"]) - total) < 1,
              f"vídeo final em 60 fps com duração = soma das partes ({total:.1f}s)")
        check((P / "brand/watermark.txt").read_text(encoding="utf-8") == "@CanalTeste", "marca d'água com o @ do canal (@ adicionado)")
        y_intro = float(re.findall(r"YAVG=([\d.]+)", sh('ffmpeg -ss 1.2 -i output/compilation.mp4 -frames:v 1 '
                                                       '-vf "crop=200:200:0:0,signalstats,metadata=print" -f null -', P)[1])[0])
        check(y_intro < 40, f"o 1º segundo é a abertura (fundo escuro da marca, brilho {y_intro:.0f})")
        ch = tl["chapters"]
        check(ch[0]["start"] == 0 and all(c["dur"] >= 10 for c in ch), "capítulos continuam válidos com abertura/tela final")
        louds = []
        for c in tl["clips"]:
            mid = c["moment_id"]
            if mid in ("intro", "outro") or not by[vid_of[mid]]["has_audio"]:
                continue
            out = sh(f"ffmpeg -hide_banner -nostats -i {c['clip']} -vn -af ebur128 -f null -", P)[1]
            louds.append(float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1]))
        check(louds and all(abs(x + 14) <= 1.5 for x in louds),
              f"volume normalizado em 2 passadas: clipes em -14 LUFS ±1,5 ({', '.join(f'{x:.1f}' for x in louds)})")
    rc, o = gtakit("shorts", P, "--count", "2", "--preset", "ultrafast")
    sfile = json.loads((P / "output/shorts/shorts.json").read_text(encoding="utf-8"))[0]["file"] if rc == 0 else None
    if sfile:
        fr = probe(f"output/shorts/{sfile}", "-select_streams v:0 -show_entries stream=r_frame_rate", P)
        check(fr == "60/1", "Shorts com marca também em 60 fps")
    else:
        check(False, "shorts com marca" + f": {o[-400:]}")


def framing_pipeline(root):
    """Projeto separado: o corte vertical segue a ação, e o estilo dividido mostra a câmera embaixo."""
    print("== enquadramento dos Shorts")
    P = root / "projects/enquadramento"
    gtakit("init", P)
    src = P / "source"
    # quadrado branco andando da esquerda para a direita (a 'ação')
    # (overlay recalcula a posição a cada quadro; o drawbox calcula uma vez só e o quadrado ficaria parado)
    sh('ffmpeg -v error -y -f lavfi -i "color=c=black:s=1280x720:r=30:d=12" -f lavfi -i "color=c=white:s=160x160:r=30:d=12" '
       '-f lavfi -i "sine=f=500:d=12:sample_rate=48000" '
       "-filter_complex \"[0][1]overlay=x='60+85*t':y=280\" -c:v libx264 -preset ultrafast -c:a aac -shortest "
       f'{src}/acao.mp4', root)
    moving = sp.run(["ffmpeg", "-v", "error", "-i", f"{src}/acao.mp4", "-vf", "fps=1,scale=32:1,format=gray",
                     "-f", "rawvideo", "-"], capture_output=True).stdout
    check(moving[:32] != moving[-32:], "vídeo de teste: o quadrado realmente se move")
    # 'gameplay' + câmera do streamer: bloco claro no canto inferior direito
    sh('ffmpeg -v error -y -f lavfi -i "testsrc2=s=1280x720:r=30:d=12,'
       'drawbox=x=960:y=500:w=320:h=220:color=white:t=fill" '
       '-f lavfi -i "sine=f=300:d=12:sample_rate=48000" -c:v libx264 -preset ultrafast -c:a aac -shortest '
       f'{src}/cam.mp4', root)
    lines = [json.dumps({"id": vid, "extractor": "twitter", "webpage_url": f"https://x.com/{vid}/status/1{i}",
                         "uploader": vid, "uploader_id": vid, "timestamp": NOW - 3600, "duration": 12,
                         "like_count": 1000, "repost_count": 100, "comment_count": 10, "description": "kkkk"})
             for i, vid in enumerate(("acao", "cam"))]
    (P / "raw_meta.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for cmd in (("discovery", P, "--now", NOW), ("approve", P, "--all"), ("probe", P), ("analyze", P),
                ("facecam", P, "cam", "--box", "0.75,0.694,0.25,0.306")):
        rc, o = gtakit(*cmd)
        if rc:
            check(False, f"preparar enquadramento ({cmd[0]}): {o[-300:]}")
            return
    rc, o = gtakit("shorts", P, "--count", "2", "--preset", "ultrafast")
    check(rc == 0, "gtakit shorts com enquadramento automático" + ("" if rc == 0 else f": {o[-500:]}"))
    if rc:
        return
    items = json.loads((P / "output/shorts/shorts.json").read_text(encoding="utf-8"))
    mom = {x["id"]: x["video_id"] for x in json.loads((P / "moments.json").read_text(encoding="utf-8"))["moments"]}
    by_vid = {mom[x["moment_id"]]: x for x in items}
    check(by_vid.get("acao", {}).get("layout") == "crop" and by_vid.get("cam", {}).get("layout") == "split",
          f"auto escolhe recorte para ação concentrada e dividido com câmera marcada "
          f"({ {k: v.get('layout') for k, v in by_vid.items()} })")

    def centroid_x(file, t):
        r = sp.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", file, "-frames:v", "1", "-vf",
                    "scale=54:96,format=gray", "-f", "rawvideo", "-"], capture_output=True, cwd=P)
        px = r.stdout
        tot = sum(px)
        return sum((i % 54 + 0.5) / 54 * v for i, v in enumerate(px)) / tot if tot else None

    f = f"output/shorts/{by_vid['acao']['file']}"
    xs = [centroid_x(f, t) for t in (2, 5, 8)]
    check(all(x is not None and 0.3 <= x <= 0.7 for x in xs),
          f"recorte segue a ação: o quadrado fica perto do centro do Short ({', '.join(f'{x:.2f}' for x in xs)})")
    r = sp.run(["ffmpeg", "-v", "error", "-ss", "3", "-i", f"output/shorts/{by_vid['cam']['file']}", "-frames:v", "1",
                "-vf", "scale=27:48,format=gray", "-f", "rawvideo", "-"], capture_output=True, cwd=P)
    top, bottom = r.stdout[:27 * 24], r.stdout[27 * 24:]
    check(sum(bottom) / len(bottom) > 200 and sum(top) / len(top) < 200,
          "dividido: câmera do streamer (bloco claro) ocupa a metade de baixo")


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
        framing_pipeline(root)
    finally:
        if "--keep" in sys.argv:
            print(f"Arquivos mantidos em {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    print(f"\n{'TODOS OS TESTES PASSARAM' if not failures else f'{len(failures)} FALHA(S)'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
