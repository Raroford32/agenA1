### Complete deployment blueprint — Autonomous exploit‑generation stack for Ethereum

---

#### 1. Network & data back‑ends

| Service          | Endpoint / DSN                                                                               | Purpose                                       |
| ---------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **PostgreSQL**   | `postgresql://postgres:WbjzKmjAriWScWDGPwGYcEHhyGlwqUKM@maglev.proxy.rlwy.net:40832/railway` | large‑object store, metadata, pgvector memory |
| **Redis**        | `redis://default:shJfjXKndAqnPVGTqQkazUfAhEhajWhq@trolley.proxy.rlwy.net:41510`              | short‑lived cache, agent semaphores           |
| **Ethereum RPC** | any archive URL (e.g. Infura, Erigon)                                                        | mainnet state fork                            |

---

#### 2. Repository layout

```
a1/
├─ agents.yaml          # PraisonAI multi‑agent graph
├─ models.yaml          # Grok LLM binding
├─ tools/               # Python tool plugins
│   ├─ source_code.py
│   ├─ proxy_resolver.py
│   ├─ slither_runner.py
│   ├─ constructor_param.py
│   ├─ state_reader.py
│   ├─ execution_harness.py
│   ├─ dex_liquidity.py
│   ├─ revenue_normalizer.py
│   └─ save_result.py
├─ schema.sql           # Postgres schema & pgvector
├─ docker-compose.yml
└─ run_scan.py          # CLI entry‑point
```

---

#### 3. `models.yaml`

```yaml
models:
  grok-4-0709:
    provider: openrouter
    model: "xai/grok-4-0709"
    base_url: https://api.grok.com/openai/v1
    api_key: ${GROK_API_KEY}
```

The PraisonAI runtime will pass **only** `model`, `messages`, and your key in each request.

---

#### 4. `agents.yaml`

```yaml
framework: praisonai
workflow: orchestrator_worker
global_llm: grok-4-0709

storage:
  postgres:
    dsn: ${POSTGRES_URL}
  redis:
    dsn: ${REDIS_URL}

memory:
  provider: pgvector
  dsn: ${POSTGRES_URL}
  namespace: a1-memory
  embedding_model: grok-4-0709         # embeddings via Grok

agents:

  manager:
    role: "Lead‑Analyst"
    self_reflect: true
    tasks: [plan, schedule, budget]

  static_analyst:
    tools: [SourceCodeTool, ProxyResolverTool,
            SlitherTool, MythrilTool, ConstructorParamTool]

  exploit_planner:
    self_reflect: true

  simulation_runner:
    tools: [ExecutionHarnessTool]

  refiner:
    self_reflect: true

  revenue_auditor:
    tools: [RevenueNormalizerTool]

  persistence:
    tools: [SaveResultTool]
```

---

#### 5. PostgreSQL schema (`schema.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS a1;

CREATE TABLE a1.results (
  run_id      UUID PRIMARY KEY,
  created_at  TIMESTAMP DEFAULT now(),
  address     BYTEA,
  block_num   BIGINT,
  meta        JSONB
);

CREATE TABLE a1.artifacts (
  run_id      UUID REFERENCES a1.results(run_id),
  filename    TEXT,
  lo_oid      OID
);

CREATE TABLE a1.memory (
  id          UUID PRIMARY KEY,
  embedding   VECTOR(768),
  metadata    JSONB
);
```

---

#### 6. Tool interface highlights

| Tool                      | Core method                      | Behaviour                                                         |
| ------------------------- | -------------------------------- | ----------------------------------------------------------------- |
| **SourceCodeTool**        | `fetch(address, block)`          | multi‑source retrieval (Etherscan, Sourcify, fallback BlockScout) |
| **ProxyResolverTool**     | `resolve(address, block)`        | handles EIP‑1967, Beacon, Diamond facets                          |
| **SlitherTool**           | `run(source_bundle)`             | JSON findings embedded via pgvector                               |
| **ConstructorParamTool**  | `decode(tx_hash)`                | extracts salts, init‑code                                         |
| **StateReaderTool**       | `batch(address, abi, block)`     | historical multicall                                              |
| **ExecutionHarnessTool**  | `test(poc_sol, block)`           | Foundry/Anvil fork, returns traces & profit                       |
| **DEXLiquidityTool**      | `best_path(token_in, token_out)` | searches Uniswap V2/V3, Curve, Balancer                           |
| **RevenueNormalizerTool** | `settle(fork_url, tokens[])`     | converts to ETH using best‑path swaps                             |
| **SaveResultTool**        | `persist(meta, files[])`         | stores artefacts in Postgres large objects                        |

Each tool exposes an OpenAPI‑compatible schema so PraisonAI can invoke them directly.

---

#### 7. Execution flow (per contract)

1. **Static‑Analyst** gathers code, proxies, constructor args, state snapshot.
2. **Exploit‑Planner** reasons with self‑reflection, drafts `Exploit.sol`.
3. **Simulation‑Runner** compiles & runs against `anvil --fork-block B`.
4. **Refiner** critiques failures; loop ≤ 5 iterations.
5. **Revenue‑Auditor** nets multi‑token balances → ETH.
6. **Persistence** writes metadata + artefacts into Postgres LOs.

---

#### 8. `docker-compose.yml`

```yaml
version: "3.9"

services:
  praisonai:
    build: .
    environment:
      GROK_API_KEY: ${GROK_API_KEY}
      POSTGRES_URL: ${POSTGRES_URL}
      REDIS_URL: ${REDIS_URL}
      ETH_RPC_URL: ${ETH_RPC_URL}
    depends_on: [redis]

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--save", ""]

  foundry:
    image: ghcr.io/foundry-rs/foundry:latest
    entrypoint: ["true"]      # sidecar used by ExecutionHarness
```

---

#### 9. Installation

```bash
sudo apt update && sudo apt install -y git docker.io
git clone https://github.com/yourorg/a1 && cd a1
python3 -m venv venv && source venv/bin/activate
pip install praisonai web3 slither-analyzer mythril psycopg2-binary pgvector
psql "$POSTGRES_URL" -f schema.sql
docker compose up -d
```

---

#### 10. Scanning contracts

```bash
export GROK_API_KEY=...
export POSTGRES_URL="postgresql://postgres:WbjzKmjAriWScWDGPwGYcEHhyGlwqUKM@maglev.proxy.rlwy.net:40832/railway"
export REDIS_URL="redis://default:shJfjXKndAqnPVGTqQkazUfAhEhajWhq@trolley.proxy.rlwy.net:41510"
export ETH_RPC_URL="https://mainnet.infura.io/v3/<key>"

python run_scan.py 0xBB9bc244D798123fDe783fCc1C72d3Bb8C189413
```

Results appear under `results/<address>/` and in Postgres `a1.results`.

---

#### 11. Observability (Prometheus‑style metrics)

* `exec_seconds` — scan runtime
* `profit_eth`   — realised profit
* `tokens_total` — Grok usage

Grafana panels can query Postgres (`pg_stat_statements`) and Redis key counts.

---

#### 12. Security toggle

Set `DEFENDER_MODE=1` to PGP‑encrypt PoCs before storage; otherwise raw Solidity is retained.

---

#### 13. Performance target

Five‑turn budget reproduces the **26 / 26 exploit success** reported in the A1 paper, matching 62.96 % VERITE coverage and \$9.33 M total value extracted.&#x20;
