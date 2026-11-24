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
   <criador original> — clipe de <author_handle> — <url>   (quando houver original_creator)
   ...

   #GTA5 #GTARP #<tema>
   ```
   - Capítulos: o primeiro **tem que** ser `00:00`, mínimo 3 capítulos, cada um com ≥ 10 s (regra do YouTube).
   - Todos os autores usados em `moments.json` devem aparecer nos créditos, e o criador original quando houver.
3. **Tags**: 10–15 tags, total < 500 caracteres, mistura PT/EN (`gta 5`, `gta rp`, `gta funny moments`, `fails gta`...).
4. **Thumbnail** (gerada automaticamente):
   1. O quadro é escolhido pelo `gtakit`: momento de maior nota que tenha `peak_time`, em `tempo_no_compilado = clip_start + (peak_time − start)` (`clip_start` vem do `output/timeline.json`). Sem nenhum `peak_time`, usa o meio do último clipe e avisa.
   2. Proponha 3 textos curtos e deixe o usuário escolher: **2–4 palavras, MAIÚSCULAS, no máx. 2 linhas de até 14 caracteres** (ex.: `CAPOTOU` / `NA RAMPA!`). O texto tem que descrever algo que acontece no vídeo.
   3. **Recomendado: várias opções.** Gere candidatas de momentos diferentes, em 2 estilos (faixa embaixo / texto em cima), e mostre a folha numerada ao usuário:
      ```bash
      py -3 -m gtakit thumbnails projects/<slug> --line "CAPOTOU" --line "NA RAMPA!" --count 4
      py -3 -m gtakit thumbnail-pick projects/<slug> <número escolhido>
      ```
      - Para cada um dos melhores momentos, testa o quadro do pico e ±0,5 s/+1 s e fica com o mais nítido; descarta quadros **escuros** (brilho < 40), **borrados** e **quase iguais** a outra candidata (o comando lista o que descartou e por quê).
      - Folha de comparação: `output/thumbs/escolha.jpg`; detalhes em `output/thumbs/candidatas.json`. Com a marca ativa, o estilo "topo" usa a cor da marca.
   4. Opção rápida (uma só imagem, no pico do melhor momento), com o texto escolhido (uma `--line` por linha):
      ```bash
      py -3 -m gtakit thumbnail projects/<slug> --line "CAPOTOU" --line "NA RAMPA!"
      ```
      - O texto vai por `textfile=` (acentos, `:` e `'` funcionam sem escapar); faixa escura na metade de baixo + texto amarelo com borda preta, legível no celular.
      - O comando confere **1280x720** e **menos de 2 MB** (limite do YouTube) e diz em que segundo pegou o quadro.
   5. Abra a imagem escolhida: se o texto sair cortado, encurte o texto e gere de novo.
5. **Confira os direitos** (obrigatório antes de dizer que está pronto):
   ```bash
   py -3 -m gtakit ready projects/<slug>
   ```
   - Saída 0 = pronto; saída 3 = **bloqueado**: lista quem ainda não autorizou. Mostre essa lista ao usuário.
   - Créditos e marca d'água **não** liberam a publicação.
   - Só se o **usuário disser explicitamente** que quer publicar mesmo assim, rode `ready ... --accept-risk "<motivo nas palavras dele>"`. Nunca decida isso sozinho.
   - Grava `output/publish_check.json`; copie `publish_ready` e as pendências para o `metadata.json`.
6. Salve `metadata.json` e mostre tudo ao usuário para revisão.

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
  "credits": [{ "author": "...", "author_handle": "@...", "original_creator": "alanzoka", "url": "..." }],
  "rights_summary": { "permission_granted": 3, "unknown": 2 },
  "publish_ready": false
}
```
- `category_id` 20 = Gaming. `privacy_status` padrão `private` (o usuário publica depois de revisar).

## Checklist de direitos (mostrar sempre)
- Liste os vídeos sem permissão (saída do `gtakit ready`) e alerte sobre risco de Content ID/strike.
- `publish_ready` só é `true` com todas as permissões registradas ou com o risco aceito explicitamente pelo usuário (fica registrado no `publish_check.json`).
- Recomende transformação (comentário, edição, legendas) e créditos visíveis — reduz o risco, mas **não** garante uso justo.

## Depois que o usuário publicar
- Registre o link: `py -3 -m gtakit published projects/<slug> --url "<link>" --title "<título>"`.
- Para acompanhar o desempenho, peça o CSV exportado do YouTube Studio e rode `gtakit metrics-import <arquivo.csv>` e `gtakit report` ([docs/METRICAS.md](../../../docs/METRICAS.md)).

## Upload
- Não faça upload por conta própria. Se o usuário pedir, explique que é preciso a YouTube Data API v3 (OAuth do próprio usuário) e peça autorização explícita antes de qualquer envio.
