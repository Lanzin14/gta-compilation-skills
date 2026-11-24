---
name: gta-video-discovery
description: Baixa e classifica por viralidade vídeos de GTA de pessoas jogando, a partir de links de posts do Twitter/X (fonte principal) ou do YouTube. Use quando o usuário enviar links de vídeos de GTA, pedir para baixar/listar/classificar vídeos virais ou iniciar um novo compilado. Gera projects/<slug>/discovery.json, lido pela skill viral-moment-analyzer.
---

# GTA Video Discovery

Primeira etapa do fluxo: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher** (orquestrado pela skill `gta-compilation`).

## Entrada
- **Links de posts do X** (`https://x.com/<usuario>/status/<id>` ou `twitter.com/...`) — fonte principal.
- Opcional: links do YouTube.
- Tema do compilado (ex.: "fails de GTA RP") e quantidade alvo (definida pela gta-compilation; padrão: os 25 mais virais, ~1 momento de ~20 s cada para um compilado de 6 min).

### Limitações do X (explique ao usuário se ele pedir algo diferente)
- O `yt-dlp` **não busca** no X nem lista os posts de um **perfil**: só baixa posts individuais. Se o usuário mandar um perfil, peça que ele abra o perfil (aba Mídia) e copie os links dos posts com vídeo de GTA.
- Não raspe a busca do X nem automatize login: viola os termos do X e pode bloquear a conta.
- Posts sensíveis (NSFW) ou de contas protegidas exigem login. Use o login que o usuário **já tem** no navegador dele, em uma destas formas (pergunte qual navegador ele usa logado no X):
  1. `--cookies-from-browser firefox` (ou `edge`, `chrome`): o `yt-dlp` lê os cookies direto do navegador. Feche o navegador antes se der erro de arquivo em uso. No Chrome/Edge recentes a criptografia nova costuma bloquear a leitura; aí use a opção 2.
  2. `--cookies <arquivo>`: arquivo de cookies exportado pelo usuário (extensão de navegador “cookies.txt”), salvo **fora** do repositório.
  - Nunca peça senha, nunca automatize login e nunca salve cookies no repositório.

## Pré-requisitos
- `yt-dlp` atualizado (`yt-dlp --version`; o X muda com frequência, use `yt-dlp -U` ou `pip install -U yt-dlp`). Se faltar, peça autorização antes de instalar.

## Passos
1. Crie o projeto com `py -3 -m gtakit init projects/<slug> --theme "<tema>"` (slug = tema em kebab-case + data `AAAAMMDD`) e salve os links recebidos em `projects/<slug>/links.txt` (um por linha).
2. Colete os metadados **sem baixar o vídeo**:
   ```bash
   yt-dlp --skip-download --dump-json --ignore-errors -a projects/<slug>/links.txt \
     > projects/<slug>/raw_meta.jsonl
   ```
   - Um post com vários vídeos gera várias linhas (uma por vídeo).
   - Links que falharem: registre em `discovery.json` com `"error"` e avise o usuário (post apagado, protegido ou sem vídeo).
3. Gere o `discovery.json` e a tabela ordenada pela nota de viralidade:
   ```bash
   py -3 -m gtakit discovery projects/<slug>
   ```
   - Lê o `raw_meta.jsonl` e usa os campos do `yt-dlp`: `id` (no X é o id da **mídia**, diferente do número do post — num post com vários vídeos, cada um tem seu id), `webpage_url`, `uploader`, `uploader_id` (@), `timestamp`, `duration`, `width`, `height`, `like_count`, `repost_count`, `comment_count`, `view_count` (pode vir `null`).
   - `post_id` sai da URL (número depois de `/status/`).
   - Rodar de novo **preserva** aprovações, `rights` e categorias já gravadas.
4. Descarte:
   - vídeos que não sejam gameplay de GTA (confirme pelo texto do post em `description`/`title`; na dúvida, pergunte ao usuário);
   - resolução < 480p ou duração > 10 min;
   - reposts de compilados de terceiros.
