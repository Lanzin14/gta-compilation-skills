---
name: youtube-publisher
description: Prepara título, descrição, tags, capítulos, créditos e demais metadados do YouTube para um compilado de GTA. Use quando o usuário pedir título, descrição, tags, SEO, thumbnail ou para preparar a publicação. Lê discovery.json, moments.json e chapters.json; gera projects/<slug>/output/metadata.json e description.txt. Não faz upload sem autorização explícita.
---

# YouTube Publisher

Última etapa: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- `projects/<slug>/discovery.json` (`author`, `author_handle`, `url` para créditos).
- `projects/<slug>/moments.json` (resumos dos momentos).
- `projects/<slug>/output/chapters.json` e `compilation.mp4`.

## Passos
1. **Título** — gere 5 opções e deixe o usuário escolher:
   - Máx. 70 caracteres, em PT-BR, palavra-chave no início ("GTA 5", "GTA RP").
   - Use o melhor momento real como gancho; nada que não aconteça no vídeo (sem clickbait enganoso).
   - Ex.: `GTA 5 RP: os FAILS mais absurdos da semana #12`.
2. **Descrição** (`description.txt`):
   ```
   <2 linhas de gancho com palavras-chave>

   ⏱️ Capítulos
   00:00 <título do 1º momento>
   00:18 <...>

   🎮 Créditos (assista os originais!)
   <author> (<author_handle>) — <url do post original>
   ...

   #GTA5 #GTARP #<tema>
   ```
   - Capítulos: o primeiro **tem que** ser `00:00`, mínimo 3 capítulos, cada um com ≥ 10 s (regra do YouTube).
   - Todos os autores usados em `moments.json` devem aparecer nos créditos.
3. **Tags**: 10–15 tags, total < 500 caracteres, mistura PT/EN (`gta 5`, `gta rp`, `gta funny moments`, `fails gta`...).
4. **Thumbnail** (gerada automaticamente):
   1. Escolha o quadro do momento de maior nota que tenha `peak_time`: `tempo_no_compilado = clip_start + (peak_time − start)` (campos do `moments.json`). Se nenhum momento tiver `peak_time`, use o meio do clipe (`clip_start + duração/2`) e avise o usuário. Abra o quadro e, se for um corte de cena borrado, tente 0,5 s depois.
   2. Proponha 3 textos curtos e deixe o usuário escolher: **2–4 palavras, MAIÚSCULAS, no máx. 2 linhas de até 14 caracteres** (ex.: `CAPOTOU` / `NA RAMPA!`). O texto tem que descrever algo que acontece no vídeo.
   3. Grave o texto em `projects/<slug>/output/thumb_text.txt` (uma linha por linha da imagem, **sem quebra de linha no final**). Usar `textfile=` evita ter que escapar acentos, `:` e `'`.
   4. Gere a imagem:
      ```bash
      ffmpeg -ss <tempo_no_compilado> -i projects/<slug>/output/compilation.mp4 -frames:v 1 \
        -vf "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=saturation=1.3:contrast=1.1,\
      drawbox=y=ih*0.55:w=iw:h=ih*0.45:color=black@0.45:t=fill,\
      drawtext=textfile=projects/<slug>/output/thumb_text.txt:fontsize=120:fontcolor=yellow:borderw=8:bordercolor=black:line_spacing=10:x=50:y=h-th-50" \
        -q:v 2 projects/<slug>/output/thumbnail.jpg
      ```
      - Faixa escura na metade de baixo + texto amarelo com borda preta: legível em qualquer cena e no celular.
      - `Cannot find a valid font`: adicione `fontfile=` no `drawtext`, como explicado na skill video-editor.
   5. Verifique: 1280x720 (`ffprobe -v error -show_entries stream=width,height -of csv=p=0 <arquivo>`) e **menos de 2 MB** (limite do YouTube). Abra a imagem e confira se o texto não saiu cortado; se sair, reduza o `fontsize`.
5. Salve `metadata.json` e mostre tudo ao usuário para revisão.

## Saída: `projects/<slug>/output/metadata.json`
```json
{
  "title": "...",
  "description_file": "description.txt",
  "tags": ["gta 5", "gta rp"],
  "category_id": "20",
  "default_language": "pt-BR",
  "privacy_status": "private",
  "made_for_kids": false,
  "contains_synthetic_media": false,
  "video_file": "compilation.mp4",
  "thumbnail_file": "thumbnail.jpg",
  "credits": [{ "author": "...", "author_handle": "@...", "url": "..." }],
  "rights_summary": { "permission_granted": 3, "unknown": 2 }
}
```
- `category_id` 20 = Gaming. `privacy_status` padrão `private` (o usuário publica depois de revisar).

## Checklist de direitos (mostrar sempre)
- Liste os vídeos com `rights: unknown` e alerte sobre risco de Content ID/strike.
- Recomende transformação (comentário, edição, legendas) e créditos visíveis — reduz o risco, mas **não** garante uso justo.

## Upload
- Não faça upload por conta própria. Se o usuário pedir, explique que é preciso a YouTube Data API v3 (OAuth do próprio usuário) e peça autorização explícita antes de qualquer envio.
