---
name: gta-video-discovery
description: Baixa e classifica por viralidade vídeos de GTA de pessoas jogando, a partir de links de posts do Twitter/X (fonte principal) ou do YouTube. Use quando o usuário enviar links de vídeos de GTA, pedir para baixar/listar/classificar vídeos virais ou iniciar um novo compilado. Gera projects/<slug>/discovery.json, lido pela skill viral-moment-analyzer.
---

# GTA Video Discovery

Primeira etapa do fluxo: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher** (orquestrado pela skill `gta-compilation`).

## Entrada
- **Links de posts do X** (`https://x.com/<usuario>/status/<id>` ou `twitter.com/...`) — fonte principal.
- Opcional: links do YouTube.
- Tema do compilado (ex.: "fails de GTA RP") e quantidade alvo (padrão: os 15 mais virais).

### Limitações do X (explique ao usuário se ele pedir algo diferente)
- O `yt-dlp` **não busca** no X nem lista os posts de um **perfil**: só baixa posts individuais. Se o usuário mandar um perfil, peça que ele abra o perfil (aba Mídia) e copie os links dos posts com vídeo de GTA.
- Não raspe a busca do X nem automatize login: viola os termos do X e pode bloquear a conta.
- Posts sensíveis (NSFW) ou de contas protegidas exigem login. Nesse caso, peça ao usuário um arquivo de cookies exportado do navegador **dele** e use `--cookies <arquivo>`. Nunca salve cookies no repositório.

## Pré-requisitos
- `yt-dlp` atualizado (`yt-dlp --version`; o X muda com frequência, use `yt-dlp -U` ou `pip install -U yt-dlp`). Se faltar, peça autorização antes de instalar.

## Passos
1. Crie a pasta `projects/<slug>/` (slug = tema em kebab-case + data `AAAAMMDD`) e salve os links recebidos em `projects/<slug>/links.txt` (um por linha).
2. Colete os metadados **sem baixar o vídeo**:
   ```bash
   yt-dlp --skip-download --dump-json --ignore-errors -a projects/<slug>/links.txt \
     > projects/<slug>/raw_meta.jsonl
   ```
   - Um post com vários vídeos gera várias linhas (uma por vídeo).
   - Links que falharem: registre em `discovery.json` com `"error"` e avise o usuário (post apagado, protegido ou sem vídeo).
3. Para cada vídeo, use os campos do `yt-dlp`: `id`, `webpage_url`, `uploader` (nome), `uploader_id` (@), `timestamp`, `duration`, `like_count`, `repost_count`, `comment_count`, `view_count` (pode vir `null`), `height`.
4. Descarte:
   - vídeos que não sejam gameplay de GTA (confirme pelo texto do post em `description`/`title`; na dúvida, pergunte ao usuário);
   - resolução < 480p ou duração > 10 min;
   - reposts de compilados de terceiros.
5. Calcule a **nota de viralidade** (abaixo), ordene e mostre ao usuário uma tabela (autor, texto curto, curtidas, reposts, nota). **Peça aprovação** antes de baixar.
6. Baixe somente os aprovados:
   ```bash
   yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]/b" --merge-output-format mp4 \
     -o "projects/<slug>/source/%(id)s.%(ext)s" "<url>"
   ```
   Confira que cada arquivo existe e tem áudio: `ffprobe -v error -show_entries stream=codec_type -of csv=p=0 <arquivo>`.

## Nota de viralidade (0–100)
```
engajamento = like_count + 2*repost_count + comment_count   (campos null contam 0)
horas       = max(1, (agora - timestamp) / 3600)
velocidade  = engajamento / horas
```
- Normalize `engajamento` e `velocidade` entre os candidatos (0–1, escala logarítmica: `log10(x+1)/log10(max+1)`).
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
      "id": "1858000000000000000",
      "platform": "x",
      "url": "https://x.com/usuario/status/1858000000000000000",
      "author": "Nome",
      "author_handle": "@usuario",
      "author_url": "https://x.com/usuario",
      "text": "texto do post",
      "posted_at": "2026-11-17T20:15:00Z",
      "duration_s": 42.5,
      "height": 720,
      "likes": 51000,
      "reposts": 8200,
      "comments": 640,
      "views": null,
      "viral_score": 91,
      "category": "funny",
      "game": "gta_rp",
      "rights": "unknown",
      "approved": true,
      "local_path": "projects/<slug>/source/1858000000000000000.mp4",
      "error": null
    }
  ]
}
```

## Direitos autorais (obrigatório)
- Guarde sempre `author_handle` e `url`: a video-editor mostra o `@` no vídeo e a youtube-publisher lista os créditos.
- Recomende pedir permissão aos autores (resposta ou DM no X) e atualizar `rights`.
- Avise que vídeos com `rights: unknown` podem gerar reivindicação ou strike no YouTube.
