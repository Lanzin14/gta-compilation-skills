# Ranking inteligente de clipes

Implementado em `gtakit/ranking.py`; pesos e limites em `config/ranking.json`. Rodado pelo `gtakit analyze` (mede e ranqueia) e pelo `gtakit rank` (só ranqueia de novo, sem medir). O resultado vai para `moments.json` (campo `ranking` de cada momento) e para `ranking.md` (tabela legível).

## Fluxo

1. **Medir** cada vídeo uma vez (cache em `projects/<slug>/analysis/<id>.json`):
   - volume a cada 0,5 s (`astats`), mudanças de cena, tempo morto (silêncio + imagem parada);
   - movimento, brilho e nitidez a cada 0,5 s (`scdet`, `signalstats`, `blurdetect`);
   - volume integrado e pico real (`ebur128`);
   - "impressão digital" (dHash de 64 bits) de 2 quadros por segundo — para repetição e duplicados.
2. **Fala (opcional, recomendado):** `gtakit audio --full` + `scripts/transcribe.py` geram `subs/<id>.full.json`. Sem transcrição o humor e o contexto ficam menos precisos (o ranking avisa).
3. **Avaliação do Claude (opcional):** `judgments.json` com nota **e motivo** por critério. Sem motivo, é ignorada.
4. **Cortes recomendados** → **6 notas** → **nota final** → **duplicados** → **seleção**.

## Corte recomendado

- **Clipe de até 90 s** (`cut.whole_clip_max_s`): entra **inteiro**, só aparando tempo morto encostado no começo e no fim.
- **Mais longo:** um corte em volta de cada grupo de eventos (picos de volume, cortes de cena, risadas/reações na fala, picos de movimento):
  - começa `setup_s` (6 s) antes do 1º evento e **recua pela conversa contínua** que leva à ação (falas separadas por até `speech_gap_s`), até `max_setup_s` (25 s) antes — é isso que preserva a preparação de uma piada;
  - termina quando o volume volta ao normal por 1,5 s depois do último evento (até `reaction_tail_max_s`);
  - nunca começa nem termina **no meio de uma fala** (com transcrição);
  - duração entre `min_cut_s` (10 s, mínimo dos capítulos do YouTube) e `max_cut_s` (60 s);
  - cortes que se sobrepõem no mesmo vídeo são **fundidos** (é a mesma cena).
- **`peak_time`** (instante da ação, usado pela thumbnail e pelos Shorts): janela de volume mais alta dentro do corte; sem áudio, o maior movimento; nunca fica vazio.

## Os 6 critérios (0–100 cada)

| Critério | O que mede | Como |
|---|---|---|
| **Viralidade** | Alcance do **post** (não a qualidade do conteúdo) | Nota de viralidade do discovery (curtidas, reposts, comentários e velocidade). |
| **Humor** | Potencial cômico | Pistas no texto do post (`humor_words.post_funny`: 1 pista = 70, 2 = 85, 3+ = 100); risadas e reações na fala dentro do corte (densidade por 30 s); avaliação do Claude com motivo substitui. **Sem transcrição e sem pistas: 50 (neutro)** — falta de dado não vira nota baixa. |
| **Reação** | Intensidade da reação do streamer | **Variação** do volume (percentil 95 − mediana, de 3 a 15 dB) — não o volume absoluto, então áudio alto constante não conta como reação; + palavras de reação na fala; + nova reação até 2 s depois de outro evento. Vídeo mudo: 30 (não medido). |
| **Contexto** | Começo, desenvolvimento e conclusão | Preparação antes da ação (até `setup_s`), desfecho depois dela (≥ 2 s), corte sem interromper fala. |
| **Qualidade** | Clareza de áudio e vídeo | Resolução (lado menor: 1080 = 100, 720 = 85, 480 = 65), fps, imagem escura (brilho < 40), borrada (`blurdetect` > 12), sem áudio, áudio baixo (< −35 LUFS), estourado (pico ≥ −0,1 dBFS), quase todo em silêncio (≥ 60% abaixo de −50 dB). |
| **Retenção** | Potencial de segurar o espectador | Gancho (evento nos primeiros 3 s), duração (ideal 15–60 s), ritmo (movimento médio), **repetição** (quadros que repetem cenas ≥ 3 s antes: replay, loop, tela parada). |

**Nota final** = média ponderada pelos pesos de `weights` (padrão: humor 0,25; os outros 0,15).

## Duplicados e repetição

- **Duplicados entre vídeos** (o mesmo clipe repostado): duração parecida (≥ 75%) **e** imagem parecida (≥ 60% dos quadros com dHash a até 10 bits) **e** mesmo áudio (formato do volume com correlação ≥ 0,85; se os dois forem quase constantes, nível a até 2,5 dB). Um mudo e um com áudio só contam como iguais com ≥ 90% dos quadros e duração quase idêntica. Fica o de maior nota final (desempate: viralidade); o outro recebe `duplicate_of`.
- **Repetição dentro do clipe:** alerta quando ≥ 35% dos quadros repetem cenas anteriores.

## Seleção

Em ordem de nota final: fora se for **duplicado**, se a nota for menor que `min_final` (40), se já houver `max_per_video` (3) momentos do mesmo vídeo; depois da duração alvo (`target_duration_s`, 360 s) os demais ficam como **reserva**. Cada momento diz o motivo em `selection_reason`. **Ninguém é descartado só por não ter pico de volume.**

## Saída por momento (`moments.json` → `ranking`)

```json
{
 "criteria": {"viralidade": 96, "humor": 76, "reacao": 7, "contexto": 90, "qualidade": 55, "retencao": 46},
 "final": 63.1,
 "humor_source": "medido",
 "justification": ["viralidade 96 (...)", "texto do post indica humor (2 pista(s))"],
 "alerts": ["áudio estourado (pico no máximo)", "sem transcrição: humor estimado só pelo texto do post"],
 "duplicate_of": null,
 "recommended": {"start": 0.0, "end": 89.4, "duration_s": 89.4},
 "selection_reason": "selecionado"
}
```
O campo `score` do momento passa a ser a nota final arredondada (o resto do fluxo — ordem, thumbnail, Shorts — usa esse campo); `legacy_score` guarda a nota antiga.

## Ajustar

- Para todos os compilados: edite `config/ranking.json`.
- Só para um compilado: crie `projects/<slug>/ranking.json` só com o que muda (ex.: `{"weights": {"humor": 0.4}}`) e rode `gtakit rank`.
- Regras antigas (só picos de volume): `gtakit analyze --legacy`.

## Avaliação do Claude (`judgments.json`)

```json
{"<video_id>": {"humor": {"score": 90, "reason": "a física do carro capotando é absurda"},
                "contexto": {"score": 40, "reason": "a piada depende de algo que aconteceu antes do clipe"}}}
```
Use só com base no que viu (quadros, transcrição); a nota fica marcada como "avaliação do Claude" no relatório.
