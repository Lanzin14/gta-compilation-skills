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
- Whisper: `openai-whisper` (`pip install openai-whisper`) ou `faster-whisper`. Se faltar, peça autorização antes de instalar (baixa modelos de centenas de MB).

## Passos
1. Extraia o áudio só do trecho do momento (mono 16 kHz, formato ideal para o Whisper):
   ```bash
   ffmpeg -ss <start> -to <end> -i <source> -vn -ac 1 -ar 16000 projects/<slug>/subs/<id>.wav
   ```
2. Transcreva **sem informar o idioma** (o Whisper detecta sozinho) e gere SRT + JSON:
   ```bash
   whisper projects/<slug>/subs/<id>.wav --model small --task transcribe \
     --output_format all --output_dir projects/<slug>/subs/
   ```
   - O idioma detectado está no campo `"language"` de `<id>.json` (também aparece no log como `Detected language: ...`).
   - Os tempos do `.srt` já ficam relativos ao início do corte. Renomeie para `<id>.<idioma>.srt`.
3. **Decida se precisa de legenda** e grave em `moments.json` `"language"` e `"needs_translation"`:
   | Situação | Ação |
   |---|---|
   | Idioma ≠ `pt` e há fala (texto com ≥ 3 palavras) | `needs_translation: true` → passo 4 |
   | Idioma = `pt` | `needs_translation: false` → sem legenda |
   | Sem fala, só música/ruído, ou texto repetitivo/sem sentido | `needs_translation: false`, `language: null` → sem legenda |
   Nunca invente falas para preencher a legenda.
4. Traduza cada bloco do `.srt` para PT-BR **mantendo números e tempos**:
   - Linguagem natural de gamer brasileiro, curta (máx. 42 caracteres por linha, 2 linhas).
   - Mantenha nomes, gírias de jogo e termos conhecidos ("wasted", "RP", "cop") quando soarem naturais.
   - Palavrões: suavize se o usuário quiser vídeo "family friendly" (pergunte uma vez).
5. Salve como `projects/<slug>/subs/<id>.pt.srt` e atualize o momento em `moments.json`:
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
