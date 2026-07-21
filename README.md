# git-deploy-schedule

Automated git commit scheduler with AI-generated commit messages. Commits randomised sample files to a target repository at configurable intervals using a local Ollama model — no external AI API required.

A web dashboard lets you monitor activity, manage credentials, and trigger commits on demand.

---

## How it works

1. On each cycle (default 10 min ± 50 s jitter) the scheduler generates 1–3 random YAML files (travel destinations or Kubernetes manifests) in the target repo
2. Ollama generates a conventional commit message from the diff (`feat`, `fix`, `chore`, etc.)
3. The commit is pushed to GitHub via a stored PAT
4. Everything is tracked in SQLite and surfaced in the web UI

---

## Quick start (Docker)

```bash
git clone https://github.com/justynroberts/git-deploy-schedule.git
cd git-deploy-schedule
cp .env.example .env
```

Edit `.env`:

```env
REPO_REMOTE_URL=https://github.com/your-org/your-repo.git
REPO_BRANCH=main
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2:3b
```

```bash
docker-compose up -d
```

Open **http://localhost:5001** — paste a GitHub PAT in Settings → GitHub Token → Save.

---

## Requirements

| Dependency | Notes |
|---|---|
| Docker + Docker Compose | Primary deployment method |
| Ollama | Run locally; any model works (`llama3.2:3b` recommended) |
| GitHub PAT | `repo` scope (classic) or Contents: Write (fine-grained) |

---

## Configuration

### `config/config.yaml`

```yaml
repositories:
  - path: /repo          # mounted inside container
    branch: main
    enabled: true

schedule:
  base_interval: 600     # seconds between commits
  jitter_range: 50       # ± seconds of randomness

ollama:
  enabled: true
  url: http://host.docker.internal:11434
  model: llama3.2:3b
  timeout: 30
  theme: "Kubernetes microservices platform"   # shapes commit message context

commit:
  use_ollama: true

push:
  enabled: true
  retry_attempts: 3
  retry_delay: 30

logging:
  level: INFO
  file: logs/scheduler.log
```

### Environment overrides (`docker-compose.yml` or `.env`)

| Variable | Default | Description |
|---|---|---|
| `REPO_REMOTE_URL` | — | Remote to clone and push to |
| `REPO_BRANCH` | `main` | Branch to commit on |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model for commit messages |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `GITHUB_TOKEN` | — | Optional: PAT passed at container start |

---

## Web UI

Port **5001** (configurable).

- **Dashboard** — live countdown to next commit, last commit, push health
- **Commit history** — every commit with push status badge
- **Controls** — pause / resume / trigger now
- **Settings** — PAT management, branch, remote URL (all persisted in SQLite)

---

## GitHub Actions + PagerDuty change integration

Create `.github/workflows/pagerduty-change.yml` in the **target repository**:

```yaml
name: PagerDuty Change Event

on:
  push:
    branches: [main, master]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Send change event to PagerDuty
        env:
          PD_ROUTING_KEY: ${{ secrets.PD_CHANGE_INTEGRATION_KEY }}
        run: |
          COMMIT_SHA="${{ github.sha }}"
          COMMIT_MSG=$(git log -1 --pretty=%s)
          AUTHOR=$(git log -1 --pretty=%an)
          REPO="${{ github.repository }}"
          RUN_URL="https://github.com/${REPO}/commit/${COMMIT_SHA}"

          curl -s --fail -X POST https://events.pagerduty.com/v2/change/enqueue \
            -H "Content-Type: application/json" \
            -d "{
              \"routing_key\": \"${PD_ROUTING_KEY}\",
              \"payload\": {
                \"summary\": \"${COMMIT_MSG}\",
                \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
                \"source\": \"github-actions\",
                \"custom_details\": {
                  \"repository\": \"${REPO}\",
                  \"commit\": \"${COMMIT_SHA:0:7}\",
                  \"author\": \"${AUTHOR}\",
                  \"compare_url\": \"${RUN_URL}\"
                }
              },
              \"links\": [{
                \"href\": \"${RUN_URL}\",
                \"text\": \"View commit\"
              }]
            }"
```

### Setup

1. In PagerDuty: **Service** → **Integrations** → **Add integration** → choose **Change Events API** → copy the **Integration Key**
2. In GitHub: **Settings** → **Secrets and variables** → **Actions** → add `PD_CHANGE_INTEGRATION_KEY`
3. Commit the workflow file to your target repo

Every push from the scheduler will create a change event visible in PagerDuty's Recent Changes timeline — useful for correlating deploys with incidents.

---

## Project structure

```
git-deploy-schedule/
├── src/
│   ├── scheduler.py          # Orchestrates commit cycles
│   ├── git_operations.py     # Git wrapper (stage / commit / push)
│   ├── file_generator.py     # Generates random YAML sample files
│   ├── ollama_client.py      # Ollama API client
│   ├── message_generator.py  # Commit message generation + fallback
│   ├── database.py           # SQLite: commits, stats, settings
│   ├── api.py                # FastAPI REST API
│   └── config.py             # YAML + env config loader
├── web/frontend/             # Dashboard (HTML/CSS/JS)
├── config/config.yaml        # Default configuration
├── main.py                   # CLI entry point
├── main_web.py               # Web UI entry point
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh             # Clones target repo on first start
└── requirements.txt
```

---

## Running without Docker

```bash
pip install -r requirements.txt

# CLI mode (headless)
python main.py

# Web UI mode
python main_web.py --port 5001

# Single commit (testing)
python main.py --once
```

---

## Token security

The GitHub PAT is stored in the SQLite database (`database/scheduler.db`), never in a file or environment variable at rest. The `database/` directory is excluded from the target repo via `.gitignore`. Tokens are only held in memory during push operations.

---

## License

MIT
