# Identidade visual do canal

Configuração em `config/brand.json` (vale para todos os compilados) ou `projects/<slug>/brand.json` (só um compilado, com os campos que mudam). Implementado em `gtakit/brand.py` e `gtakit/render.py`.

**Enquanto `channel_handle` estiver vazio, a marca fica desligada** — sem marca d'água, abertura e tela final (o `gtakit render` avisa). Nada é inventado.

| Campo | Para quê | Padrão |
|---|---|---|
| `channel_handle` | @ do canal (o `@` é adicionado se faltar) | `null` (desligado) |
| `channel_name` | nome do canal (`{name}` nos textos) | `null` |
| `colors.accent` / `.text` / `.background` | cor dos textos da abertura/tela final, da marca d'água e do fundo | amarelo, branco, quase preto |
| `font_file` | fonte própria (`.ttf`/`.otf`) para a marca | fonte do sistema |
| `logo` | imagem (PNG com transparência) — caminho absoluto ou relativo à raiz do repositório | sem logo |
| `watermark` | marca d'água com o @: `position` (`bottom-right`, `bottom-left`, `top-left`), `opacity`, `size` | canto inferior direito, 65% |
| `intro` | abertura: `seconds`, `text` (`{handle}`, `{name}`, `\n` para quebrar linha) | 2,5 s, "COMPILADO POR @canal" |
| `outro` | tela final | 5 s, "INSCREVA-SE @canal" |
| `fps` | 30 ou 60 (gameplay fica mais fluido em 60; arquivo maior) | 30 |
| `audio_two_pass` | volume normalizado em 2 passadas (mede antes, aplica depois: mais preciso) | `true` |
| `transition` | `{"type": "fade", "seconds": 0.25}` escurece e volta entre clipes; `{"type": "none"}` desliga | fade 0,25 s |

## Onde aparece
- **Compilado:** abertura → clipes (crédito do criador no canto superior direito, marca d'água no canto escolhido, logo no canto oposto) → tela final.
- **Shorts:** marca d'água centralizada logo abaixo do crédito (longe dos botões do app); logo acima do vídeo.
- O crédito dos criadores **continua sempre** — a marca do canal não substitui o crédito nem a autorização de uso.

## Por que fade e não transição cruzada
O compilado é juntado **sem recodificar** (rápido e sem perda). O fade acontece dentro de cada clipe, então continua compatível. Uma transição cruzada (`xfade`) exigiria recodificar o vídeo inteiro.
