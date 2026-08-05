# ETH Whale Watcher

Watches Ethereum for "whale" USDT transfers and stores them in Postgres.

## How it works

1. Polls `eth_getLogs` over explicit block ranges, lagging `CONFIRMATION_BLOCKS` behind head.
   Not `create_filter` — a server-side filter keeps its cursor on the node, so there is
   nothing to persist and nothing to resume from.
2. Keeps `Transfer` events at or above `WHALE_THRESHOLD_TOKENS`. `value` is not indexed and
   log filters only match topics by equality, so the threshold has to be applied client-side.
3. Writes them deduplicated by `(tx_hash, log_index)`. One transaction emits many `Transfer`
   logs, so `tx_hash` alone is not unique.
4. Scan position lives in `scan_state`, not in `MAX(block_number)` — most ranges contain no
   whales, but having scanned them is still progress.

Inserts and the scan-position update share one transaction, so a crash mid-scan re-scans
that range on the next poll and `ON CONFLICT DO NOTHING` makes the retry a no-op.

## Stack

- **Web3** — Python API for talking to Ethereum nodes
- **SQLAlchemy + Alembic** — ORM + migration system
- **pydantic-settings** — config, .env management
- **uv** — dependency management
- **Docker Compose** — local infrastructure in one command

## Configuration

| Variable                 | Default   | Notes                                 |
|--------------------------|-----------|---------------------------------------|
| `WHALE_THRESHOLD_TOKENS` | `1000000` | whole USDT, not raw units             |
| `CONFIRMATION_BLOCKS`    | `12`      | reorg buffer, ~2.4 min                |
| `MAX_BLOCKS_PER_SCAN`    | `10`      | capped by the RPC provider, see below |
| `SQL_ECHO`               | `false`   | log every SQL statement               |

## Running locally

One-time setup:

```bash
uv sync
cp .env.example .env        # fill in ETH_RPC_URL
docker compose up -d
uv run alembic upgrade head
uv run pre-commit install
```

Running poller:

```bash
uv run python main.py
```

## Provider limits

- Alchemy free tier caps `eth_getLogs` at a 10-block range. At 15s polling that covers 40 blocks/min against ~5
  produced, so there is headroom to catch up after downtime.
- publicnode allows 100-block ranges but keeps only ~50 blocks of log history and returns a bare HTTP 403 for anything
  older, so it can't be used to backfill.

## Status

Polling, filtering, and storage work.

Not done yet: reorg handling (`block_hash` is stored but unused, and
`CONFIRMATION_BLOCKS` is a probabilistic buffer rather than finality), Celery beat
instead of the current `while`/`sleep` loop, and Slack notifications.
