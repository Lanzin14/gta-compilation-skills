---
name: viral-moment-analyzer
description: Ranqueia os clipes de GTA já baixados por 6 critérios (viralidade, humor, reação, contexto, qualidade, retenção), recomenda o corte de cada um sem cortar piadas, aponta duplicados e alertas, e escolhe os melhores momentos. Use quando o usuário pedir para achar os melhores trechos, momentos virais ou pontos de corte. Lê discovery.json e gera projects/<slug>/moments.json.
---

# Viral Moment Analyzer

Segunda etapa: **discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher**.

## Entrada
- `projects/<slug>/discovery.json` (somente vídeos com `"approved": true` e `local_path` existente).

## Pré-requisitos
- `ffmpeg`/`ffprobe` (`ffmpeg -version`).

## Passos
1. **Transcrição antes do ranking** (recomendado: é o que mede humor e evita cortar falas):
   ```bash
   py -3 -m gtakit audio projects/<slug> --full
   py -3 scripts/transcribe.py projects/<slug>/subs/<video_id>.full.wav --out-dir projects/<slug>/subs/ --model small
   ```
   (um `transcribe.py` por vídeo; gera `subs/<video_id>.full.json`, que o ranking lê sozinho). Sem Whisper, siga sem: o ranking avisa onde faltou.
2. Rode a análise (mede cada vídeo uma vez, com cache em `analysis/`, e gera `moments.json` + `ranking.md`):
   ```bash
   py -3 -m gtakit analyze projects/<slug>
   ```
   - Se `moments.json` já existir, o comando recusa; use `--force` só se for refazer (apaga edições manuais).
3. **Olhe** quadros dos primeiros colocados (`ffmpeg -ss <peak_time> -i <video> -frames:v 1 quadro.png`) e leia as transcrições. Registre em `projects/<slug>/judgments.json` o que a medição não vê — sempre com nota **e motivo** (sem motivo, é ignorado):
   ```json
   {"<video_id>": {"humor": {"score": 90, "reason": "a física do carro capotando é absurda"},
                   "qualidade": {"score": 30, "reason": "HUD da live cobre metade da ação"}}}
   ```
   Depois rode só `py -3 -m gtakit rank projects/<slug>` (não mede de novo). Escreva um `summary` curto de cada momento selecionado no `moments.json`.
4. Mostre ao usuário a tabela do `ranking.md` (criador, URL, nota por critério, nota final, justificativa, corte recomendado, duração, alertas) para revisão antes da edição.

## Ranking (detalhes em [docs/RANKING.md](../../../docs/RANKING.md); pesos em `config/ranking.json`)
- **6 notas independentes (0–100):** viralidade (métricas do post — **não** é qualidade do conteúdo), humor, reação, contexto, qualidade, retenção. Nota final = média ponderada.
- **Clipes de até 90 s entram inteiros** (só apara tempo morto das pontas). Mais longos: corte em volta dos eventos, recuando pela conversa contínua que prepara a ação (até 25 s) e indo até o fim da reação; **nunca no meio de uma fala**.
- **Falta de pico de volume não descarta ninguém**: áudio alto constante tem reação baixa, mas humor/contexto/qualidade decidem. Sem transcrição e sem pistas, humor = 50 (neutro) com alerta.
- **Duplicados** (o mesmo clipe repostado) e **trechos repetitivos** são detectados; fica só o melhor de cada grupo.
- Ajuste por compilado: `projects/<slug>/ranking.json` só com o que muda. Regras antigas: `gtakit analyze --legacy`.

## Regras de medição de picos e tempo morto (`gtakit/analysis.py`, `gtakit/ff.py`; usadas pelo ranking e pelo `--legacy`)
- **Vídeo mudo** (`has_audio: false`): sem medição de áudio.
- **Picos de áudio**: volume RMS em janelas de 0,5 s (`aresample=48000,asetnsamples=n=24000,astats=…:reset=1`).
  - Janelas abaixo de -60 dB (silêncio, inclusive `-inf`) contam como **-60 dB** no cálculo da mediana e nunca são pico.
  - **Pico** = janela ≥ **mediana + 6 dB**. Num vídeo quase todo mudo a mediana fica em -60 dB e o grito aparece. Não use média + desvio padrão: trechos mudos inflam o desvio e escondem gritos, e áudio constante gera picos falsos.
  - `reset` do `astats` conta *frames*, não amostras: por isso o `asetnsamples` fixa blocos de 0,5 s e `reset=1`.
- **Mudança de cena**: `select='gt(scene,0.4)'`.
- **Reação**: novo pico de áudio até 2 s depois de um pico ou mudança de cena.
- **Momento**: sinais a menos de 3 s entre si formam um momento.
- **Tempo morto:** trecho que está ao mesmo tempo em silêncio (−40 dB, ≥ 1 s) e com imagem parada (≥ 1 s), encostado no início ou no fim.
- **`peak_time`** (ranking): janela de volume mais alta dentro do corte; sem áudio, o maior movimento; nunca vazio. Usado pela thumbnail e pelos Shorts.
- No modo `--legacy`: corte de 10–30 s em volta dos picos (vídeos > 40 s) e vídeos até 40 s inteiros.

## Penalidades que só você vê
Tela de menu ou carregamento, HUD de stream cobrindo a ação, música com copyright evidente, conteúdo que é react/repost de outra página: registre em `judgments.json` (com motivo) ou reprove o vídeo no discovery.

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
      "score": 74,
      "legacy_score": 100,
      "signals": ["audio_peak", "scene_change", "reaction"],
      "peaks": [91.5, 92.0],
      "peak_time": 92.0,
      "summary": "Carro capota na rampa e o jogador grita",
      "language": null,
      "needs_translation": null,
      "selected": true,
      "ranking": {"criteria": {"viralidade": 90, "humor": 63, "reacao": 84, "contexto": 86, "qualidade": 85, "retencao": 83},
                  "final": 80.0, "humor_source": "medido", "justification": ["..."], "alerts": ["..."],
                  "duplicate_of": null, "recommended": {"start": 84.5, "end": 102.0, "duration_s": 17.5},
                  "selection_reason": "selecionado"}
    }
  ]
}
```
- `start`/`end`/`peak_time` em segundos (float), no tempo do **vídeo de origem**; `start ≤ peak_time ≤ end`.
- `source` é relativo à pasta do projeto.
- `language` e `needs_translation` ficam `null` aqui: a video-translator detecta o idioma e preenche.
- Considere também `viral_score` do `discovery.json`: em empate, prefira o momento do vídeo mais viral.

## Regras
- Os timestamps vêm das medições; não chute valores. Notas do Claude só com motivo, em `judgments.json`.
- No máximo 3 momentos por vídeo; duração alvo do compilado em `config/ranking.json` (`target_duration_s`, padrão 6 min). Avise se os selecionados somarem menos de 80% da meta (faltam vídeos).
