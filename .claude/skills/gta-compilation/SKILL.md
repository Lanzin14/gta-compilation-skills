---
name: gta-compilation
description: Comando único que produz um compilado de melhores momentos de GTA a partir de vídeos virais do Twitter/X — baixa, escolhe os momentos, legenda em PT-BR o que estiver em outro idioma, monta o vídeo e prepara a publicação no YouTube. Use quando o usuário pedir "faz um compilado", "compilado de GTA" ou mandar uma lista de links de vídeos de GTA.
---

# GTA Compilation (orquestrador)

Executa as 5 skills em ordem. Cada etapa lê o arquivo da anterior em `projects/<slug>/`.

| # | Skill | Gera |
|---|---|---|
| 1 | `gta-video-discovery` | `discovery.json`, `source/*.mp4` |
| 2 | `viral-moment-analyzer` | `moments.json` |
| 3 | `video-translator` | `subs/*.pt.srt` (só falas em outro idioma) |
| 4 | `video-editor` | `output/compilation.mp4`, `output/chapters.json` |
| 5 | `youtube-publisher` | `output/metadata.json`, `output/description.txt` |

## Antes de começar
1. Confirme que há **links de posts do X** (ou do YouTube). Sem links, explique que o X não permite busca automática gratuita e peça que o usuário cole os links dos posts (pode copiar da aba Mídia dos perfis).
2. Pergunte apenas o que faltar (uma vez, tudo junto):
   - tema/título provisório;
   - duração alvo (padrão: **6 min**). Vídeos do X rendem ~1 momento de ~20 s cada, então peça links suficientes: `links ≈ duração_alvo_s / 20 × 1,4` (6 min → ~25 links; a folga cobre descartes).
   - palavrões nas legendas: manter ou suavizar (padrão: suavizar).
3. Verifique as ferramentas: `ffmpeg -version`, `yt-dlp --version`, `whisper --help` (ou `faster-whisper`). Se algo faltar, peça autorização antes de instalar.

## Execução
Siga cada skill na ordem acima. Pontos de **parada obrigatória** (espere o usuário aprovar):
- **Após a etapa 1:** lista dos vídeos ordenados pela nota de viralidade, antes de baixar.
- **Após a etapa 2:** momentos escolhidos (vídeo, início–fim, motivo), antes de editar.
- **Após a etapa 5:** título, descrição e alertas de direitos autorais, antes de qualquer publicação.

As etapas 3 e 4 rodam sem parada, mas mostre uma amostra das legendas traduzidas.

## Se algo falhar
- Link que não baixa: siga sem ele e liste no resumo final.
- Etapa que falha: pare, mostre o erro real e proponha a correção. Não pule etapas nem marque como concluído sem verificar o arquivo gerado.

## Resumo final
- Caminho do `compilation.mp4`, duração e resolução (via `ffprobe`).
- Quantos momentos, quantos legendados e de quais idiomas.
- Vídeos descartados ou com falha, e por quê.
- Lista de autores com `rights: unknown` (risco de Content ID/strike).
