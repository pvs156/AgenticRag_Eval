# Runbook

Each alert in `deploy/prometheus/alerts.yml` links to a section here.

## Everyday commands

```bash
docker compose ps                         # status and health
docker compose logs -f api --since 10m    # API logs (JSON lines from Caddy, Python logs from api)
cat .release/current .release/history    # deployed SHA and release history
./deploy/scripts/release.sh <sha>         # deploy or roll back to any built SHA
```

## api-down

1. Run `docker compose ps api`. If it is restarting, check `docker compose logs api | tail -50`.
2. **OOM kill** (`dmesg | grep -i oom`): raise `mem_limit` for `api`, or move to a bigger VM. Swap should prevent this on small hosts.
3. **Bad release:** roll back with `./deploy/scripts/release.sh $(tail -2 .release/history | head -1 | cut -d' ' -f2)`.

## errors

1. Find failing turns: `docker compose logs api | grep -i error`.
2. **LLM HTTP 401/403:** the key was revoked or has expired. Update `.env`, then `docker compose up -d api`.
3. **LLM HTTP 429:** the free-tier rate limit was hit. Lower `RATE_LIMIT_PER_MIN`, or switch `LLM_MODEL` to a model with higher limits.

## latency

1. The Grafana panel "p95 latency by agent node" shows which step is slow.
2. **`explain` or `understand` slow:** the provider is slow, so try another model.
3. **`retrieve` slow:** the reranker is CPU-bound. Set `ENABLE_RERANK=false` as a temporary measure and note the quality trade-off.

## quality

Triggered by an abstention spike, a retry spike or a groundedness drop.

1. Open Langfuse and filter traces by low `groundedness` or `first_draft_passed = 0`.
2. Check whether the model or prompt changed: the dashboard annotations and `.release/history`.
3. Label bad traces in the Langfuse annotation queue, add them to `evals/datasets/build_golden.py`, and rerun the eval. The regression then becomes a permanent test.
4. Roll back if a release caused it.

## cost

1. Check the "LLM spend" panel. Free tiers should show $0; any spend means a paid model is configured.
2. Lower `ONLINE_EVAL_SAMPLE_RATE` or `JUDGE_BUDGET_USD`.

## disk

1. Reclaim space with `docker system prune -af` (removes unused images).
2. Check `du -sh ~/backups`; backups keep 14 copies.
3. Prometheus retention is 15 days (`--storage.tsdb.retention.time`).

## Restore drill (do this once and record the date)

```bash
./deploy/scripts/backup.sh
./deploy/scripts/restore.sh ~/backups/app-<stamp>.db
curl -s https://<site>/api/health
```
