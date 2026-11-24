"""Pasta de um compilado (projects/<slug>/): leitura/escrita de JSON, estado das etapas e validação."""
import datetime
import json
import pathlib

STAGES = ("discovery", "analyze", "translate", "render", "publish", "shorts")

# Campos obrigatórios de cada contrato entre etapas: (campo, tipo(s) aceitos)
SCHEMAS = {
    "discovery.videos": [("id", str), ("url", str), ("author_handle", str), ("viral_score", int),
                         ("approved", bool), ("rights", str)],
    "discovery.downloaded": [("local_path", str), ("duration_s", (int, float)), ("width", int),
                             ("height", int), ("has_audio", bool)],
    "moments": [("id", str), ("video_id", str), ("source", str), ("start", (int, float)),
                ("end", (int, float)), ("score", int), ("signals", list), ("selected", bool)],
    "timeline": [("moment_id", str), ("clip", str), ("clip_start", (int, float)), ("clip_dur", (int, float))],
}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path, default=None):
    path = pathlib.Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def check_items(kind, items):
    """Devolve lista de erros legíveis (vazia = ok)."""
    errors = []
    for i, item in enumerate(items):
        for field, typ in SCHEMAS[kind]:
            if field not in item:
                errors.append(f"{kind}[{i}]: falta o campo '{field}'")
            elif item[field] is not None and not isinstance(item[field], typ):
                errors.append(f"{kind}[{i}].{field}: tipo {type(item[field]).__name__} inválido")
            elif item[field] is None and field not in ("peak_time",):
                errors.append(f"{kind}[{i}].{field}: está vazio (null)")
    return errors


class Project:
    def __init__(self, path):
        self.dir = pathlib.Path(path)

    def p(self, *parts):
        return self.dir.joinpath(*parts)

    # ---------- estado das etapas (project.json) ----------
    def state(self):
        return load_json(self.p("project.json"), {"stages": {}})

    def mark(self, stage, status, **info):
        st = self.state()
        st.setdefault("stages", {})[stage] = {"status": status, "at": now_iso(), **info}
        save_json(self.p("project.json"), st)

    # ---------- contratos ----------
    def validate(self):
        errors = []
        disc = load_json(self.p("discovery.json"))
        if disc is None:
            return ["discovery.json não existe"]
        vids = disc.get("videos", [])
        errors += check_items("discovery.videos", vids)
        approved = [v for v in vids if v.get("approved")]
        errors += check_items("discovery.downloaded", [v for v in approved if v.get("local_path")])
        for v in approved:
            if v.get("local_path") and not self.p(v["local_path"]).exists():
                errors.append(f"vídeo aprovado {v['id']}: arquivo {v['local_path']} não existe")
        mom = load_json(self.p("moments.json"))
        if mom is not None:
            errors += check_items("moments", mom.get("moments", []))
            ids = {v["id"] for v in vids}
            for m in mom.get("moments", []):
                if m.get("video_id") not in ids:
                    errors.append(f"momento {m.get('id')}: video_id {m.get('video_id')} não está no discovery.json")
                pt = m.get("peak_time")
                if pt is not None and not (m["start"] <= pt <= m["end"]):
                    errors.append(f"momento {m['id']}: peak_time fora do corte")
                sub = m.get("subtitle_pt")
                if sub and not self.p(sub).exists():
                    errors.append(f"momento {m['id']}: legenda {sub} não existe")
        tl = load_json(self.p("output", "timeline.json"))
        if tl is not None:
            errors += check_items("timeline", tl.get("clips", []))
        return errors
