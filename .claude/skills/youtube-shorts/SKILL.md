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

## Passos
1. Gere os Shorts (por padrão os 3 momentos de maior nota; desempate pela viralidade):
   ```bash
   py -3 -m gtakit shorts projects/<slug> --count 3
   ```
   Cria `output/shorts/<NN>_<id>.mp4` e `output/shorts/shorts.json` (com a descrição já trazendo o crédito) e confere 1080x1920, áudio e ≤ 60 s.
2. Escreva o `title` de cada Short no `shorts.json`: **até 100 caracteres**, PT-BR, descreve só o que acontece no clipe, termina com `#Shorts`.
3. Mostre os títulos ao usuário para aprovação. Upload continua manual (privado por padrão).

## Regras (implementadas em `gtakit/render.py`)
- **Duração:** alvo 15–45 s; máximo **60 s**. Momento mais longo: janela de 60 s começando 4 s antes do `peak_time` (sem `peak_time`, os primeiros 60 s). Momento com menos de 8 s não vira Short.
- **Horizontal:** vídeo inteiro na largura, centralizado sobre fundo desfocado. **Vertical:** ocupa a tela.
- **Legenda** no terço de baixo, acima dos botões do app (`FontSize=13,Bold=1,Outline=3,MarginV=70`); **crédito** no topo (`y=160`).
- **Vídeo mudo:** faixa de silêncio; mesmos cuidados de fonte e corte da video-editor.
- **Marca do canal** (se configurada): marca d'água centralizada abaixo do crédito e logo; mesmo fps, fade e volume do compilado.
- `shorts.json`: `file`, `moment_id`, `title`, `description` (sempre com o crédito e o link do post original), `duration_s`.

## Verificações (obrigatórias)
- O comando já confere `1080x1920`, faixa de vídeo **e** de áudio e duração ≤ 60 s.
- Extraia um quadro do meio e confira: legenda legível e não cortada nas laterais, crédito visível.
- Direitos autorais: Shorts com `rights: unknown` têm o mesmo risco do compilado — liste-os no resumo.
