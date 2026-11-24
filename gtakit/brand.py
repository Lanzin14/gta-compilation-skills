"""Identidade visual do canal: marca d'água, logo, abertura e tela final (config/brand.json).

A marca só fica ativa com `channel_handle` preenchido — o gtakit nunca inventa nome de canal.
Ajustes de qualidade (fps, volume em 2 passadas, transição) valem com ou sem marca.
"""
import json
import pathlib

REPO_BRAND = pathlib.Path(__file__).resolve().parent.parent / "config" / "brand.json"
POSITIONS = {
    "bottom-right": "x=w-tw-30:y=h-th-30",
    "bottom-left": "x=30:y=h-th-30",
    "top-left": "x=30:y=30",
}


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_brand(project_dir=None):
    brand = json.loads(REPO_BRAND.read_text(encoding="utf-8"))
    if project_dir:
        local = pathlib.Path(project_dir) / "brand.json"
        if local.exists():
            _merge(brand, json.loads(local.read_text(encoding="utf-8")))
    handle = (brand.get("channel_handle") or "").strip()
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    brand["channel_handle"] = handle or None
    brand["active"] = bool(handle)
    if brand["fps"] not in (30, 60):
        raise ValueError("fps da marca deve ser 30 ou 60")
    return brand


def ff_color(hex_color, alpha=None):
    c = "0x" + hex_color.lstrip("#")
    return f"{c}@{alpha}" if alpha is not None else c


def font_opt(brand):
    """Opção fontfile= do drawtext (':' do caminho do Windows escapado), ou ''."""
    f = brand.get("font_file")
    return f"fontfile='{f.replace(':', chr(92) + ':')}':" if f else ""


def card_text(brand, kind):
    return brand[kind]["text"].replace("{handle}", brand["channel_handle"] or "").replace(
        "{name}", brand.get("channel_name") or brand["channel_handle"] or "")


def watermark(brand, textfile, short=False):
    """drawtext da marca d'água (texto do canal), ou '' se a marca estiver desligada."""
    if not (brand["active"] and brand["watermark"]["enabled"]):
        return ""
    wm = brand["watermark"]
    color = ff_color(brand["colors"]["text"], wm["opacity"])
    if short:  # Shorts: centralizado logo abaixo do crédito, longe dos botões do app
        pos, size = "x=(w-tw)/2:y=230", max(24, wm["size"] - 4)
    else:
        pos, size = POSITIONS.get(wm["position"], POSITIONS["bottom-right"]), wm["size"]
    return (f"drawtext={font_opt(brand)}textfile={textfile}:expansion=none:fontsize={size}:fontcolor={color}:"
            f"borderw=2:bordercolor=black@0.5:{pos}")


def logo_overlay(brand, logo_rel, short=False):
    """Sufixo de filtro que sobrepõe o logo (movie=), ou ''. logo_rel é relativo à pasta do projeto."""
    if not (brand["active"] and logo_rel):
        return ""
    alpha = brand["watermark"]["opacity"]
    h = 90 if short else 70
    pos = "(W-w)/2:300" if short else "30:H-h-30" if brand["watermark"]["position"] == "bottom-right" else "W-w-30:H-h-30"
    return (f"[base];movie={logo_rel},scale=-1:{h},format=rgba,colorchannelmixer=aa={alpha}[lg];"
            f"[base][lg]overlay={pos}")
