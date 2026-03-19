# Memgraph AI Query Interface

This project runs a Streamlit app that generates and executes Cypher queries against a Memgraph database using xAI models.

Main app file: `graph_display_v2.py`

## What This App Does

- Connects to Memgraph on `127.0.0.1:7687` (no auth by default in current code)
- Uses multiple xAI models to generate Cypher
- Uses a judge model to pick the best query
- Validates selected Cypher against schema
- Runs an EXPLAIN-based repair loop before execution
- Executes the final query and summarizes results

## Required Resources

## 1) Software

- Python 3.10+ (3.13 tested in this repo)
- Docker Desktop (or another Docker runtime)
- Memgraph container
- Internet access to call xAI API

## 2) Python Packages

Installed from `requirements.txt`:

- tabulate
- pandas
- openpyxl
- langchain-core
- langchain-openai
- langchain_community
- langchain_neo4j
- langchain-classic
- langchain-memgraph
- neo4j
- streamlit-agraph
- pymgclient
- streamlit
- streamlit_chat
- streamlit_chatbox

## 3) External Services

- xAI API account + API key
- Memgraph instance reachable at `127.0.0.1:7687`

## 4) Data

Optional local mock data folders are included under `AI_Mock_Data/`.

## Setup

## 1) Create and activate a virtual environment

```bash
cd /Users/davenportaw/Projects/create_data_model_esi
python3 -m venv .venvai
source .venvai/bin/activate
```

If you already have `.venvai`, just activate it.

## 2) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Start Memgraph (Docker)

Example:

```bash
docker run -d \
  --name memgraph_ai_test \
  -p 7687:7687 \
  memgraph/memgraph
```

If a container already exists, start it:

```bash
docker start memgraph_ai_test
```

## 4) Set environment variables

```bash
export AIX_MODELS="grok-code-fast-1,grok-4-fast,grok-3-mini-fast"
export AIX_JUDGE_MODEL="grok-4.20-beta-0309-reasoning"
export AIX_INSECURE_SSL=true
```

Notes:

- `AIX_INSECURE_SSL=true` is useful in corporate/self-signed TLS environments.
- The current code has `AIX_API_KEY` hardcoded in `graph_display_v2.py`. For security, move this to an environment variable and read with `os.getenv("AIX_API_KEY")`.

## 5) Run the app

```bash
streamlit run graph_display_v2.py --server.port 8501
```

Open the URL shown by Streamlit (usually `http://localhost:8501`).

## Verify It Is Working

1. Confirm Memgraph is reachable:

```bash
docker ps | grep memgraph
```

2. Submit a natural language query in the app.

3. Check tabs:
- `Cypher Code` should show judge-selected/validated/repaired Cypher
- `Results` should show model runs, judge notes, repair log, summary, and table

## Troubleshooting

- `CERTIFICATE_VERIFY_FAILED`:
  - Set `AIX_INSECURE_SSL=true`

- `No Cypher query was generated`:
  - Verify `AIX_MODELS` values are valid model names for your xAI account

- Memgraph connection error:
  - Ensure container is running and port `7687` is mapped

- Package build issues for `pymgclient`:
  - Install system build tools (Xcode command line tools on macOS)
  - Then reinstall requirements

## Recommended Security Cleanup

- Remove hardcoded API keys from source code
- Load secrets from environment variables or Streamlit secrets
- Add `.env` to `.gitignore` if used
