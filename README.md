# gta-compilation-skills

Skills do Claude Code para produzir compilados dos vídeos de GTA mais virais do Twitter/X, com legenda PT-BR quando a fala for em outro idioma.

## Fluxo
Comando único: skill `gta-compilation` ("faz um compilado de GTA com esses links").

```
gta-video-discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher
   discovery.json        moments.json          subs/*.pt.srt     compilation.mp4    metadata.json
```

| Skill | Função |
|---|---|
| `gta-compilation` | Orquestra todas as etapas |
| `gta-video-discovery` | Baixar vídeos do X e ordenar por viralidade |
| `viral-moment-analyzer` | Identificar os melhores momentos |
| `video-translator` | Detectar idioma e legendar em PT-BR |
| `video-editor` | Montar o compilado |
| `youtube-publisher` | Título, descrição e metadados |

Os arquivos de cada compilado ficam em `projects/<slug>/`.

## Requisitos
- `ffmpeg`
- `yt-dlp` (`pip install yt-dlp`)
- Whisper (`pip install openai-whisper`)

## Uso
Abra o repositório no Claude Code, cole os links dos posts do X com vídeos de GTA e peça: "faz um compilado de melhores momentos".

> O X não permite busca automática gratuita: o `yt-dlp` baixa posts individuais, então os links precisam ser enviados (copie da aba Mídia dos perfis). Posts sensíveis/protegidos exigem cookies do seu navegador (`--cookies`), que nunca devem ir para o repositório.

## Direitos autorais
Sempre credite os criadores e, de preferência, peça permissão. Vídeos de terceiros podem gerar Content ID ou strike.
