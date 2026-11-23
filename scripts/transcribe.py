"""Transcreve um áudio e detecta o idioma da fala.

Usa o faster-whisper (várias vezes mais rápido, sem PyTorch) se estiver instalado;
senão, usa o openai-whisper. Usado pela skill video-translator.

Uso:
    py -3 scripts/transcribe.py <audio.wav> --out-dir <pasta> [--model small] [--engine auto|faster|openai]

Gera, com o mesmo nome do áudio:
    <pasta>/<nome>.srt   legenda no idioma original (tempos relativos ao início do áudio)
    <pasta>/<nome>.json  {"engine", "model", "language", "language_probability", "text", "segments": [...]}

Códigos de saída: 0 = ok | 2 = nenhum motor de transcrição instalado | 1 = outro erro.
"""
import argparse
import importlib.util
import json
import pathlib
import sys


def fmt_time(seconds):
    """1.2 -> '00:00:01,200' (formato SRT)."""
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_srt(segments):
    """segments: lista de dicts com start, end, text. Ignora textos vazios e tempos inválidos."""
    blocks, n = [], 0
    for seg in segments:
        text = seg["text"].strip()
        if not text or seg["end"] <= seg["start"]:
            continue
        n += 1
        blocks.append(f"{n}\n{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n{text}\n")
    return "\n".join(blocks)


def available_engine(choice):
    has_faster = importlib.util.find_spec("faster_whisper") is not None
    has_openai = importlib.util.find_spec("whisper") is not None
    if choice == "faster":
        return "faster" if has_faster else None
    if choice == "openai":
        return "openai" if has_openai else None
    return "faster" if has_faster else ("openai" if has_openai else None)


def transcribe_faster(audio, model_name):
    import ctranslate2
    from faster_whisper import WhisperModel
    # Placa de vídeo NVIDIA (CUDA) -> float16; senão CPU com int8 (o tipo mais rápido na CPU).
    gpu = ctranslate2.get_cuda_device_count() > 0
    model = WhisperModel(model_name, device="cuda" if gpu else "cpu", compute_type="float16" if gpu else "int8")
    segments, info = model.transcribe(str(audio), task="transcribe", vad_filter=True)
    segs = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    return info.language, round(info.language_probability, 3), segs


def transcribe_openai(audio, model_name):
    import whisper
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio), task="transcribe")
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in result["segments"]]
    return result["language"], None, segs  # openai-whisper não informa a confiança no idioma


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("audio", type=pathlib.Path)
    ap.add_argument("--out-dir", type=pathlib.Path, required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--engine", choices=["auto", "faster", "openai"], default="auto")
    args = ap.parse_args(argv)

    engine = available_engine(args.engine)
    if engine is None:
        print("ERRO: nenhum motor de transcrição instalado. Instale com:\n"
              "  py -3 -m pip install --user faster-whisper   (recomendado)\n"
              "  py -3 -m pip install --user openai-whisper", file=sys.stderr)
        return 2
    if not args.audio.is_file():
        print(f"ERRO: áudio não encontrado: {args.audio}", file=sys.stderr)
        return 1

    run = transcribe_faster if engine == "faster" else transcribe_openai
    language, prob, segs = run(args.audio, args.model)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.audio.stem
    (args.out_dir / f"{stem}.srt").write_text(format_srt(segs), encoding="utf-8")
    data = {"engine": f"{engine}-whisper", "model": args.model, "language": language,
            "language_probability": prob, "text": " ".join(s["text"].strip() for s in segs).strip(),
            "segments": segs}
    (args.out_dir / f"{stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{engine}-whisper | idioma: {language} (confiança: {prob}) | {len(segs)} trechos -> "
          f"{args.out_dir / (stem + '.srt')}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
