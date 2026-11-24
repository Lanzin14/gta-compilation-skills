---
name: viral-moment-analyzer
description: Identifica e pontua os melhores momentos (picos de ação, reação, humor) dentro de vídeos de GTA já baixados, gerando cortes com início/fim. Use quando o usuário pedir para achar os melhores trechos, momentos virais ou pontos de corte. Lê discovery.json e gera projects/<slug>/moments.json.
---

# Viral Moment Analyzer

Segunda etapa: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- `projects/<slug>/discovery.json` (somente vídeos com `"approved": true` e `local_path` existente).

## Pré-requisitos
- `ffmpeg`/`ffprobe` (`ffmpeg -version`).

## Passos
1. Rode a análise (mede volume, cortes de cena e tempo morto de cada vídeo aprovado e gera `moments.json`):
   ```bash
   py -3 -m gtakit analyze projects/<slug>
   ```
   - Se `moments.json` já existir, o comando recusa; use `--force` só se for refazer (apaga edições manuais).
   - O comando imprime cada momento: corte, nota, sinais, `peak_time` e se foi selecionado.
2. Olhe alguns quadros dos momentos selecionados (`ffmpeg -ss <t> -i <video> -frames:v 1 quadro.png`) e aplique o que a medição não vê: penalize (−20, editando `score`/`selected` no `moments.json`) tela de menu, carregamento, HUD cobrindo a ação ou música com copyright evidente. Escreva um `summary` curto do que acontece em cada momento.
3. Mostre os momentos ao usuário (timestamps + motivo) para revisão antes da edição.

## Regras de medição (implementadas em `gtakit/analysis.py` e `gtakit/ff.py`)
- **Vídeo mudo** (`has_audio: false`): sem medição de áudio.
- **Picos de áudio**: volume RMS em janelas de 0,5 s (`aresample=48000,asetnsamples=n=24000,astats=…:reset=1`).
  - Janelas abaixo de -60 dB (silêncio, inclusive `-inf`) contam como **-60 dB** no cálculo da mediana e nunca são pico.
  - **Pico** = janela ≥ **mediana + 6 dB**. Num vídeo quase todo mudo a mediana fica em -60 dB e o grito aparece. Não use média + desvio padrão: trechos mudos inflam o desvio e escondem gritos, e áudio constante gera picos falsos.
  - `reset` do `astats` conta *frames*, não amostras: por isso o `asetnsamples` fixa blocos de 0,5 s e `reset=1`.
- **Mudança de cena**: `select='gt(scene,0.4)'`.
- **Reação**: novo pico de áudio até 2 s depois de um pico ou mudança de cena.
- **Momento**: sinais a menos de 3 s entre si formam um momento.
- **Corte** (vídeos com mais de 40 s): 4 s antes do 1º sinal até 2,5 s depois do último; duração **10–30 s** (mínimo de 10 s por causa dos capítulos do YouTube); no máximo 3 momentos por vídeo.
- **Vídeos de até 40 s** (comum no X): entram inteiros, cortando só o **tempo morto** do começo: trecho que está ao mesmo tempo em silêncio (−40 dB, ≥ 1 s) e com imagem parada (≥ 1 s), encostado no início.
- **`peak_time`**: janela de pico de áudio mais alta dentro do corte; sem pico, a 1ª mudança de cena dentro do corte; sem nenhum dos dois, `null`. Usado pela thumbnail e pelos Shorts.

## Pontuação (0–100)
| Sinal | Peso |
|---|---|
| Pico de áudio forte | 30 |
| Mudança de cena / ação física | 25 |
| Reação (pico de áudio logo após a ação) | 25 |
| Momento compreensível sem contexto externo | 20 |

Penalize (−20) trechos com tela de menu, carregamento, HUD de stream cobrindo a ação ou música com copyright evidente.

**Nota mínima:** descarte (`selected: false`) momentos sem pico de áudio **e** sem mudança de cena, ou com nota < 45 — não há ação que justifique entrar no compilado. Em empate de nota, use o `viral_score` do vídeo.

## Saída: `projects/<slug>/moments.json`
```json
{
  "moments": [
    {
      "id": "m01",
      "video_id": "abc123",
      "source": "source/abc123.mp4",
      "start": 84.5,
      "end": 102.0,
      "score": 87,
      "signals": ["audio_peak", "scene_change", "reaction"],
      "peaks": [91.5, 92.0],
      "peak_time": 92.0,
      "summary": "Carro capota na rampa e o jogador grita",
      "language": null,
      "needs_translation": null,
      "selected": true
    }
  ]
}
```
- `start`/`end`/`peak_time` em segundos (float), no tempo do **vídeo de origem**; `start ≤ peak_time ≤ end`.
- `source` é relativo à pasta do projeto.
- `language` e `needs_translation` ficam `null` aqui: a video-translator detecta o idioma e preenche.
- Considere também `viral_score` do `discovery.json`: em empate, prefira o momento do vídeo mais viral.

## Regras
- Os timestamps vêm das medições; não chute valores. Se um sinal não pôde ser medido, omita-o de `signals`.
- No máximo 3 momentos por vídeo de origem, para variar o compilado.
- Duração total: a definida na gta-compilation (padrão **6 min**). Some as durações dos momentos selecionados e avise se ficar abaixo de 80% da meta (faltam vídeos).
