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
| `viral-moment-analyzer` | Ranquear os clipes por 6 critérios e escolher os melhores momentos ([como funciona](docs/RANKING.md)) |
| `video-translator` | Detectar idioma e legendar em PT-BR |
| `video-editor` | Montar o compilado |
| `youtube-publisher` | Título, descrição, thumbnail e metadados |
| `youtube-shorts` | Shorts verticais (1080x1920, até 60 s) dos melhores momentos |

Os arquivos de cada compilado ficam em `projects/<slug>/`. A execução de cada etapa fica no pacote `gtakit/` (`py -3 -m gtakit --help`); as skills dizem ao Claude o que decidir e quando chamar cada comando.

## Marca do canal
Preencha `channel_handle` (e, se quiser, `logo`, cores e `fps: 60`) em `config/brand.json` para ter abertura, marca d'água, logo e tela final. Detalhes em [`docs/MARCA.md`](docs/MARCA.md).

## Histórico e métricas
Cada compilado fica registrado em `data/history.jsonl` (clipes usados, duração, link do YouTube). Importe o CSV do YouTube Studio com `gtakit metrics-import` e veja `gtakit report`. Detalhes em [`docs/METRICAS.md`](docs/METRICAS.md).

## Requisitos
- `ffmpeg`
- `yt-dlp` (`pip install yt-dlp`)
- Whisper (`pip install openai-whisper`) e, opcional e mais rápido, `faster-whisper`
- Python 3.12 ou mais novo (o `gtakit` só usa a biblioteca padrão)

**Windows:** rode `scripts\setup-windows.ps1` e siga o checklist em [`docs/INSTALACAO-WINDOWS.md`](docs/INSTALACAO-WINDOWS.md).

## Uso
Abra o repositório no Claude Code, cole os links dos posts do X com vídeos de GTA e peça: "faz um compilado de melhores momentos".

> O X não permite busca automática gratuita: o `yt-dlp` baixa posts individuais, então os links precisam ser enviados (copie da aba Mídia dos perfis). Posts sensíveis/protegidos exigem cookies do seu navegador (`--cookies`), que nunca devem ir para o repositório.

## Testes
`python3 -m unittest discover -s tests -p "test_*.py"` (testes de unidade) e `python3 tests/e2e_test.py` (fluxo inteiro com vídeos sintéticos, sem rede do X e sem Whisper: confere vídeo, áudio, legendas, capítulos, créditos, thumbnail e Shorts). Roda automaticamente no GitHub Actions a cada PR, em Linux e Windows (no Windows também valida e executa `scripts/setup-windows.ps1`).

## Direitos autorais
Créditos e marca d'água **não** substituem autorização. O `gtakit` mantém um registro local de permissões (`data/permissions.json`, fora do Git), gera as mensagens de pedido (`gtakit permissions`) e **bloqueia** a marcação de "pronto para publicar" (`gtakit ready`) enquanto o dono de algum conteúdo usado não tiver autorizado — a menos que você aceite o risco explicitamente (`--accept-risk "motivo"`, que fica registrado). Vídeos de terceiros sem permissão podem gerar Content ID ou strike.
