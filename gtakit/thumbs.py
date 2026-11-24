"""Thumbnails múltiplas: candidatas de momentos diferentes, filtro de qualidade e folha de comparação.

Para cada um dos melhores momentos usados no compilado, testa o quadro do pico (peak_time) e
pequenas variações em volta, e fica com o mais nítido. Descarta quadros escuros, borrados, perto de um
corte/transição de cena (imagem dupla) ou quase iguais a outra candidata. Cada candidata sai em 2 estilos; o usuário escolhe pela folha numerada.
"""
OFFSETS = (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, 2.0)
DARK_YAVG = 40.0
BLURRY = 12.0
SCENE_CUT = 6.0    # mudança de cena (scdet) em ±0,5 s acima disso = transição: imagem dupla/borrada
SAME_HASH = 10


def candidate_times(moments, timeline, count):
    """[(moment_id, [tempos no compilado])] dos melhores momentos (nota) que estão no compilado."""
    pos = {e["moment_id"]: e for e in timeline["clips"]}
    used = sorted((m for m in moments if m["id"] in pos), key=lambda m: (-m["score"], m["id"]))
    out = []
    for m in used[:count * 2]:  # sobra para compensar descartes
        e = pos[m["id"]]
        peak = m.get("peak_time")
        base = e["clip_start"] + ((peak - m["start"]) if peak is not None else e["clip_dur"] / 2)
        lo, hi = e["clip_start"] + 0.3, e["clip_start"] + e["clip_dur"] - 0.3
        out.append((m["id"], [min(hi, max(lo, base + o)) for o in OFFSETS]))
    return out


def choose(cands, probe, count):
    """cands: [(moment_id, [t...])]; probe(t) -> (yavg, blur, hash, mudança de cena em ±0,5 s).
    Devolve (escolhidas, rejeitadas)."""
    chosen, rejected = [], []
    for mid, times in cands:
        if len(chosen) >= count:
            break
        best = None
        for t in times:
            y, blur, h, change = probe(t)
            if y < DARK_YAVG:
                rejected.append((mid, t, f"escuro (brilho {y:.0f})"))
                continue
            if change >= SCENE_CUT:
                rejected.append((mid, t, f"perto de corte/transição de cena (mudança {change:.1f})"))
                continue
            if blur > BLURRY:
                rejected.append((mid, t, f"borrado (índice {blur:.1f})"))
                continue
            if any(bin(h ^ c["hash"]).count("1") <= SAME_HASH for c in chosen):
                rejected.append((mid, t, "quase igual a outra candidata"))
                continue
            if best is None or blur < best["blur"]:
                best = {"moment_id": mid, "t": round(t, 2), "yavg": round(y, 1), "blur": round(blur, 2), "hash": h,
                        "scene_change": round(change, 2)}
        if best:
            chosen.append(best)
    return chosen, rejected


def layout_filter(style, textfile, accent="yellow", font_opt=""):
    base = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=saturation=1.3:contrast=1.1,"
    text = (f"drawtext={font_opt}textfile={textfile}:expansion=none:fontsize=120:fontcolor={accent}:borderw=8:"
            "bordercolor=black:line_spacing=10:")
    if style == "faixa":   # faixa escura embaixo, texto embaixo à esquerda (o estilo original)
        return base + "drawbox=y=ih*0.55:w=iw:h=ih*0.45:color=black@0.45:t=fill," + text + "x=50:y=h-th-50"
    if style == "topo":    # faixa escura em cima, texto em cima
        return base + "drawbox=y=0:w=iw:h=ih*0.42:color=black@0.45:t=fill," + text + "x=50:y=40"
    raise ValueError(f"estilo desconhecido: {style}")


def sheet_args(files, out):
    """Folha de comparação: miniaturas numeradas em grade de 2 colunas."""
    n = len(files)
    args = ["ffmpeg", "-v", "error", "-y"]
    for f in files:
        args += ["-i", f]
    parts, labels = [], []
    for i in range(n):
        # número no canto inferior direito: não cobre o texto em nenhum dos dois estilos
        parts.append(f"[{i}:v]scale=640:360,drawbox=x=iw-110:y=ih-100:w=100:h=90:color=black@0.6:t=fill,"
                     f"drawtext=text='{i + 1}':fontsize=72:fontcolor=white:borderw=4:bordercolor=black:"
                     f"x=w-60-tw/2:y=h-55-th/2[t{i}]")
        labels.append(f"[t{i}]")
    if n % 2:
        parts.append("color=c=black:s=640x360:d=1[pad]")
        labels.append("[pad]")
    cols = 2
    layout = "|".join(f"{(k % cols) * 640}_{(k // cols) * 360}" for k in range(len(labels)))
    graph = ";".join(parts) + ";" + "".join(labels) + f"xstack=inputs={len(labels)}:layout={layout}"
    return args + ["-filter_complex", graph, "-frames:v", "1", "-q:v", "3", out]
