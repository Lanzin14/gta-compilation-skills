# Instalação no Windows e primeiro uso

## 1. Instalar as ferramentas

Abra o **PowerShell** na pasta do repositório e rode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

O script verifica cada ferramenta e só instala o que falta:

| Ferramenta | Para quê | Como é instalada |
|---|---|---|
| Git | Exigido pelo Claude Code no Windows | `winget` (`Git.Git`) |
| Python 3.12 | Roda yt-dlp e Whisper | `winget` (`Python.Python.3.12`) |
| FFmpeg | Cortar, legendar e juntar os vídeos | `winget` (`Gyan.FFmpeg`) |
| yt-dlp | Baixar os vídeos do X | `pip` |
| Whisper | Detectar idioma e transcrever | `pip` (instala também o PyTorch, alguns GB) |
| faster-whisper | Transcrição várias vezes mais rápida (opcional; se não instalar, usa o Whisper acima) | `pip` |

- Sem o Whisper (para economizar espaço): adicione `-SkipWhisper`.
- Se aparecer "ainda não está no PATH": feche e abra o terminal e rode o script de novo.
- O `winget` vem no Windows 10/11 pelo app **Instalador de Aplicativo** (Microsoft Store).

Depois instale o **Claude Code** seguindo a documentação oficial (https://code.claude.com/docs) e abra-o dentro da pasta do repositório.

## 2. Checklist do primeiro uso (teste pequeno)

Faça um teste com **3 links** antes de um compilado de verdade:

- [ ] **Teste automático:** `py -3 tests\e2e_test.py` termina com `TODOS OS TESTES PASSARAM`.
- [ ] **Download:** cole 3 links de posts do X com vídeo de GTA e peça "faz um compilado de teste com esses links". Confira que os vídeos aparecem em `projects\<slug>\source\`.
  - Erro de login/NSFW: exporte os cookies do seu navegador para um arquivo (ex.: `x-cookies.txt`) **fora do repositório** e passe o caminho quando pedido.
- [ ] **Métricas:** a tabela mostra curtidas/reposts reais (compare com o post no X).
- [ ] **Momentos:** os trechos sugeridos são realmente os melhores. Se a detecção errar muito (música alta do jogo), anote — a regra de pico (+6 dB) pode precisar de ajuste.
- [ ] **Legenda:** um vídeo em inglês recebe legenda PT-BR no tempo certo; um em português não recebe.
- [ ] **Crédito:** o `@autor` aparece no canto. Se der `Cannot find a valid font`, a skill `video-editor` explica como indicar a fonte (`C:/Windows/Fonts/arial.ttf`).
- [ ] **Vídeo final:** `projects\<slug>\output\compilation.mp4` abre, com som em todos os trechos.
- [ ] **Shorts:** `projects\<slug>\output\shorts\` tem os vídeos verticais; abra um no celular e confira legenda e `@autor` legíveis.
- [ ] **Publicação:** título, descrição, capítulos e créditos fazem sentido. O envio ao YouTube é manual.

Anote o que falhar e traga para o Claude Code: os ajustes entram nas skills e no `tests\e2e_test.py`.