5. Mostre ao usuário a tabela impressa pelo comando (nota, autor, curtidas, reposts, views, texto). **Peça aprovação** antes de baixar e registre a decisão:
   ```bash
   py -3 -m gtakit approve projects/<slug> <id> <id> ...     # ou --all; recusar: --reject <id>
   ```
6. Baixe somente os aprovados:
   ```bash
   yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]/b" --merge-output-format mp4 \
     -o "projects/<slug>/source/%(id)s.%(ext)s" "<url>"
   ```
   Depois confira os arquivos (duração, tamanho, fps, se tem áudio — muitos vídeos do X são mudos):
   ```bash
   py -3 -m gtakit probe projects/<slug>
   ```
   Ele grava `local_path`, `duration_s`, `width`, `height`, `fps` e `has_audio` e acusa aprovado sem arquivo.

## Nota de viralidade (0–100) — implementada em `gtakit/viral.py`
```
engajamento = like_count + 2*repost_count + comment_count   (campos null contam 0)
horas       = max(1, (agora - timestamp) / 3600)
velocidade  = engajamento / horas
```
- Normalize `engajamento` e `velocidade` entre os candidatos (0–1, escala logarítmica: `log10(x+1)/log10(max+1)`). Se `max` for 0 (nenhum candidato com engajamento), o valor normalizado é 0 — evita divisão por zero.
- `nota = 60*engajamento_norm + 40*velocidade_norm`, arredondada.
- Se `view_count` existir, mostre-o na tabela, mas não o use na nota (nem sempre vem).
- Nunca invente métricas: campo ausente fica `null`.

## Classificação
| Campo | Valores |
|---|---|
| `platform` | `x`, `youtube` |
| `category` | `fail`, `funny`, `stunt`, `chase`, `rp_drama`, `glitch`, `other` |
| `game` | `gta5`, `gta_online`, `gta_rp`, `gta6`, `other` |
| `rights` | `unknown`, `permission_requested`, `permission_granted` |

## Saída: `projects/<slug>/discovery.json`
```json
{
  "theme": "fails de GTA RP",
  "created_at": "2026-11-19",
  "videos": [
    {
      "id": "1857999999999999999",
      "platform": "x",
      "post_id": "1858000000000000000",
      "url": "https://x.com/usuario/status/1858000000000000000",
      "author": "Nome",
      "author_handle": "@usuario",
      "author_url": "https://x.com/usuario",
      "text": "texto do post",
      "posted_at": "2026-11-17T20:15:00Z",
      "timestamp": 1794792663,
      "duration_s": 42.5,
      "width": 1280,
      "height": 720,
      "fps": 30.0,
      "likes": 51000,
      "reposts": 8200,
      "comments": 640,
      "views": null,
      "viral_score": 91,
      "category": "funny",
      "game": "gta_rp",
      "rights": "unknown",
      "approved": true,
      "has_audio": true,
      "local_path": "source/1857999999999999999.mp4",
      "error": null
    }
  ]
}
```

## Direitos autorais (obrigatório)
- Guarde sempre `author_handle` e `url`: a video-editor mostra o `@` no vídeo e a youtube-publisher lista os créditos.
- **Pedidos de permissão:** depois da aprovação da lista, gere `projects/<slug>/permissions.md` com uma mensagem pronta por autor, usando os modelos de [permission-template.md](permission-template.md) no idioma do post (nome do canal: pergunte uma vez ao usuário). Cada item: `@autor`, link do post, mensagem preenchida.
  - **O usuário envia manualmente** (DM ou resposta). Nunca envie mensagens nem automatize o X.
  - Quando o usuário disser que enviou ou que recebeu resposta, atualize `rights` conforme a tabela do modelo. Autor que negou: tire o vídeo (`approved: false`).
- Avise que vídeos com `rights: unknown` podem gerar reivindicação ou strike no YouTube.
