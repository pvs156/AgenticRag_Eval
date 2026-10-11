# Deploying the stack

Everything runs on one small Linux VM with Docker Compose. Only Caddy is reachable from the internet (ports 80/443); the API, Qdrant, Prometheus and Grafana stay on the internal Docker network. Grafana is served at `/grafana` behind its own login.

```
internet ──443──▶ Caddy ──▶ web (Next.js) ──▶ api (FastAPI + agent) ──▶ qdrant
                     └──/grafana──▶ grafana ◀── prometheus ◀── api /metrics, node-exporter
api ──▶ LLM provider (hosted free tier)      api ──▶ Langfuse cloud (traces, scores)
```

## Costs (target: $0 to $10)

| Item | Choice | Cost |
|---|---|---|
| VM | Oracle Cloud Always Free (Ampere A1), or a ~$5/month VPS with at least 4 GB RAM | $0 or ~$5/mo |
| LLM | Hosted free tier (for example Groq or Gemini), set in `.env` | $0 within limits |
| Judge LLM for nightly evals | Same free tier, or a cheap paid model with `JUDGE_BUDGET_USD` | $0 to $5 |
| Tracing | Langfuse cloud Hobby tier | $0 |
| TLS | Let's Encrypt via Caddy | $0 |
| Domain | Optional. Without one, use the VM IP with `sslip.io`, e.g. `203-0-113-7.sslip.io` | $0 |
| CI/CD and registry | GitHub Actions and GHCR (public repo) | $0 |

Check each provider's current free-tier terms when you sign up; they change.

## First deployment

1. **Create the VM.** Use Ubuntu 24.04 with at least 4 GB RAM (the embedding and rerank models need about 1 GB) and open ports 22, 80 and 443 in the cloud firewall.
2. **Bootstrap it:**
   ```bash
   ssh ubuntu@<vm-ip>
   git clone https://github.com/<you>/dispute-assistant.git && cd dispute-assistant
   ./deploy/scripts/bootstrap-vm.sh && exit      # log in again afterwards
   ```
   The script installs Docker, sets up the firewall, disables SSH passwords, turns on unattended upgrades and adds 2 GB of swap.
3. **Configure** `~/dispute-assistant/.env` (start from `.env.example`):
   - `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` for a hosted free tier
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
   - `DEMO_TOKEN`, `INTERVIEWER_TOKEN`: long random strings (`openssl rand -hex 24`)
   - `SITE_ADDRESS`: your domain, or `<ip-with-dashes>.sslip.io`
   - `GRAFANA_ADMIN_PASSWORD`

   Then `chmod 600 .env`.
4. **Start the stack.** Either pull the images CI pushed:
   ```bash
   echo 'export GHCR_OWNER=<your-github-user-lowercase>' >> ~/.bashrc && source ~/.bashrc
   ./deploy/scripts/release.sh latest
   ```
   Or build on the VM: `docker compose up -d --build`.
5. **Verify** each of these:
   - `https://<site>/` loads the chat.
   - `https://<site>/interviewer?token=<INTERVIEWER_TOKEN>` shows the trace links and agent steps.
   - `https://<site>/grafana` shows the dashboard.
   - A chat turn appears in Langfuse with spans for each agent node.
6. **Schedule backups:**
   ```bash
   crontab -e   # add: 0 3 * * * cd ~/dispute-assistant && ./deploy/scripts/backup.sh >> ~/backup.log 2>&1
   ```

## Continuous delivery

- **On every pull request.** CI runs lint, unit and API tests, front-end checks, and the eval gate: an agent smoke run that fails the build if quality drops below `evals/thresholds.yaml` or regresses against `evals/baseline.json`.
- **On a merge to main.** CI pushes both images to GHCR, tagged with the commit SHA.
- **Deploying.** The `deploy` workflow waits for approval on the `production` environment, then SSHes to the VM and runs `release.sh <sha>`. That script backs up, pulls, restarts, health-checks, and rolls back automatically if `/readyz` doesn't come up.
- **Repository secrets needed:**
  - `VM_HOST`, `VM_USER`, `VM_SSH_KEY`
  - `LLM_API_KEY` (optional; CI falls back to a local Ollama model)
  - `JUDGE_API_KEY` (optional)
- **Repository variables:** `LLM_BASE_URL`, `LLM_MODEL`, `JUDGE_BASE_URL`, `JUDGE_MODEL`.

See [RUNBOOK.md](RUNBOOK.md) for operations.
