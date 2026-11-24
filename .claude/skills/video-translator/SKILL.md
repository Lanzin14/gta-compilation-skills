---
name: video-translator
description: Detecta o idioma da fala dos momentos selecionados de vídeos de GTA e, quando não for português, transcreve e gera legendas traduzidas para PT-BR em .srt. Use quando o usuário pedir transcrição, tradução, legendas ou subtítulos. Lê moments.json e gera projects/<slug>/subs/<moment_id>.pt.srt, usados pela video-editor.
---

# Video Translator

Terceira etapa: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- `projects/<slug>/moments.json` (todos os momentos com `selected: true`; o idioma é detectado aqui).
- Idioma de destino (padrão: `pt-BR`).

## Pré-requisitos
- `ffmpeg`.
- Whisper: `faster-whisper` (recomendado: várias vezes mais rápido, sem PyTorch) ou `openai-whisper`. O `scripts/transcribe.py` usa o que estiver instalado. Se nenhum estiver, peça autorização antes de instalar (o modelo `small` baixa ~460 MB no primeiro uso).

## Passos
1. Extraia o áudio de cada momento selecionado (mono 16 kHz, formato ideal para o Whisper; vídeos mudos são pulados):
   ```bash
   py -3 -m gtakit audio projects/<slug>
   ```
   Gera `subs/<id>.wav` com exatamente o `start`/`end` do momento — os mesmos do corte da video-editor, então a legenda sai sincronizada.
2. Transcreva **sem informar o idioma** (o Whisper detecta sozinho):
   ```bash
   py -3 scripts/transcribe.py projects/<slug>/subs/<id>.wav --out-dir projects/<slug>/subs/ --model small
   ```
   (Linux/macOS: `python3` no lugar de `py -3`.)
   - Gera `<id>.srt` e `<id>.json` com `language`, `language_probability` (confiança 0–1; `null` no openai-whisper) e `text`.
   - Código de saída 2 = nenhum motor instalado (a mensagem diz como instalar).
   - Os tempos do `.srt` já ficam relativos ao início do corte. Renomeie para `<id>.<idioma>.srt`.
3. **Decida se precisa de legenda** e grave em `moments.json` `"language"` e `"needs_translation"`:
   | Situação | Ação |
   |---|---|
   | Idioma ≠ `pt` e há fala (texto com ≥ 3 palavras) | `needs_translation: true` → passo 4 |
   | Idioma = `pt` | `needs_translation: false` → sem legenda |
   | Sem fala, só música/ruído, ou texto repetitivo/sem sentido | `needs_translation: false`, `language: null` → sem legenda |
   | `language_probability` < 0,5 (detecção incerta — comum com barulho de jogo) | `needs_translation: false`, `language: null` → sem legenda; avise o usuário |
   Nunca invente falas para preencher a legenda.
4. Traduza cada bloco do `.srt` para PT-BR **mantendo números e tempos**:
   - Linguagem natural de gamer brasileiro, curta (máx. 42 caracteres por linha, 2 linhas).
   - Mantenha nomes, gírias de jogo e termos conhecidos ("wasted", "RP", "cop") quando soarem naturais.
   - Palavrões: suavize se o usuário quiser vídeo "family friendly" (pergunte uma vez).
5. Salve como `projects/<slug>/subs/<id>.pt.srt` e atualize o momento em `moments.json` (caminhos relativos à pasta do projeto; confira depois com `py -3 -m gtakit validate projects/<slug>`):
   ```json
   { "subtitle_original": "subs/m01.en.srt", "subtitle_pt": "subs/m01.pt.srt" }
   ```
6. Mostre ao usuário uma amostra (original → tradução) dos 3 primeiros momentos para validar o tom.

## Formato SRT
```
1
00:00:01,200 --> 00:00:03,050
Mano, olha isso!

2
00:00:03,400 --> 00:00:05,900
NÃO, NÃO, NÃO!
```

## Verificações
- Numeração sequencial, sem tempos sobrepostos, `end > start`.
- Nenhum bloco traduzido vazio.
- Se o Whisper retornar texto sem sentido (música/ruído), marque `"needs_translation": false` e avise o usuário, em vez de inventar falas.
