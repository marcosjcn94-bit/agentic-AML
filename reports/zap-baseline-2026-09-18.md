# ZAP baseline — 2026-09-18

Execução: imagem `zaproxy/zap-stable:latest` via Docker, contra a API local em
`http://host.docker.internal:8000`, sem autenticação e sem dados pessoais.

Resultado do baseline:

- 66 verificações aprovadas;
- 0 falhas (`FAIL-NEW: 0`);
- 1 alerta informativo (`WARN-NEW: 1`): conteúdo cacheável em `robots.txt` e
  `sitemap.xml`, ambos retornando 404. Esses endpoints não existem na API e não
  expõem conteúdo sensível.

Arquivos brutos gerados localmente: `zap-baseline.html` e `zap-baseline.json`.
