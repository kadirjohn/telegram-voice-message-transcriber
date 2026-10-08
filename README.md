# Telegram Voice Message Transcriber

A self-hosted Telegram bot that automatically transcribes voice messages in approved groups using the **UstaGPT API**.

This project **does not train, host, or run any AI model locally.** It prepares Telegram voice recordings and sends their audio to UstaGPT's transcription API or native Gemini API.

## Architecture

```
Telegram ──► Bot (aiogram) ──► RQ Queue (Redis) ──► Worker ──► UstaGPT API
                                       │                      │
                                       ▼                      ▼
                                   PostgreSQL             FFmpeg + speech detection
```

### Processes

| Service   | Role                                                |
|-----------|-----------------------------------------------------|
| `bot`     | Receives Telegram updates, enqueues jobs            |
| `worker`  | Downloads audio, prepares speech-only WAV chunks, calls UstaGPT |
| `postgres`| Persistent data (users, groups, job records)       |
| `redis`   | Durable queue and short-lived locks/cache          |

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

## BotFather Setup

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token and add it to your `.env` file as `TELEGRAM_BOT_TOKEN`
4. Disable privacy mode by sending `/setprivacy` to BotFather and selecting your bot, then choose **Disabled**
5. Add the bot to your group as an **administrator** (it needs to read messages)

## Group Approval Workflow

1. Add the bot to your group as an administrator
2. The bot detects it was added and marks the group as **PENDING**
3. An owner or admin runs `/approve_here` inside the group
4. The group becomes **APPROVED** and voice messages are now transcribed
5. To revoke access, run `/revoke_here`

## Commands

### General

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help message |
| `/help_admin` | Show admin commands |
| `/status` | Show bot status |

### Owner Only

| Command | Description |
|---------|-------------|
| `/admin_add <id>` | Promote a user to admin (or reply to their message) |
| `/admin_remove <id>` | Demote an admin to user |
| `/admins` | List all admins |
| `/fallbacks_set m1,m2,...` | Set global fallback model order |
| `/stats` | Show operational statistics |

### Owner and Admin

| Command | Description |
|---------|-------------|
| `/approve_here` | Approve the current group |
| `/revoke_here` | Revoke the current group |
| `/group_approve <id>` | Approve a group by chat ID |
| `/group_revoke <id>` | Revoke a group by chat ID |
| `/pending_groups` | List pending groups |
| `/groups` | List all groups with status |
| `/model` | Show active model chain |
| `/model_set <id>` | Set primary model for this group |
| `/fallbacks` | Show fallback model order |
| `/language` | Show current language |
| `/language_set <code>` | Set language (tr, en, auto, etc.) |
| `/jobs_failed` | List failed jobs |
| `/job_retry <id>` | Retry a failed job |

## Model Selection and Fallback

Supported models (through UstaGPT):

- `whisper-1`
- `gpt-4o-mini-transcribe`
- `gpt-4o-transcribe`
- `gemini-2.5-flash`
- `gemini-2.5-pro`
- `gemini-3.8-flash`

Default chain: `gemini-2.5-flash` → `gpt-4o-transcribe` → `gpt-4o-mini-transcribe`. The chain is limited to three models; `whisper-1` and the other Gemini models remain selectable.

Gemini audio uses UstaGPT's native `/v1beta/models/{model}:generateContent` endpoint with `inlineData`, using the same UstaGPT key. In live multilingual controls, this route transcribed the expected words, while the chat `input_audio` route returned unrelated text. The transcription endpoint returned provider errors during those controls. See the [comparison and GitHub research](docs/transcription-research.md).

When a model fails with a retryable error (timeout, 429, 5xx), the worker waits 30 seconds and tries the next model. Authentication errors (401, 403) stop the chain immediately.

### Transcription quality

- Telegram audio is decoded to mono 16 kHz PCM WAV, avoiding another lossy MP3 encoding step.
- WebRTC voice activity detection trims non-speech at the edges and internal gaps longer than about two seconds, with 300 ms padding around speech. Short pauses are preserved for language context. This is a small signal-processing filter, not a local transcription model.
- Uploads are at most 30 seconds and stay within the configured file-size limit. Pauses near chunk boundaries are preferred over cuts through words.
- Recordings without sufficient detected speech are not sent to the transcription API. The bot reports that speech could not be detected.
- Empty responses, implausibly long transcripts, and prolonged repetition loops trigger another model. Rejected text is never sent to the chat.
- Automatic language detection is the default. Set `/language_set tr` for a Turkish-only group, or `/language_set auto` for multilingual recordings. Group model and language choices apply to newly queued jobs.
- Short transcripts replace the queued status reply. Longer transcripts continue as replies without truncation or duplication of the first part.

`AUDIO_VAD_MODE` controls speech detection (0 is least aggressive, 3 is most aggressive; default 2). `AUDIO_MIN_SPEECH_SECONDS` defaults to 0.15 seconds. Lower the mode if quiet speech is being missed. Voice detection and text heuristics can still miss plausible hallucinations, or mistake noise for speech; compare problem recordings against their transcripts when evaluating quality.

