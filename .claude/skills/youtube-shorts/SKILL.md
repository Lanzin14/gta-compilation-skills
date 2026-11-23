---
name: youtube-shorts
description: Gera YouTube Shorts verticais (1080x1920, até 60 s) a partir dos melhores momentos de um compilado de GTA já analisado, com legenda PT-BR, crédito do criador e título/descrição próprios. Use quando o usuário pedir Shorts, cortes verticais, vídeos curtos ou versão para celular/TikTok/Reels de um compilado. Lê moments.json, discovery.json e as legendas; gera projects/<slug>/output/shorts/.
---

# YouTube Shorts

Etapa opcional, depois da `video-editor` (ou junto dela). Reaproveita os momentos já escolhidos: **um Short por momento**.

## Entrada
- `projects/<slug>/moments.json` (momentos `selected: true`, com `start`/`end`, `score` e `subtitle_pt` quando houver).
- `projects/<slug>/discovery.json` (`width`/`height` ou orientação, `has_audio`, `author_handle`, `url`).
- Quantidade de Shorts (padrão: os **3** momentos de maior `score`; em empate, maior `viral_score`).

## Regras de duração
- Alvo **15–45 s**; máximo **60 s** (funciona em YouTube, TikTok e Reels).
- Momento com mais de 60 s: corte em volta do pico (`peaks`/sinais do momento), mantendo 3–5 s antes e 2–3 s depois.
- Momento com menos de 8 s: não vire Short sozinho (fica fraco); pule-o.

## Passos
1. Para cada momento escolhido, descubra a orientação do vídeo de origem (`ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <source>`).
2. Monte o início do `-vf` conforme a orientação:
   - **Horizontal** (largura ≥ altura): vídeo inteiro na largura, centralizado, sobre fundo desfocado:
     ```
     split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,
     ```
   - **Vertical**:
     ```
     scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,
     ```
3. Renderize (mesmos cuidados da skill video-editor: `-t` em vez de `-to`, silêncio para vídeo mudo, `fontfile=` se faltar fonte):
   ```bash
   ffmpeg -ss <start> -t <duração> -i <source> \
     -vf "<início do passo 2>subtitles=projects/<slug>/subs/<id>.pt.srt:force_style='FontSize=13,Bold=1,Outline=3,MarginV=70,Alignment=2',\
   drawtext=text='<author_handle>':x=(w-tw)/2:y=160:fontsize=48:fontcolor=white:borderw=3" \
     -af "loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -ac 2 \
     -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k -movflags +faststart \
     projects/<slug>/output/shorts/<NN>_<id>.mp4
   ```
   - Sem legenda: remova o trecho `subtitles=...,`.
   - **Vídeo mudo**: insira `-f lavfi -i anullsrc=r=48000:cl=stereo -map 0:v -map 1:a -shortest` logo após `-i <source>` e remova o `-af`.
   - A legenda fica no terço de baixo, mas acima da área dos botões do app (`MarginV=70`); o crédito fica no topo, abaixo da barra de busca (`y=160`).
4. Gere `projects/<slug>/output/shorts/shorts.json`, um item por Short:
   ```json
   [{
     "file": "01_m03.mp4",
     "moment_id": "m03",
     "title": "Ele capotou na rampa e não acreditou 😂 #GTA #Shorts",
     "description": "Clipe original: <author> (<author_handle>) — <url>\n#GTA5 #GTARP #Shorts",
     "duration_s": 24.0
   }]
   ```
   - Título: **até 100 caracteres**, PT-BR, descreve só o que acontece no clipe, termina com `#Shorts`.
   - Descrição: **sempre** o crédito com link do post original.
5. Mostre os títulos ao usuário para aprovação. Upload continua manual (privado por padrão).

## Verificações (obrigatórias)
```bash
ffprobe -v error -show_entries stream=codec_type,width,height -show_entries format=duration -of csv=p=0 <short>
```
- `1080,1920`, faixa de vídeo **e** de áudio, duração ≤ 60 s.
- Extraia um quadro do meio e confira: legenda legível e não cortada nas laterais, crédito visível.
- Direitos autorais: Shorts com `rights: unknown` têm o mesmo risco do compilado — liste-os no resumo.
