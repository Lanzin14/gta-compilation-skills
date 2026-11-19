# gta-compilation-skills

Skills do Claude Code para produzir compilados de GTA para o YouTube.

## Fluxo
```
gta-video-discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher
   discovery.json        moments.json          subs/*.pt.srt     compilation.mp4    metadata.json
```

| Skill | Função |
|---|---|
| `gta-video-discovery` | Encontrar e classificar vídeos |
| `viral-moment-analyzer` | Identificar os melhores momentos |
| `video-translator` | Transcrever e traduzir legendas |
| `video-editor` | Montar o compilado |
| `youtube-publisher` | Título, descrição e metadados |

Os arquivos de cada compilado ficam em `projects/<slug>/`.

## Requisitos
- `ffmpeg`
- `yt-dlp` (`pip install yt-dlp`)
- Whisper (`pip install openai-whisper`)

## Uso
Abra o repositório no Claude Code e peça, por exemplo: "crie um compilado de fails de GTA RP".

## Direitos autorais
Sempre credite os criadores e, de preferência, peça permissão. Vídeos de terceiros podem gerar Content ID ou strike.