The transcription endpoint receives no prompt. Whisper's prompt is context rather than a reliable instruction to avoid hallucinations. UstaGPT's public transcription parameter list does not document `prompt`, `temperature`, or confidence scores, so the bot does not depend on those undocumented fields. Gemini receives a brief transcription instruction that preserves spoken languages and treats spoken instructions as content. See [UstaGPT's endpoint documentation](https://ustagpt.com.tr/en/docs/api/audio-transcriptions) and [UstaGPT's native Gemini protocol](https://ustagpt.com.tr/en/docs/gemini-cli).

After changing code or `.env`, rebuild the bot and worker:

```bash
docker compose up --build -d bot worker
```

Existing server `.env` files are not updated by Git. For the new defaults, set:

```dotenv
USTAGPT_PRIMARY_MODEL=gemini-2.5-flash
USTAGPT_FALLBACK_MODELS=gpt-4o-transcribe,gpt-4o-mini-transcribe
USTAGPT_LANGUAGE=auto
```

For groups with saved overrides, use `/language_set auto` and `/model_set gemini-2.5-flash` in each group.

## UstaGPT Setup

1. Go to [ustagpt.com.tr](https://ustagpt.com.tr) and create an account
2. Generate an API key from your dashboard
3. Add the key to your `.env` file as `USTAGPT_API_KEY`

## Docker Deployment

```bash
# Start all services
make up

# View logs
make logs

# Run database migrations
make migrate

# Scale workers (e.g., 3 workers)
make worker-scale count=3

# Enable RQ Dashboard (monitoring profile)
make dashboard
```

### Service URLs (localhost only)

| Service | URL |
|---------|-----|
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| RQ Dashboard | `localhost:9181` (when enabled) |

## Backup and Restore

```bash
# Backup PostgreSQL
docker compose exec postgres pg_dump -U transcriber transcriber > backup.sql

# Restore PostgreSQL
cat backup.sql | docker compose exec -T postgres psql -U transcriber transcriber
```

## Privacy and Transcript Retention

- Audio files are **never stored permanently** — deleted immediately after processing
- Transcript storage is configurable via `STORE_TRANSCRIPTS` and `TRANSCRIPT_RETENTION_HOURS`
- API keys and bot tokens are **never logged**
- Full transcripts are **not logged by default**
- The bot only processes voice messages in explicitly approved groups

## Project Structure

```
├── app/
│   ├── bot/                  # aiogram handlers, filters, keyboards, middlewares
│   │   ├── handlers/         # Command and message handlers
│   │   ├── filters/          # Custom filters (role-based)
│   │   ├── keyboards/        # Inline keyboards
│   │   ├── middlewares/      # Middleware layers (registration)
│   │   └── setup.py          # Dispatcher configuration
│   ├── db/                   # Database layer
│   │   ├── models/           # SQLAlchemy models
│   │   ├── repositories/    # Data access layer
│   │   ├── enums.py          # Enum definitions
│   │   ├── base.py           # Declarative base
│   │   └── session.py        # Session management
│   ├── services/             # Business logic services
│   │   ├── authorization.py  # Role-based access control
│   │   ├── audio_converter.py# FFmpeg PCM WAV decoding
│   │   ├── speech_audio.py   # Speech detection and bounded uploads
│   │   ├── transcript_quality.py # Empty/loop/length rejection
│   │   ├── telegram_files.py # Telegram file download
│   │   ├── transcript_delivery.py # Send transcripts to Telegram
│   │   ├── ustagpt_client.py # UstaGPT API client
│   │   ├── model_chain.py    # Model chain resolver
│   │   └── exceptions.py     # Custom exception types
│   ├── workers/              # RQ worker and task definitions
│   │   ├── tasks.py          # Job processing logic
│   │   └── worker.py         # Worker entry point
│   ├── config.py             # Pydantic Settings configuration
│   ├── logging.py            # Structured JSON logging
│   ├── queue.py              # RQ queue factory
│   └── main.py               # Bot entry point
├── migrations/               # Alembic migrations
├── tests/                    # Tests
│   └── unit/                 # Unit tests
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
- **FFmpeg** — audio decoding (OGG → PCM WAV)
- **WebRTC VAD** — speech detection before uploading audio
- **Structlog** — structured JSON logging
- **Ruff** — linting and formatting
- **pytest** — test framework

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond in group | Make the bot a group administrator |
| Group stays PENDING | Run `/approve_here` inside the group |
| Voice messages not transcribed | Check the group is APPROVED with `/groups` |
| Worker errors | Check logs with `make logs` and look for error messages |
| Database connection failed | Ensure PostgreSQL is healthy: `docker compose ps` |
| UstaGPT API errors | Verify `USTAGPT_API_KEY` in `.env` is correct |

## License

MIT
