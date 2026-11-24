"""Enquadramento inteligente dos Shorts (9:16) a partir de vídeos horizontais.

- recorte: corte vertical em tela cheia que segue a ação. O movimento é medido em quadros
  minúsculos (32×18, 4 por segundo); o centro do corte segue o centro do movimento, suavizado e
  com velocidade máxima de panorâmica (sem tremer).
- dividido: jogo em cima e câmera do streamer embaixo (região marcada em `facecam` no discovery).
- desfocado: o vídeo inteiro no meio, com fundo desfocado (quando a ação está espalhada).
"""
FPS = 4
COLS, ROWS = 32, 18
WINDOW = 1080 / (1920 * 16 / 9)   # largura do corte 9:16 em fração da largura de um vídeo 16:9 (~0,32)
MAX_PAN_PER_S = 0.15              # o corte anda no máximo 15% da largura por segundo
MIN_CONCENTRATION = 0.45          # fração do movimento que precisa caber no corte para usar "recorte"


def column_motion(frames, cols=COLS, rows=ROWS):
    """Energia de movimento por coluna entre quadros consecutivos: [(t, [col...])]."""
    out = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        col = [0] * cols
        for r in range(rows):
            base = r * cols
            for c in range(cols):
                col[c] += abs(a[base + c] - b[base + c])
        out.append((i / FPS, col))
    return out


def _center(col):
    total = sum(col)
    if total == 0:
        return None, 0.0
    c = sum((i + 0.5) / len(col) * v for i, v in enumerate(col)) / total
    lo, hi = c - WINDOW / 2, c + WINDOW / 2
    inside = sum(v for i, v in enumerate(col) if lo <= (i + 0.5) / len(col) <= hi)
    return c, inside / total


def track(profile, smooth_s=1.0):
    """Centro do corte ao longo do tempo: [(t, centro 0–1)], suavizado e com limite de velocidade.
    Devolve também a concentração média do movimento (quanto do movimento cabe no corte)."""
    raw, concs, weights = [], [], []
    last = 0.5
    for t, col in profile:
        c, conc = _center(col)
        if c is None:
            c, conc = last, 0.0
        raw.append((t, c))
        concs.append(conc)
        weights.append(sum(col))
        last = c
    if not raw:
        return [(0.0, 0.5)], 0.0
    k = max(1, int(smooth_s * FPS))
    smooth = []
    for i, (t, _) in enumerate(raw):
        win = raw[max(0, i - k):i + k + 1]
        smooth.append((t, sum(c for _, c in win) / len(win)))
    limited, step = [smooth[0]], MAX_PAN_PER_S / FPS
    for t, c in smooth[1:]:
        prev = limited[-1][1]
        limited.append((t, prev + max(-step, min(step, c - prev))))
    total_w = sum(weights)
    conc = sum(c * w for c, w in zip(concs, weights)) / total_w if total_w else 0.0
    return limited, conc


def keyframes(path_track, every_s=1.0):
    """Reduz o trajeto a pontos a cada `every_s` segundos (expressão curta para o ffmpeg)."""
    if not path_track:
        return [(0.0, 0.5)]
    out, next_t = [], path_track[0][0]
    for t, c in path_track:
        if t >= next_t:
            out.append((round(t, 2), round(min(1.0, max(0.0, c)), 4)))
            next_t = t + every_s
    if out[-1][0] != round(path_track[-1][0], 2):
        out.append((round(path_track[-1][0], 2), round(min(1.0, max(0.0, path_track[-1][1])), 4)))
    return [(0.0, out[0][1])] + out if out[0][0] > 0 else out


def center_expr(keys):
    """Expressão ffmpeg do centro (fração 0–1) em função de t: interpolação linear entre pontos."""
    expr = f"{keys[-1][1]}"
    for (t0, c0), (t1, c1) in reversed(list(zip(keys, keys[1:]))):
        lerp = f"{c0}+({c1}-{c0})*(t-{t0})/{max(0.01, t1 - t0)}"
        expr = f"if(lt(t,{t1}),{lerp},{expr})"
    return expr


def crop_x(keys, out_w):
    """Expressão do x do crop: centro × largura − metade do corte, sem sair da imagem."""
    return f"clip(({center_expr(keys)})*iw-{out_w // 2},0,iw-{out_w})"


def choose_layout(video, concentration, requested="auto"):
    """(estilo, motivo). Vertical: sempre 'vertical'."""
    if (video.get("height") or 0) > (video.get("width") or 0):
        return "vertical", "vídeo já é vertical"
    face = video.get("facecam")
    if requested == "split" and not face:
        raise ValueError(f"vídeo {video['id']}: estilo 'dividido' precisa da câmera marcada (gtakit facecam)")
    if requested != "auto":
        return requested, "escolhido pelo usuário"
    if face:
        return "split", "câmera do streamer marcada: jogo em cima, câmera embaixo"
    if concentration >= MIN_CONCENTRATION:
        return "crop", f"{concentration:.0%} do movimento cabe no corte vertical: segue a ação em tela cheia"
    return "blur", f"ação espalhada (só {concentration:.0%} cabe num corte vertical): vídeo inteiro com fundo desfocado"


def base_filter(layout, video, keys, fps):
    """Início do -vf de cada estilo (o resto — legenda, crédito, marca — é igual para todos)."""
    if layout == "vertical":
        return f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps={fps},"
    if layout == "blur":
        return ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
                f"[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},")
    if layout == "crop":
        return f"scale=-2:1920,crop=1080:1920:x='{crop_x(keys, 1080)}':y=0,fps={fps},"
    if layout == "split":
        f = video["facecam"]
        return ("split[g][c];"
                f"[g]scale=-2:960,crop=1080:960:x='{crop_x(keys, 1080)}':y=0[top];"
                f"[c]crop=iw*{f['w']}:ih*{f['h']}:iw*{f['x']}:ih*{f['y']},"
                "scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bot];"
                f"[top][bot]vstack,fps={fps},")
    raise ValueError(f"estilo desconhecido: {layout}")
