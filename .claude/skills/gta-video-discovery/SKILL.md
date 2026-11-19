---
name: gta-video-discovery
description: Encontra e classifica vídeos de GTA (clipes, fails, stunts, momentos engraçados) no YouTube/Twitch para compor um compilado. Use quando o usuário pedir para buscar, listar, filtrar ou classificar vídeos de GTA, ou iniciar um novo compilado. Gera projects/<slug>/discovery.json, lido pela skill viral-moment-analyzer.
---

# GTA Video Discovery

Primeira etapa do fluxo: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- Tema do compilado (ex.: "fails de GTA 5 RP", "stunts de moto GTA Online").
- Opcional: idioma de origem, período, quantidade alvo (padrão: 20 candidatos).

## Pré-requisitos
- `yt-dlp` (`pip install yt-dlp`). Verifique com `yt-dlp --version`. Se faltar, peça autorização antes de instalar.

## Passos
1. Crie a pasta do projeto: `projects/<slug>/` (slug = tema em kebab-case + data `AAAAMMDD`).
2. Busque **apenas metadados** (sem baixar vídeo):
   ```bash
   yt-dlp "ytsearch30:<termo>" --flat-playlist --dump-json > projects/<slug>/raw_search.jsonl
   yt-dlp --dump-json --skip-download "<url>"   # metadados completos de um vídeo
   ```
   Use 2–4 termos variados (PT e EN, ex.: "GTA 5 funny moments", "GTA RP engraçado").
3. Descarte vídeos que:
   - tenham menos de 720p, ou mais de 20 min (difícil de analisar);
   - sejam compilados de terceiros (reupload de reupload);
   - tenham licença/descrição que proíba reutilização.
4. Classifique cada vídeo restante (ver tabela abaixo) e salve `discovery.json`.
5. Mostre ao usuário uma tabela resumida (título, canal, categoria, nota) e **peça para ele aprovar** a lista antes de baixar qualquer coisa.
6. Após aprovação, baixe somente os aprovados:
   ```bash
   yt-dlp -f "bv*[height<=1080]+ba/b[height<=1080]" --merge-output-format mp4 \
     -o "projects/<slug>/source/%(id)s.%(ext)s" "<url>"
   ```

## Classificação
| Campo | Valores |
|---|---|
| `category` | `fail`, `funny`, `stunt`, `chase`, `rp_drama`, `glitch`, `other` |
| `game` | `gta5`, `gta_online`, `gta_rp`, `gta6`, `other` |
| `language` | código ISO (`en`, `pt`, `es`...) |
| `potential` | 1–5 (engajamento visível: views/idade, likes/views, comentários) |
| `rights` | `unknown`, `permission_requested`, `permission_granted`, `cc_by` |

Nota de potencial (guia): views por dia desde a publicação + razão likes/views > 3% → +1; título/thumbnail com momento claro → +1.

## Saída: `projects/<slug>/discovery.json`
```json
{
  "theme": "fails de GTA 5 RP",
  "created_at": "2026-11-19",
  "videos": [
    {
      "id": "abc123",
      "url": "https://www.youtube.com/watch?v=abc123",
      "title": "...",
      "channel": "...",
      "channel_url": "...",
      "duration_s": 312,
      "resolution": "1080p",
      "views": 120000,
      "language": "en",
      "category": "fail",
      "game": "gta5",
      "potential": 4,
      "rights": "unknown",
      "local_path": "projects/<slug>/source/abc123.mp4",
      "approved": true
    }
  ]
}
```

## Direitos autorais (obrigatório)
- Registre **sempre** `channel` e `channel_url`: serão usados nos créditos pela youtube-publisher.
- Recomende ao usuário pedir permissão aos criadores (e-mail/Discord da descrição) e atualizar `rights`.
- Avise que vídeos com `rights: unknown` podem gerar reivindicação de Content ID ou strike.
- Nunca invente métricas: se um campo não vier do `yt-dlp`, use `null`.
