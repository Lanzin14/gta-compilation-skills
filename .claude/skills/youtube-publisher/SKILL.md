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
   1. O quadro é escolhido pelo `gtakit`: momento de maior nota que tenha `peak_time`, em `tempo_no_compilado = clip_start + (peak_time − start)` (`clip_start` vem do `output/timeline.json`). Sem nenhum `peak_time`, usa o meio do último clipe e avisa.
   2. Proponha 3 textos curtos e deixe o usuário escolher: **2–4 palavras, MAIÚSCULAS, no máx. 2 linhas de até 14 caracteres** (ex.: `CAPOTOU` / `NA RAMPA!`). O texto tem que descrever algo que acontece no vídeo.
   3. Gere a imagem com o texto escolhido (uma `--line` por linha):
      ```bash
      py -3 -m gtakit thumbnail projects/<slug> --line "CAPOTOU" --line "NA RAMPA!"
      ```
      - O texto vai por `textfile=` (acentos, `:` e `'` funcionam sem escapar); faixa escura na metade de baixo + texto amarelo com borda preta, legível no celular.
      - O comando confere **1280x720** e **menos de 2 MB** (limite do YouTube) e diz em que segundo pegou o quadro.
   4. Abra a imagem: se o quadro for um corte de cena borrado ou o texto sair cortado, avise e ajuste (texto mais curto).
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
