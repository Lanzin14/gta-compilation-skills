---
name: video-editor
description: Monta o compilado final de GTA com ffmpeg — corta os momentos, queima legendas PT-BR, adiciona crédito do criador, normaliza áudio e concatena em um MP4 1080p para o YouTube. Use quando o usuário pedir para editar, montar, renderizar ou exportar o compilado. Lê moments.json e as legendas; gera projects/<slug>/output/compilation.mp4 e chapters.json.
---

# Video Editor

Quarta etapa: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- `projects/<slug>/moments.json` (momentos `selected: true`, na ordem desejada).
- `projects/<slug>/discovery.json` (`author_handle` para o crédito).
- Legendas `subs/<id>.pt.srt` (opcional por momento).

## Pré-requisitos
- `ffmpeg` com `libx264`, `libass` (legendas) e `drawtext` (`ffmpeg -filters | grep -E "subtitles|drawtext"`).

## Ordem dos momentos
- Abra com um dos 2 melhores (gancho nos primeiros 5 s), termine com o melhor de todos.
- Alterne categorias; evite dois clipes do mesmo autor em sequência.

## Passos
1. **Cortar e padronizar cada clipe** (1920x1080, 30 fps, mesmo codec — necessário para concatenar sem erros):
   ```bash
   ffmpeg -ss <start> -t <duração> -i <source> \
     -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,\
   subtitles=projects/<slug>/subs/<id>.pt.srt:force_style='FontSize=22,Outline=2,MarginV=40',\
   drawtext=text='<author_handle>':x=w-tw-30:y=30:fontsize=28:fontcolor=white:borderw=2" \
     -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -ac 2 \
     -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k \
     projects/<slug>/clips/<NN>_<id>.mp4
   ```
   - Sem legenda: remova o trecho `subtitles=...,`.
   - **Vídeo sem áudio** (ver `has_audio` no `discovery.json`): o clipe sairia sem faixa de som e deixaria um buraco no áudio ao concatenar. Adicione silêncio — insira logo após `-i <source>`:
     ```
     -f lavfi -i anullsrc=r=48000:cl=stereo -map 0:v -map 1:a -shortest
     ```
     e remova o `-af "loudnorm=..."` (não há o que normalizar).
   - `<duração>` = `end - start` (segundos). Use `-t`, não `-to`, antes do `-i`: `-to` como opção de entrada não funciona em versões antigas do ffmpeg.
   - `-ss` antes de `-i` é rápido; como recodificamos, o corte fica preciso.
   - Escape `:` e `'` no `author_handle` dentro do `drawtext`.
   - Se aparecer `Cannot find a valid font` (comum no ffmpeg do Windows), indique a fonte no `drawtext`: `fontfile='C\:/Windows/Fonts/arial.ttf':` (Linux: `/usr/share/fonts/...`; macOS: `/System/Library/Fonts/Helvetica.ttc`).
   - **Vídeo vertical (altura > largura, comum no X):** em vez de barras pretas, use fundo desfocado. Troque o início do `-vf` (até `fps=30,`) por:
     ```
     split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=20:2[bg];\
     [b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,fps=30,
     ```
     (descubra a orientação com `ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <source>`).
2. **Lista de concatenação** `projects/<slug>/clips/list.txt`:
   ```
   file '01_abc123.mp4'
   file '02_def456.mp4'
   ```
3. **Concatenar** (sem recodificar, pois todos os clipes têm o mesmo formato):
   ```bash
   ffmpeg -f concat -safe 0 -i projects/<slug>/clips/list.txt -c copy \
     -movflags +faststart projects/<slug>/output/compilation.mp4
   ```
4. **Capítulos**: some as durações (`ffprobe -v error -show_entries format=duration -of csv=p=0 <clip>`) e salve `output/chapters.json`:
   ```json
   [{ "start": 0.0, "moment_ids": ["m03"], "title": "Capotou na rampa" }]
   ```
   - O YouTube exige capítulos de **no mínimo 10 s**: se um clipe tiver menos, junte-o ao capítulo seguinte (`moment_ids` com os dois) e use um título que cubra ambos.
   - Se o **último** clipe tiver menos de 10 s (não há capítulo seguinte), junte-o ao capítulo **anterior**.
   - O primeiro capítulo começa em `0.0`; se houver intro, ela é o primeiro capítulo.
5. Opcional: intro/outro do usuário — padronize-os com o mesmo comando do passo 1 (sem legenda/crédito) e coloque no início/fim de `list.txt`.

## Verificações (obrigatórias antes de concluir)
```bash
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration \
  -of json projects/<slug>/output/compilation.mp4
```
- Resolução 1920x1080, vídeo `h264`, áudio `aac`, duração ≈ soma dos clipes (diferença < 1 s).
- Extraia 3 quadros (início/meio/fim) com `ffmpeg -ss <t> -i ... -frames:v 1 frame.png` e confira legenda e crédito visíveis.
- Se o concat falhar por formato divergente, refaça o passo 1 do clipe problemático — não troque para `-c copy` em clipes não padronizados.
