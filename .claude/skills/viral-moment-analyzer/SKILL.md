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
0. Verifique se o vídeo tem áudio: `ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 <video>` (saída vazia = mudo). Vídeo mudo: pule os passos 1 e 3.
1. **Picos de áudio** (gritos, explosões, risadas) — volume por janela de 0,5 s:
   ```bash
   ffmpeg -i <video> -af "aresample=48000,asetnsamples=n=24000:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=audio_rms.txt" -f null -
   ```
   - `asetnsamples=24000` em 48 kHz = blocos de 0,5 s; `reset=1` zera a medição a cada bloco. Cada `pts_time` no arquivo é o início da janela.
   - Não use `reset=<amostras>`: o `reset` conta *frames* de áudio, e o resultado vira uma média acumulada que esconde os picos.
   - Janelas abaixo de -60 dB (silêncio, inclusive `-inf`) contam como **-60 dB** no cálculo da mediana e nunca são pico.
   - **Pico** = janela ≥ **mediana + 6 dB**. Assim, num vídeo quase todo mudo a mediana fica em -60 dB e o grito aparece. Não use média + desvio padrão: trechos mudos inflam o desvio e escondem os gritos, e áudio constante gera picos falsos.
2. **Mudanças bruscas de cena** (batidas, quedas, explosões):
   ```bash
   ffmpeg -i <video> -vf "select='gt(scene,0.4)',showinfo" -f null - 2>&1 | grep pts_time
   ```
3. **Reação**: novo pico de áudio até 2 s depois de um pico ou mudança de cena (grito/risada de reação). A transcrição ainda não existe nesta etapa (é criada pela video-translator), então use só o áudio.
4. Agrupe sinais que estejam a menos de 3 s entre si num mesmo **momento**.
5. Defina o corte: começa 3–5 s **antes** do pico (contexto) e termina 2–3 s **depois** (reação). Duração: **10–30 s** (mínimo de 10 s por causa da regra de capítulos do YouTube; se o vídeo inteiro tiver menos de 10 s, use-o completo).
   - **Vídeos curtos (≤ 40 s, comum no X):** geralmente o vídeo inteiro já é o momento. Use-o completo, cortando só o tempo morto do começo/fim, medido assim:
     ```bash
     ffmpeg -i <video> -af silencedetect=noise=-40dB:d=1 -vf freezedetect=n=0.003:d=1 -f null - 2>&1 \
       | grep -E "silence_(start|end)|freeze_(start|end)"
     ```
     Tempo morto = trecho que está **ao mesmo tempo** em silêncio e com imagem parada, encostado no início ou no fim. Se não houver, não corte.
     Se aparecer só `*_start` sem o `*_end` correspondente, o trecho vai até o fim do vídeo.
6. Pontue e ordene. Mostre os top momentos ao usuário (timestamps + motivo) para revisão antes da edição.

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
      "source": "projects/<slug>/source/abc123.mp4",
      "start": 84.5,
      "end": 102.0,
      "score": 87,
      "signals": ["audio_peak", "scene_change", "reaction"],
      "summary": "Carro capota na rampa e o jogador grita",
      "language": null,
      "needs_translation": null,
      "selected": true
    }
  ]
}
```
- `start`/`end` em segundos (float).
- `language` e `needs_translation` ficam `null` aqui: a video-translator detecta o idioma e preenche.
- Considere também `viral_score` do `discovery.json`: em empate, prefira o momento do vídeo mais viral.

## Regras
- Os timestamps vêm das medições; não chute valores. Se um sinal não pôde ser medido, omita-o de `signals`.
- No máximo 3 momentos por vídeo de origem, para variar o compilado.
- Duração total: a definida na gta-compilation (padrão **6 min**). Some as durações dos momentos selecionados e avise se ficar abaixo de 80% da meta (faltam vídeos).
