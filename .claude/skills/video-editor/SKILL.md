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

## Passos
1. Monte o compilado:
   ```bash
   py -3 -m gtakit render projects/<slug>            # --preset ultrafast para um rascunho rápido
   ```
   Ele corta e padroniza cada clipe na ordem abaixo, junta tudo em `output/compilation.mp4`, grava `output/timeline.json` (onde cada clipe começa: `clip_start`) e `output/chapters.json`, e confere resolução, áudio e duração.
2. Dê um título curto a cada capítulo em `output/chapters.json` (`title`), descrevendo o que acontece.
3. Opcional: intro/outro do usuário — padronize-os com o mesmo filtro dos clipes (sem legenda/crédito) e coloque no início/fim de `clips/list.txt`; depois rode só a concatenação (`ffmpeg -f concat -safe 0 -i clips/list.txt -c copy -movflags +faststart output/compilation.mp4` dentro da pasta do projeto) e atualize os `clip_start`.

## Regras (implementadas em `gtakit/render.py` e `gtakit/timeline.py`)
- **Ordem** (`--order smart`, padrão; `gtakit/timeline.py`): **fecha com o melhor** (maior nota final); **abre com um gancho** (mais energia — reação + retenção — entre os de nota acima da mediana, de preferência ≤ 30 s); no meio, **nunca o mesmo criador em sequência** (o streamer do `original_creator` conta como a mesma pessoa) quando houver ordem possível, alternando energia e evitando repetir categoria. É determinística, e o porquê fica em `output/timeline.json` (`order_notes`); sem ordem possível, avisa. `--order legacy` usa a regra antiga (abre com o 2º melhor).
- **Padronização** (necessária para juntar sem recodificar): 1920x1080, 30 ou 60 fps (`config/brand.json`), SAR 1:1, yuv420p, H.264 `-crf 20`, AAC 192 kbps 48 kHz estéreo, volume normalizado em -14 LUFS (`loudnorm`, em 2 passadas por padrão), fade curto entre clipes.
- **Marca do canal** ([docs/MARCA.md](../../../docs/MARCA.md)): com `channel_handle` preenchido, entram abertura, marca d'água, logo e tela final. Sem ele, o render avisa e segue sem marca — **pergunte ao usuário o @ do canal**, nunca invente.
- **Vídeo horizontal:** escala + barras (`pad`). **Vertical:** fundo desfocado do próprio vídeo atrás.
- **Legenda** (`subtitle_pt`): queimada com `FontSize=22,Outline=2,MarginV=40`. **Crédito:** no canto superior direito, `@autor` ou `criador | clipe @autor` (lido de `credits/<id>.txt` com `expansion=none`: qualquer caractere funciona; emojis são removidos porque a fonte não os desenha).
- **Vídeo mudo:** recebe faixa de silêncio (sem ela, a junção deixa um buraco no áudio) e não passa pelo `loudnorm`.
- **Corte:** `-ss <start> -t <duração>` antes do `-i` (o `-to` antes do `-i` não funciona em ffmpeg antigo).
- **Fonte:** se o ffmpeg disser `Cannot find a valid font` (comum no Windows), o gtakit tenta de novo com `C:/Windows/Fonts/arial.ttf` (Linux: DejaVu).
- **Capítulos:** mínimo de **10 s** (regra do YouTube): clipe curto junta ao seguinte; o último curto junta ao anterior; o 1º começa em `0.0`.

## Verificações (obrigatórias antes de concluir)
```bash
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration \
  -of json projects/<slug>/output/compilation.mp4
```
- O `render` já confere resolução 1920x1080, áudio presente e duração ≈ soma dos clipes (diferença < 1 s); se falhar, ele sai com erro e diz o motivo.
- Extraia 3 quadros (início/meio/fim) com `ffmpeg -ss <t> -i ... -frames:v 1 frame.png` e confira legenda e crédito visíveis.
- Se o concat falhar por formato divergente, refaça o passo 1 do clipe problemático — não troque para `-c copy` em clipes não padronizados.
