# eth-whale-watcher

Watches Ethereum for "whale" USDT transfers, stores them, and (optionally) posts them to Slack.

## How it works

1. A periodic Celery task polls the chain for new blocks (lagging `CONFIRMATION_BLOCKS` behind head to avoid reorgs).
2. It scans `Transfer` events of the USDT contract and keeps those above `WHALE_THRESHOLD`.
3. New transfers are written to the database, deduplicated by `(tx_hash, log_index)`.
4. If Slack is enabled, each newly stored transfer triggers a webhook message.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Redis (Celery broker)
- PostgreSQL (or any SQLAlchemy-supported DB)

## Setup

```bash
uv sync
cp .env.example .env   # then fill in ETH_RPC_URL and the rest
uv run pre-commit install
```

## Running

```bash
# worker
uv run celery -A app.celery_app worker --loglevel=info

# beat scheduler (periodic polling)
uv run celery -A app.celery_app beat --loglevel=info
```

## Development

Lint and format via pre-commit (ruff):

```bash
uv run pre-commit run --all-files
```

## Configuration

See `.env.example` for every supported variable.

## Status

Early scaffolding. Chain polling, storage layer, and Slack sink are not implemented yet.
