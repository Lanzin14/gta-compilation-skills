# gta-compilation-skills

Skills do Claude Code que produzem compilados de GTA para o YouTube a partir de posts virais do Twitter/X.

## Estrutura
- `.claude/skills/<nome>/SKILL.md` — uma skill por etapa; `gta-compilation` orquestra todas.
- Fluxo: `gta-video-discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher` (+ `youtube-shorts`, opcional).
- `scripts/transcribe.py` — transcrição + detecção de idioma (faster-whisper, ou openai-whisper como reserva).
- Cada compilado vive em `projects/<slug>/` (ignorado pelo Git: contém vídeos e textos de terceiros).
- `tests/e2e_test.py` — teste ponta a ponta com vídeos sintéticos; roda no GitHub Actions a cada PR.
- `scripts/setup-windows.ps1` e `docs/INSTALACAO-WINDOWS.md` — instalação no Windows.

## Regras
- Responda e escreva em português (PT-BR).
- Ao mudar um comando ffmpeg ou uma regra (pontuação, cortes, capítulos) em um `SKILL.md`, atualize `tests/e2e_test.py` e rode `python3 tests/e2e_test.py` antes de commitar.
- O frontmatter de cada skill tem só `name` (igual ao nome da pasta) e `description` (≤ 1024 caracteres).
- Nunca faça upload no YouTube, nem raspe/automatize login no X. Nunca versione cookies ou arquivos de `projects/`.
- Não invente métricas, timestamps ou falas: use só o que vier do `yt-dlp`, `ffmpeg` ou Whisper.
