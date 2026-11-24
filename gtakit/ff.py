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


def visual_stats(path, cwd=None):
    """A cada 0,5 s: (t, movimento 0–100 [scdet], brilho médio 0–255 [YAVG], borrão [blurdetect, maior = mais borrado])."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an", "-vf",
                   "fps=2,scdet=threshold=100,signalstats,blurdetect,metadata=print", "-f", "null", "-"], cwd)
    if rc:
        raise FFmpegError(f"medição visual falhou em {path}: {out.strip()[-300:]}")
    sc = [float(x) for x in re.findall(r"lavfi\.scd\.score=([\d.]+)", out)]
    ya = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", out)]
    bl = [float(x) for x in re.findall(r"lavfi\.blur=([\d.]+)", out)]
    n = min(len(sc), len(ya), len(bl))
    return [(round(i * 0.5, 2), sc[i], ya[i], bl[i]) for i in range(n)]


def loudness(path, cwd=None):
    """Volume integrado (LUFS) e pico real (dBFS) do vídeo inteiro; None se não houver áudio."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true",
                   "-f", "null", "-"], cwd)
    if rc:
        return None
    i = re.findall(r"^\s+I:\s+(-?[\d.]+|-inf) LUFS", out, re.M)
    pk = re.findall(r"^\s+Peak:\s+(-?[\d.]+|-inf) dBFS", out, re.M)
    if not i:
        return None
    to_f = lambda s: float("-inf") if s == "-inf" else float(s)
    return {"lufs": to_f(i[-1]), "true_peak_dbfs": to_f(pk[-1]) if pk else None}


def frame_hashes(path, fps=2, cwd=None):
    """'Impressão digital' (dHash de 64 bits) de cada quadro, a `fps` quadros/s — para achar repetição e duplicados."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf",
                        f"fps={fps},scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, cwd=cwd)
    if r.returncode:
        raise FFmpegError(f"hash de quadros falhou em {path}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    data, hashes = r.stdout, []
    for off in range(0, len(data) - 71, 72):
        px = data[off:off + 72]
        bits = 0
        for row in range(8):
            for col in range(8):
                bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
        hashes.append(bits)
    return hashes


def loudnorm_measure(path, start, duration, cwd=None):
    """1ª passada do loudnorm: mede o volume do trecho (para a 2ª passada ser precisa). None se falhar."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", path,
                   "-vn", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], cwd)
    if rc:
        return None
    block = out[out.rfind("{"):out.rfind("}") + 1]
    try:
        return json.loads(block)
    except ValueError:
        return None


def frame_probe(video, t, cwd=None):
    """Um quadro em t: (brilho médio 0–255, índice de borrão, dHash de 64 bits)."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-hide_banner", "-nostats", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-an", "-vf",
                        "signalstats,blurdetect,metadata=print,scale=9:8:flags=area,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, cwd=cwd)
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode or len(r.stdout) < 72:
        raise FFmpegError(f"quadro em {t:.2f}s de {video}: {err.strip()[-300:]}")
    y = re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", err)
    b = re.findall(r"lavfi\.blur=([\d.]+)", err)
    px = r.stdout[:72]
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return float(y[0]) if y else 0.0, float(b[0]) if b else 0.0, bits


def scene_change_near(video, t, window=0.5, cwd=None):
    """Maior mudança de cena (scdet, 0–100) entre t−window e t+window. Alto = corte/transição por perto."""
    rc, out = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{max(0.0, t - window):.2f}", "-t", f"{2 * window:.2f}",
                   "-i", video, "-an", "-vf", "scdet=threshold=100,metadata=print", "-f", "null", "-"], cwd)
    if rc:
        raise FFmpegError(f"mudança de cena em {t:.2f}s de {video}: {out.strip()[-300:]}")
    vals = [float(x) for x in re.findall(r"lavfi\.scd\.score=([\d.]+)", out)]
    return max(vals) if vals else 0.0
