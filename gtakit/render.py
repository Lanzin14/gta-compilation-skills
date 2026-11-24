"""Monta os comandos ffmpeg das skills video-editor, youtube-publisher e youtube-shorts.

Os filtros são os documentados nas skills; aqui eles viram listas de argumentos.
Caminhos são relativos à pasta do projeto (o ffmpeg roda com cwd = projects/<slug>/).
Todo vídeo sai com o mesmo formato (resolução, fps, SAR 1:1, yuv420p, AAC 48 kHz estéreo) para
poder ser juntado sem recodificar.
"""
from . import brand as brandmod

AUDIO_TARGET = "I=-14:TP=-1.5:LRA=11"
AUDIO_NORM = f"loudnorm={AUDIO_TARGET}"
SILENCE_INPUT = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-shortest"]
SHORT_MAX_S = 60.0
FINISH = "setsar=1,format=yuv420p"


def is_vertical(video):
    return (video.get("height") or 0) > (video.get("width") or 0)


def _credit(credit_file, position):
    # textfile= + expansion=none: o crédito é lido de um arquivo e desenhado literalmente,
    # então nomes com ' : % \\ { } não quebram o filtro nem viram comandos do drawtext.
    return f"drawtext=textfile={credit_file}:expansion=none:{position}"


def _fades(duration, fade):
    if not fade or not duration or duration <= 4 * fade:
        return ""
    return f"fade=t=in:st=0:d={fade},fade=t=out:st={duration - fade:.3f}:d={fade},"


def _assemble(vf, subtitle, sub_style, credit_file, credit_pos, brand, wm_file, logo_rel, short, duration, fade):
    if subtitle:
        vf += f"subtitles={subtitle}:force_style='{sub_style}',"
    if credit_file:
        vf += _credit(credit_file, credit_pos) + ","
    if brand:
        wm = brandmod.watermark(brand, wm_file, short=short) if wm_file else ""
        if wm:
            vf += wm + ","
    vf += _fades(duration, fade) + FINISH
    if brand and logo_rel:
        vf += brandmod.logo_overlay(brand, logo_rel, short=short)
    return vf


def compilation_filter(video, subtitle=None, credit_file=None, fps=30, brand=None, wm_file=None, logo_rel=None,
                       duration=None, fade=None):
    if is_vertical(video):
        vf = ("split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=20:2[bg];"
              f"[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,fps={fps},")
    else:
        vf = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={fps},"
    return _assemble(vf, subtitle, "FontSize=22,Outline=2,MarginV=40", credit_file,
                     "x=w-tw-30:y=30:fontsize=28:fontcolor=white:borderw=2", brand, wm_file, logo_rel, False, duration, fade)


def short_filter(video, subtitle=None, credit_file=None, fps=30, brand=None, wm_file=None, logo_rel=None,
                 duration=None, fade=None, base=None):
    if base:  # enquadramento escolhido pelo gtakit/framing.py (recorte, dividido, desfocado)
        vf = base
    elif is_vertical(video):
        vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps={fps},"
    else:
        vf = ("split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];"
              f"[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},")
    return _assemble(vf, subtitle, "FontSize=13,Bold=1,Outline=3,MarginV=70,Alignment=2", credit_file,
                     "x=(w-tw)/2:y=160:fontsize=48:fontcolor=white:borderw=3", brand, wm_file, logo_rel, True, duration, fade)


def audio_filter(measured=None, duration=None, fade=None):
    """loudnorm em 1 passada, ou em 2 (mais preciso) quando há a medição da 1ª passada."""
    if measured and measured.get("input_i") not in (None, "-inf", "inf"):
        af = (f"loudnorm={AUDIO_TARGET}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured['target_offset']}:linear=true")
    else:
        af = AUDIO_NORM
    if fade and duration and duration > 4 * fade:
        af += f",afade=t=in:st=0:d={fade},afade=t=out:st={duration - fade:.3f}:d={fade}"
    return af


def encode_args(source, start, duration, has_audio, vf, out, preset="medium", faststart=False, af=None):
    args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source]
    if not has_audio:
        args += SILENCE_INPUT          # vídeo mudo: faixa de silêncio (evita buraco no áudio ao juntar)
    args += ["-vf", vf]
    if has_audio:
        args += ["-af", af or AUDIO_NORM]
    args += ["-ar", "48000", "-ac", "2", "-c:v", "libx264", "-preset", preset, "-crf", "20",
             "-c:a", "aac", "-b:a", "192k"]
    if faststart:
        args += ["-movflags", "+faststart"]
    return args + [out]


def card_args(brand, kind, textfile, out, fps, size=(1920, 1080), preset="medium", logo_rel=None):
    """Abertura/tela final: fundo da marca + texto central (+ logo), no mesmo formato dos clipes."""
    secs = brand[kind]["seconds"]
    w, h = size
    fade = min(0.4, secs / 5)
    vf = (f"drawtext={brandmod.font_opt(brand)}textfile={textfile}:expansion=none:fontsize={int(h * 0.09)}:"
          f"fontcolor={brandmod.ff_color(brand['colors']['accent'])}:borderw=4:bordercolor=black:"
          f"line_spacing=20:x=(w-tw)/2:y=(h-th)/2,fade=t=in:st=0:d={fade},fade=t=out:st={secs - fade:.3f}:d={fade},{FINISH}")
    if logo_rel:
        vf += (f"[base];movie={logo_rel},scale=-1:{int(h * 0.18)},format=rgba[lg];"
               f"[base][lg]overlay=(W-w)/2:H*0.12")
    return ["ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={brandmod.ff_color(brand['colors']['background'])}:s={w}x{h}:r={fps}:d={secs}",
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", f"{secs}",
            "-vf", vf, "-ar", "48000", "-ac", "2", "-c:v", "libx264", "-preset", preset, "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-shortest", out]


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
