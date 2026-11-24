# gta-compilation-skills

Skills do Claude Code que produzem compilados de GTA para o YouTube a partir de posts virais do Twitter/X.

## Estrutura
- `.claude/skills/<nome>/SKILL.md` — uma skill por etapa; `gta-compilation` orquestra todas. As skills descrevem **o que decidir**; a execução fica no `gtakit`.
- `gtakit/` — pacote Python (só stdlib + ffmpeg) com a lógica de cada etapa e a linha de comando `py -3 -m gtakit <comando> projects/<slug>` (rode da raiz do repositório).
- Fluxo: `gta-video-discovery → viral-moment-analyzer → video-translator → video-editor → youtube-publisher` (+ `youtube-shorts`, opcional).
- `scripts/transcribe.py` — transcrição + detecção de idioma (faster-whisper, ou openai-whisper como reserva).
- Marca do canal: `config/brand.json` (`docs/MARCA.md`); sem `channel_handle`, a marca fica desligada — nunca invente o nome do canal.
- Ranking de clipes: `gtakit/ranking.py`, pesos/limites em `config/ranking.json`, documentação em `docs/RANKING.md` (mudou um número ou regra, atualize o doc e `tests/test_ranking.py`).
- Histórico e métricas: `gtakit/history.py`, `data/history.jsonl` (fora do Git), CSV do YouTube Studio via `metrics-import` (`docs/METRICAS.md`). Testes usam `GTAKIT_HISTORY` temporário — nunca o histórico real.
- Cada compilado vive em `projects/<slug>/` (ignorado pelo Git: contém vídeos e textos de terceiros).
- `tests/test_gtakit.py` — testes de unidade (funções puras, sem ffmpeg).
- `tests/e2e_test.py` — teste ponta a ponta com vídeos sintéticos, pela linha de comando do gtakit; roda no GitHub Actions a cada PR (Linux e Windows).
- `scripts/setup-windows.ps1` e `docs/INSTALACAO-WINDOWS.md` — instalação no Windows.

## Regras
- Responda e escreva em português (PT-BR).
- Regras e comandos ffmpeg vivem no `gtakit/`. Ao mudar uma regra: altere o `gtakit/`, atualize a descrição no `SKILL.md`, adicione/ajuste testes e rode antes de commitar:
  `python3 -m unittest discover -s tests -p "test_*.py"` e `python3 tests/e2e_test.py`.
- Contratos entre etapas (campos obrigatórios dos JSON) ficam em `gtakit/project.py` (`SCHEMAS`); mudou um campo, atualize lá.
- `gtakit` não pode depender de pacotes fora da biblioteca padrão sem necessidade comprovada (precisa instalar fácil no Windows).
- O frontmatter de cada skill tem só `name` (igual ao nome da pasta) e `description` (≤ 1024 caracteres).
- Nunca faça upload no YouTube, nem raspe/automatize login no X. Nunca versione cookies ou arquivos de `projects/`.
- Não invente métricas, timestamps ou falas: use só o que vier do `yt-dlp`, `ffmpeg` ou Whisper.
- Créditos e marca d'água **não** substituem autorização de uso. Nunca use `gtakit ready --accept-risk` sem o usuário pedir explicitamente. O registro de permissões fica em `data/` (fora do Git).
