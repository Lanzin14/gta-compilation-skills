---
name: gta-compilation
description: Comando único que produz um compilado de melhores momentos de GTA a partir de vídeos virais do Twitter/X — baixa, escolhe os momentos, legenda em PT-BR o que estiver em outro idioma, monta o vídeo e prepara a publicação no YouTube. Use quando o usuário pedir "faz um compilado", "compilado de GTA" ou mandar uma lista de links de vídeos de GTA.
---

# GTA Compilation (orquestrador)

Executa as skills em ordem. Cada etapa lê o arquivo da anterior em `projects/<slug>/`.

## Ferramenta: `gtakit`
As partes automáticas de cada etapa rodam pela linha de comando do pacote `gtakit/` (só Python + ffmpeg), sempre a partir da **raiz do repositório**:
```bash
py -3 -m gtakit <comando> projects/<slug>      # Windows
python3 -m gtakit <comando> projects/<slug>    # Linux/macOS
```
`init → discovery → approve → probe → analyze → audio → render → thumbnail → shorts`, mais `validate` (confere os JSON entre etapas) e `status` (o que já foi feito). O `--help` de cada comando explica as opções.
- **Retomar um compilado:** rode `status` e continue da primeira etapa não concluída.
- **Antes de cada etapa que lê arquivos de outra**, rode `validate`; se apontar problema, corrija antes de seguir.
- As decisões (o que aprovar, o que é engraçado, a tradução, títulos) continuam sendo suas e do usuário; o `gtakit` só mede, corta e monta.

| # | Skill | Gera |
|---|---|---|
| 1 | `gta-video-discovery` | `discovery.json`, `source/*.mp4` |
| 2 | `viral-moment-analyzer` | `moments.json` |
| 3 | `video-translator` | `subs/*.pt.srt` (só falas em outro idioma) |
| 4 | `video-editor` | `output/compilation.mp4`, `output/chapters.json` |
| 5 | `youtube-publisher` | `output/metadata.json`, `output/description.txt` |
| 6 | `youtube-shorts` *(opcional)* | `output/shorts/*.mp4`, `output/shorts/shorts.json` |

## Antes de começar
1. Confirme que há **links de posts do X** (ou do YouTube). Sem links, explique que o X não permite busca automática gratuita e peça que o usuário cole os links dos posts (pode copiar da aba Mídia dos perfis).
2. Pergunte apenas o que faltar (uma vez, tudo junto):
   - tema/título provisório;
   - duração alvo (padrão: **6 min**). Vídeos do X rendem ~1 momento de ~20 s cada, então peça links suficientes: `links ≈ duração_alvo_s / 20 × 1,4` (6 min → ~25 links; a folga cobre descartes).
   - palavrões nas legendas: manter ou suavizar (padrão: suavizar);
   - gerar Shorts dos melhores momentos (padrão: sim, 3 Shorts).
3. Verifique as ferramentas: `ffmpeg -version`, `yt-dlp --version`, `whisper --help` (ou `faster-whisper`). Se algo faltar, peça autorização antes de instalar.
4. Crie o projeto: `py -3 -m gtakit init projects/<slug> --theme "<tema>"` (slug = tema em kebab-case + data `AAAAMMDD`).

## Execução
Siga cada skill na ordem acima. Pontos de **parada obrigatória** (espere o usuário aprovar):
- **Após a etapa 1:** lista dos vídeos ordenados pela nota de viralidade, antes de baixar. Em seguida, entregue `permissions.md` com as mensagens de pedido de permissão para o usuário enviar.
- **Após a etapa 2:** momentos escolhidos (vídeo, início–fim, motivo), antes de editar.
- **Após a etapa 5:** título, texto e imagem da thumbnail, descrição e o resultado do `gtakit ready` (quem ainda não autorizou), antes de qualquer publicação. Créditos não substituem autorização; aceitar o risco é decisão **explícita** do usuário (`--accept-risk`).

As etapas 3 e 4 rodam sem parada, mas mostre uma amostra das legendas traduzidas.

## Se algo falhar
- Link que não baixa: siga sem ele e liste no resumo final.
- Etapa que falha: pare, mostre o erro real e proponha a correção. Não pule etapas nem marque como concluído sem verificar o arquivo gerado.

## Resumo final
- Caminho do `compilation.mp4`, duração e resolução (via `ffprobe`).
- Quantos momentos, quantos legendados e de quais idiomas.
- Vídeos descartados ou com falha, e por quê.
- Shorts gerados: quantos, caminho de cada um em `output/shorts/` e o título proposto (de `shorts.json`).
- Resultado do `gtakit ready`: pronto ou bloqueado, e quem ainda não autorizou (risco de Content ID/strike).
