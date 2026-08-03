# Telegram Voice Message Transcriber

A self-hosted Telegram bot that automatically transcribes voice messages in approved groups using the **UstaGPT API**.

This project **does not train, host, or run any AI model locally.** It only receives Telegram voice message files and sends them to UstaGPT's OpenAI-compatible audio transcription API.

## Architecture

```
Telegram  ──►  Bot (aiogram)  ──►  RQ Queue (Redis)  ──►  Worker  ──►  UstaGPT API
                                        │                       │
                                        ▼                       ▼
                                    PostgreSQL              FFmpeg (OGG→MP3)
```

### Processes

| Service   | Role                                                |
|-----------|-----------------------------------------------------|
| `bot`     | Receives Telegram updates, enqueues jobs            |
| `worker`  | Downloads audio, converts, sends to API             |
| `postgres`| Persistent data (users, groups, job records)        |
| `redis`   | Durable queue and short-lived locks/cache           |

## Requirements

- Docker and Docker Compose (v2)
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- A UstaGPT API key from [ustagpt.com.tr](https://ustagpt.com.tr)
- Linux VPS (recommended) or any Docker-capable system

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd telegram-voice-message-transcriber

# 2. Configure environment variables
cp .env.example .env
# Edit .env: set TELEGRAM_BOT_TOKEN, USTAGPT_API_KEY, OWNER_TELEGRAM_ID

# 3. Start the stack
make up

# 4. Follow the logs
make logs
```

## Commands

| Command | Description |
|---------|-------------|
| `make up` | Start the stack |
| `make down` | Stop the stack |
| `make logs` | Follow all service logs |
| `make migrate` | Run database migrations |
| `make test` | Run tests |
| `make lint` | Run Ruff code quality checks |
| `make worker-scale count=3` | Scale worker replicas |
| `make dashboard` | Start RQ Dashboard (monitoring profile) |

## Project Structure

```
├── app/
│   ├── bot/                  # aiogram handlers, filters, keyboards, middlewares
│   │   ├── handlers/         # Command and message handlers
│   │   ├── filters/          # Custom filters
│   │   ├── keyboards/        # Inline keyboards
│   │   ├── middlewares/      # Middleware layers
│   │   └── setup.py          # Dispatcher configuration
│   ├── db/                   # Database layer
│   │   ├── models/           # SQLAlchemy models
│   │   ├── repositories/     # Data access layer
│   │   └── session.py        # Session management
│   ├── services/             # Business logic services
│   ├── workers/              # RQ worker and task definitions
│   ├── config.py             # Pydantic Settings configuration
│   ├── logging.py            # Structured JSON logging
│   ├── queue.py              # RQ queue factory
│   └── main.py               # Bot entry point
├── migrations/               # Alembic migrations
├── tests/                    # Tests
├── .env.example              # Example configuration
├── Dockerfile                # Multi-stage Docker image
├── docker-compose.yml        # Service definitions
├── pyproject.toml            # Dependencies and tool configs
└── Makefile                  # Helper commands
```

## Tech Stack

- **Python 3.12** — primary runtime
- **aiogram 3.x** — Telegram Bot framework
- **PostgreSQL 16** — persistent database
- **Redis 7** — queue and cache
- **RQ** — durable job queue
- **SQLAlchemy 2.x** — ORM
- **Alembic** — migration management
- **httpx** — HTTP client (UstaGPT API)
- **Pydantic Settings 2.x** — configuration management
- **FFmpeg** — audio conversion (OGG → MP3)
- **Structlog** — structured JSON logging
- **Ruff** — linting and formatting
- **pytest** — test framework

## License

MIT
