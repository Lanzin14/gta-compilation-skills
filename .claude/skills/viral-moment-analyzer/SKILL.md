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
1. **Picos de áudio** (gritos, explosões, risadas) — volume por janela de ~0,5 s:
   ```bash
   ffmpeg -i <video> -af "astats=metadata=1:reset=22050,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=audio_rms.txt" -f null -
   ```
   (`reset` = amostras por janela; 22050 ≈ 0,5 s em 44,1 kHz.) Marque janelas acima de média + 2 desvios padrão.
2. **Mudanças bruscas de cena** (batidas, quedas, explosões):
   ```bash
   ffmpeg -i <video> -vf "select='gt(scene,0.4)',showinfo" -f null - 2>&1 | grep pts_time
   ```
3. **Fala/reação**: se houver legenda/transcrição (video-translator), procure palavras de reação ("no way", "what", "kkkk", "caramba", palavrões).
4. Agrupe sinais que estejam a menos de 3 s entre si num mesmo **momento**.
5. Defina o corte: começa 3–5 s **antes** do pico (contexto) e termina 2–3 s **depois** (reação). Duração alvo: 8–30 s.
6. Pontue e ordene. Mostre os top momentos ao usuário (timestamps + motivo) para revisão antes da edição.

## Pontuação (0–100)
| Sinal | Peso |
|---|---|
| Pico de áudio forte | 30 |
| Mudança de cena / ação física | 25 |
| Reação falada / risada | 25 |
| Momento compreensível sem contexto externo | 20 |

Penalize (−20) trechos com tela de menu, carregamento, HUD de stream cobrindo a ação ou música com copyright evidente.

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
      "language": "en",
      "needs_translation": true,
      "selected": true
    }
  ]
}
```
- `start`/`end` em segundos (float).
- `needs_translation`: `true` quando há fala relevante em idioma ≠ `pt`.

## Regras
- Os timestamps vêm das medições; não chute valores. Se um sinal não pôde ser medido, omita-o de `signals`.
- No máximo 3 momentos por vídeo de origem, para variar o compilado.
- Duração total sugerida do compilado: 8–12 min (o usuário pode mudar).
