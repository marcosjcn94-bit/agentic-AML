# Langfuse local — runbook dev (ADR-018)

Observabilidade **dev-only** do grafo LangGraph. **Não substitui `audit_events`** (DT-12, RF-11), que continua sendo a única fonte regulatória. Opt-in por variável de ambiente: sem `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`, o grafo roda idêntico a antes (ADR-018, "Decisão Selecionada").

## Pré-requisitos
- Docker Desktop rodando
- Porta `3000` livre em `localhost`
- Dependência instalada: `pip install -e ".[dev]"` (extra `dev` inclui `langfuse`)

## Subir o servidor (uma vez)

```bash
mkdir -p ~/dev/langfuse && cd ~/dev/langfuse
curl -L -o docker-compose.yml https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml
docker compose up -d
```

Primeira subida puxa ~2 GB de imagens. Verifique: `docker compose ps` deve mostrar `langfuse-web`, `langfuse-worker`, `db`, `clickhouse`, `redis`/`valkey`, `minio` saudáveis.

## Configurar credenciais

1. Abrir `http://localhost:3000` → criar conta **local** (o e-mail nunca sai da sua máquina).
2. Criar projeto: **`agentic-AML`**.
3. Settings → API Keys → Create new API keys → copiar `Public Key` (`pk-lf-...`) e `Secret Key` (`sk-lf-...`).
4. Exportar no shell **antes** de rodar a API ou os testes:

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=http://localhost:3000
```

## Usar

- `pytest -k e2e` — um trace por execução (`INVESTIGAR`, `PROPOR_ARQUIVAMENTO`)
- `python scripts/evaluate.py --ollama --sample-size 30` — um trace por alerta, navegável por alerta na UI
- `POST /alerts` com o servidor dev rodando — trace em tempo real

Na UI: escolher projeto `agentic-AML` → aba **Traces**. Cada trace mostra um span por nó (triage → investigation → retrieval → selection → reviewer → dossier), com latência, tokens (quando o LLM responde) e estado final.

## Desligar

```bash
unset LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY
```

O grafo volta a rodar sem nenhum overhead. O servidor pode ficar ligado; ninguém mais fala com ele.

## Parar o servidor

```bash
cd ~/dev/langfuse && docker compose down
```

Dados persistem em volume Docker. Para apagar tudo: `docker compose down -v`.

## Garantias

- **RNF-10:** nenhum dado sai de `localhost`. Verificável: desligue a rede Wi-Fi, rode `pytest -k e2e` com as env vars setadas — deve funcionar idêntico.
- **RNF-05 (canário):** o state do grafo só carrega tokens (`CPF_01`, `CONTA_01`) — nunca `CPF` real. O canário (`pytest -k canary`) continua cobrindo isso; o Langfuse é só mais um destino sanitizado.
- **PII no trace:** o handler é plugado em `graph/build.py::run_alert`, **depois** do nó `triage` — nunca vê `DT-01` cru.

## Troubleshooting

| Sintoma | Causa provável | Ação |
| :--- | :--- | :--- |
| `Connection refused` em `:3000` | Docker parado ou compose não subiu | `docker compose ps` em `~/dev/langfuse` |
| Trace não aparece | env vars não exportadas neste shell | `echo $LANGFUSE_PUBLIC_KEY` |
| `langfuse` import error | dependência não instalada | `pip install -e ".[dev]"` no repositório |
| Grafo lento | Langfuse **não** está no caminho crítico; overhead do handler < 5 ms localmente | se suspeitar, `unset` as env vars e re-rodar |
