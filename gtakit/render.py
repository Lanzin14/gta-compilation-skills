"""Monta os comandos ffmpeg das skills video-editor, youtube-publisher e youtube-shorts.

Os filtros são os mesmos documentados nas skills; aqui eles viram listas de argumentos.
Caminhos são relativos à pasta do projeto (o ffmpeg roda com cwd = projects/<slug>/).
"""
AUDIO_NORM = "loudnorm=I=-14:TP=-1.5:LRA=11"
SILENCE_INPUT = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-shortest"]
SHORT_MAX_S = 60.0


def is_vertical(video):
    return (video.get("height") or 0) > (video.get("width") or 0)


def _credit(credit_file, position):
    # textfile= + expansion=none: o crédito é lido de um arquivo e desenhado literalmente,
    # então nomes com ' : % \\ { } ou emoji não quebram o filtro nem viram comandos do drawtext.
    return f"drawtext=textfile={credit_file}:expansion=none:{position}"


def compilation_filter(video, subtitle=None, credit_file=None):
    if is_vertical(video):
        vf = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=20:2[bg];"
              "[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,fps=30,")
    else:
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,"
    if subtitle:
        vf += f"subtitles={subtitle}:force_style='FontSize=22,Outline=2,MarginV=40',"
    if credit_file:
        vf += _credit(credit_file, "x=w-tw-30:y=30:fontsize=28:fontcolor=white:borderw=2")
    return vf.rstrip(",")


def short_filter(video, subtitle=None, credit_file=None):
    if is_vertical(video):
        vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,"
    else:
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
              "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,")
    if subtitle:
        vf += f"subtitles={subtitle}:force_style='FontSize=13,Bold=1,Outline=3,MarginV=70,Alignment=2',"
    if credit_file:
        vf += _credit(credit_file, "x=(w-tw)/2:y=160:fontsize=48:fontcolor=white:borderw=3")
    return vf.rstrip(",")


def encode_args(source, start, duration, has_audio, vf, out, preset="medium", faststart=False):
    args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source]
    if not has_audio:
        args += SILENCE_INPUT          # vídeo mudo: faixa de silêncio (evita buraco no áudio ao juntar)
    args += ["-vf", vf]
    if has_audio:
        args += ["-af", AUDIO_NORM]
    args += ["-ar", "48000", "-ac", "2", "-c:v", "libx264", "-preset", preset, "-crf", "20",
             "-c:a", "aac", "-b:a", "192k"]
    if faststart:
        args += ["-movflags", "+faststart"]
    return args + [out]


def concat_args(list_file, out):
    return ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy",
            "-movflags", "+faststart", out]


def thumbnail_args(video, t, textfile, out):
    vf = ("scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=saturation=1.3:contrast=1.1,"
          "drawbox=y=ih*0.55:w=iw:h=ih*0.45:color=black@0.45:t=fill,"
          f"drawtext=textfile={textfile}:fontsize=120:fontcolor=yellow:borderw=8:bordercolor=black:"
          "line_spacing=10:x=50:y=h-th-50")
    return ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", vf, "-q:v", "2", out]


def short_window(moment):
    """Até 60 s: o momento inteiro; mais longo: janela de 60 s começando 4 s antes do peak_time."""
    start, end = moment["start"], moment["end"]
    if end - start <= SHORT_MAX_S:
        return start, end - start
    pt = moment.get("peak_time")
    s = start if pt is None else max(start, pt - 4.0)
    s = min(s, end - SHORT_MAX_S)
    return s, SHORT_MAX_S
