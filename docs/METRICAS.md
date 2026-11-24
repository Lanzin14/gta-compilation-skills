# Histórico e métricas

Tudo fica em `data/` na raiz do repositório (fora do Git): `data/history.jsonl` (um compilado por linha) e `data/permissions.json` (permissões).

## O que é gravado
- **Automaticamente no `gtakit render`:** projeto, tema, duração, clipes usados (post, autor, criador original, corte, nota), tempo de render, número de Shorts e se estava liberado para publicar.
- **Clipe repetido:** o `gtakit discovery` avisa quando um post já entrou num compilado anterior (`used_before` no `discovery.json`), e o ranking mostra o alerta. Repetir não é proibido — a decisão é sua.

## Depois de publicar (manual)
```bash
py -3 -m gtakit published projects/<slug> --url "https://youtu.be/<id>" --title "<título usado>"
```

## Métricas do YouTube (sem API, sem senha)
1. No **YouTube Studio**: Análises → **Modo avançado** → escolha o período → **Exportar** → *Valores separados por vírgula (.csv)*.
2. Descompacte e importe o arquivo `Tabela de dados.csv` (ou `Table data.csv`):
   ```bash
   py -3 -m gtakit metrics-import "C:\Users\<você>\Downloads\Tabela de dados.csv"
   py -3 -m gtakit report
   ```
- Lê o CSV em português ou inglês (colunas de visualizações, tempo de exibição, inscritos, impressões, CTR e duração média) e números como `1.234`, `38,5` e `0:01:23`.
- Cada linha é ligada ao compilado pelo ID do vídeo (do link registrado no `published`) ou, se não houver, pelo título. O que não for ligado é listado.
- O `report` mostra views, CTR e horas assistidas por compilado e a média de views dos compilados em que cada criador aparece — base para ajustar os pesos do ranking (`config/ranking.json`).

Os testes usam um histórico temporário (`GTAKIT_HISTORY`) e nunca tocam no `data/history.jsonl` real.
