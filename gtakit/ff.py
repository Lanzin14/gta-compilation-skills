"""Chamadas ao ffmpeg/ffprobe e medições de áudio/vídeo.

Os comandos são executados como LISTA de argumentos (sem shell): assim não há diferença de aspas
entre Windows (cmd/PowerShell) e Linux. Medições são lidas da saída do ffmpeg (sem arquivos
temporários), o que evita escapar caminhos do Windows dentro de filtros.
"""
import json
import os
import re
import shutil
import subprocess

# Fonte de reserva para o drawtext, usada só se o ffmpeg não achar uma sozinho (comum no Windows).
FONT_CANDIDATES = {
    "nt": "C\\:/Windows/Fonts/arial.ttf",
    "posix": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}
_fontfile = None


class FFmpegError(RuntimeError):
    pass


def run(args, cwd=None):
    """Executa um comando e devolve (código de saída, stdout+stderr) em UTF-8."""
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    return r.returncode, r.stdout + r.stderr


def require_tools():
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        raise FFmpegError(f"não encontrado no PATH: {', '.join(missing)}")


def _with_font(args, font):
    return [a.replace("drawtext=", f"drawtext=fontfile='{font}':") if isinstance(a, str) else a for a in args]


def run_drawtext(args, cwd=None):
    """Como run(), mas se o ffmpeg reclamar de fonte aplica o fontfile de reserva e tenta de novo
    (mesma correção descrita na skill video-editor)."""
    global _fontfile
    a = _with_font(args, _fontfile) if _fontfile else args
    rc, out = run(a, cwd)
    if rc and _fontfile is None and "font" in out.lower():
        _fontfile = FONT_CANDIDATES.get(os.name)
        rc, out = run(_with_font(args, _fontfile), cwd)
    return rc, out


def media_info(path, cwd=None):
    """Duração, largura, altura, fps e se tem áudio."""
    rc, out = run(["ffprobe", "-v", "error", "-show_entries",
                   "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", path], cwd)
    if rc:
        raise FFmpegError(f"ffprobe falhou em {path}: {out.strip()[-300:]}")
    data = json.loads(out[out.find("{"):])
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    num, _, den = (video.get("r_frame_rate") or "0/1").partition("/")
    fps = round(float(num) / float(den or 1), 3) if float(den or 1) else 0.0
    return {
        "duration_s": round(float(data.get("format", {}).get("duration", 0.0)), 3),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def rms_windows(path, cwd=None):
    """Volume (dB RMS) em janelas de 0,5 s: lista de (início_s, dB). -inf vira float('-inf')."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af",
                   "aresample=48000,asetnsamples=n=24000:p=0,astats=metadata=1:reset=1,"
                   "ametadata=print:key=lavfi.astats.Overall.RMS_level", "-f", "null", "-"], cwd)
    if rc:
        raise FFmpegError(f"medição de volume falhou em {path}: {out.strip()[-300:]}")
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", out)]
    vals = [float(x) for x in re.findall(r"RMS_level=(\S+)", out)]
    return list(zip(times, vals))


def scene_changes(path, threshold=0.4, cwd=None):
    """Instantes (s) de mudança brusca de cena."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
                   f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"], cwd)
    if rc:
        raise FFmpegError(f"detecção de cenas falhou em {path}: {out.strip()[-300:]}")
    return [float(x) for x in re.findall(r"Parsed_showinfo.*?pts_time:([\d.]+)", out)]


def dead_time(path, cwd=None):
    """Trechos de silêncio (-40 dB, ≥1 s) e de imagem parada (≥1 s)."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                   "-af", "silencedetect=noise=-40dB:d=1", "-vf", "freezedetect=n=0.003:d=1",
                   "-f", "null", "-"], cwd)
    if rc:
        raise FFmpegError(f"detecção de tempo morto falhou em {path}: {out.strip()[-300:]}")
    f = lambda pat: [float(x) for x in re.findall(pat, out)]
    return {"silence_start": f(r"silence_start: ([\d.]+)"), "silence_end": f(r"silence_end: ([\d.]+)"),
            "freeze_start": f(r"freeze_start: ([\d.]+)"), "freeze_end": f(r"freeze_end: ([\d.]+)")}
