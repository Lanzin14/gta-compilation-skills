"""Créditos, permissões de uso e bloqueio de publicação.

Princípio: crédito e marca d'água NÃO substituem autorização. Um vídeo só conta como liberado
quando o dono do conteúdo deu permissão (registrada com prova) ou quando o usuário aceitou o risco
explicitamente, com motivo — e isso fica registrado.

Quem precisa autorizar: o criador original (`original_creator`, ex.: o streamer) quando houver;
senão, o autor do post. A permissão do clipador sozinha não libera um corte da live de outra pessoa.
"""
import pathlib
import re

from .project import load_json, now_iso, save_json

DEFAULT_LEDGER = pathlib.Path("data") / "permissions.json"
STATUSES = ("unknown", "requested", "granted", "denied")


def key(name):
    """Chave do registro: @handle ou nome, sem @, minúsculo."""
    return (name or "").strip().lstrip("@").lower()


def _drawable(text):
    """Remove emojis e seletores de variação: as fontes do drawtext não os têm (viram um quadrado)."""
    keep = (c for c in text if ord(c) <= 0xFFFF and not 0xFE00 <= ord(c) <= 0xFE0F and not 0x2600 <= ord(c) <= 0x27BF)
    return " ".join("".join(keep).split())


def credit_text(video):
    """Texto do crédito exibido no vídeo: 'criador | clipe @autor' ou só '@autor' (sem emojis)."""
    handle = video.get("author_handle") or video.get("author") or ""
    creator = (video.get("original_creator") or {}).get("name")
    if creator and key(creator) != key(handle):
        return _drawable(f"{creator} | clipe {handle}")
    return _drawable(handle)


def owner_of(video):
    """Quem precisa autorizar o uso deste vídeo."""
    creator = (video.get("original_creator") or {}).get("name")
    return creator or video.get("author_handle")


class Ledger:
    """Registro local de permissões (data/permissions.json, fora do Git), válido entre projetos."""

    def __init__(self, path=DEFAULT_LEDGER):
        self.path = pathlib.Path(path)
        self.data = load_json(self.path, {"people": {}})

    def get(self, name):
        return self.data["people"].get(key(name))

    def set(self, name, status, evidence=None, post_id=None, notes=None):
        if status not in STATUSES:
            raise ValueError(f"status inválido: {status} (use {', '.join(STATUSES)})")
        if status == "granted" and not evidence:
            raise ValueError("permissão concedida precisa de prova (--evidence: link da resposta ou caminho do print)")
        entry = self.data["people"].setdefault(key(name), {"name": name, "posts": {}})
        entry["name"] = name
        if post_id:  # permissão só para um post específico
            entry["posts"][str(post_id)] = {"status": status, "evidence": evidence, "at": now_iso()}
        else:        # permissão geral (vale para qualquer clipe dessa pessoa)
            entry.update({"status": status, "evidence": evidence, "at": now_iso()})
        if notes:
            entry["notes"] = notes
        save_json(self.path, self.data)
        return entry

    def status_for(self, video):
        """Status do vídeo segundo o registro: post específico > permissão geral > unknown."""
        entry = self.get(owner_of(video))
        if not entry:
            return "unknown"
        post = entry.get("posts", {}).get(str(video.get("post_id")))
        if post:
            return post["status"]
        return entry.get("status", "unknown")


def sync_project(disc, ledger):
    """Aplica o registro ao discovery.json: atualiza `rights` e reprova vídeos negados."""
    changes = []
    for v in disc["videos"]:
        st = ledger.status_for(v)
        if st == "unknown" and v.get("rights") in ("requested", "permission_requested"):
            continue  # mantém um pedido registrado só no projeto
        new = {"granted": "permission_granted", "requested": "permission_requested",
               "denied": "denied", "unknown": "unknown"}[st]
        if v.get("rights") != new:
            changes.append((v["id"], v.get("rights"), new))
            v["rights"] = new
        if new == "denied" and v.get("approved"):
            v["approved"] = False
            changes.append((v["id"], "approved", "removido (permissão negada)"))
    return changes


def publish_check(used_videos, override=None):
    """Decide se o compilado pode ser marcado como pronto para publicar.

    override: {"reason": "..."} quando o usuário aceita o risco explicitamente.
    """
    pending = [{"id": v["id"], "owner": owner_of(v), "rights": v.get("rights", "unknown")}
               for v in used_videos if v.get("rights") != "permission_granted"]
    result = {"checked_at": now_iso(), "videos": len(used_videos), "pending": pending,
              "publish_ready": not pending, "override": None,
              "note": "Créditos e marca d'água não substituem autorização de uso."}
    if pending and override and override.get("reason", "").strip():
        result["override"] = {"reason": override["reason"].strip(), "at": now_iso()}
        result["publish_ready"] = True
    return result


# ---------------------------------------------------------------- mensagens de pedido
def parse_templates(text):
    """Lê permission-template.md -> {idioma: {tipo: mensagem}} (idiomas: pt, en, es; tipos: dm, reply)."""
    langs = {"Português": "pt", "English": "en", "Español": "es"}
    out, lang, kind = {}, None, None
    blocks = re.split(r"(```.*?```)", text, flags=re.S)
    for chunk in blocks:
        if chunk.startswith("```"):
            if lang and kind:
                out.setdefault(lang, {})[kind] = chunk.strip("`").strip("\n")
            kind = None
            continue
        for line in chunk.splitlines():
            h = re.match(r"^##\s+(.+)$", line)
            if h:
                lang = langs.get(h.group(1).strip())
            k = re.match(r"^\*\*(DM|Resposta ao post|Reply)\*\*", line.strip())
            if k:
                kind = "dm" if k.group(1) == "DM" else "reply"
    return out


PT_WORDS = {"que", "não", "nao", "mano", "kkk", "kkkk", "com", "uma", "pra", "isso", "ele", "ela", "muito", "demais"}
ES_WORDS = {"jaja", "jajaja", "qué", "pero", "muy", "esto", "hermano", "con", "una", "para"}


def guess_lang(text):
    words = set(re.findall(r"[a-záéíóúãõçñ]+", (text or "").lower()))
    if "kkk" in (text or "").lower() or len(words & PT_WORDS) >= 1 and len(words & PT_WORDS) >= len(words & ES_WORDS):
        return "pt"
    if len(words & ES_WORDS) >= 2:
        return "es"
    return "en"


def fill(template, video, channel):
    link = video.get("url") or ""
    reps = {"<@autor>": video.get("author_handle") or "", "<@author>": video.get("author_handle") or "",
            "<link do post>": link, "<post link>": link, "<enlace>": link,
            "<nome do canal>": channel, "<channel name>": channel, "<nombre del canal>": channel}
    for k, v in reps.items():
        template = template.replace(k, v)
    return template


def x_length(message):
    """Tamanho como o X conta: todo link vale 23 caracteres."""
    return len(re.sub(r"https?://\S+", "x" * 23, message))
