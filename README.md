# Telegram Voice Message Transcriber

Telegram gruplarındaki sesli mesajları **UstaGPT API**'sini kullanarak otomatik olarak yazıya çeviren, kendi kendine barındırılabilen (self-hosted) bir Telegram botu.

Bu proje **herhangi bir yapay zeka modeli eğitmez, barındırmaz veya yerel olarak çalıştırmaz.** Yalnızca Telegram voice message dosyalarını alıp UstaGPT'nin OpenAI uyumlu audio transcription API'sına gönderir.

## Mimari

```
Telegram  ──►  Bot (aiogram)  ──►  RQ Queue (Redis)  ──►  Worker  ──►  UstaGPT API
                                        │                       │
                                        ▼                       ▼
                                    PostgreSQL              FFmpeg (OGG→MP3)
```

### Süreçler

| Servis    | Görev                                                |
|-----------|------------------------------------------------------|
| `bot`     | Telegram güncellemelerini alır, işleri kuyruğa ekler |
| `worker`  | Ses dosyasını indirir, dönüştürür, API'ya gönderir   |
| `postgres`| Kalıcı veri (kullanıcılar, gruplar, iş kayıtları)    |
| `redis`   | Dayanıklı kuyruk ve kısa süreli kilit/cache          |

## Gereksinimler

- Docker ve Docker Compose (v2)
- Bir Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Bir UstaGPT API anahtarı ([ustagpt.com.tr](https://ustagpt.com.tr))
- Linux VPS (önerilen) veya Docker destekli herhangi bir sistem

## Hızlı Başlangıç

```bash
# 1. Repoyu klonla
git clone <repo-url>
cd telegram-voice-message-transcriber

# 2. Ortam değişkenlerini yapılandır
cp .env.example .env
# .env dosyasını düzenle: TELEGRAM_BOT_TOKEN, USTAGPT_API_KEY, OWNER_TELEGRAM_ID

# 3. Stack'i başlat
make up

# 4. Logları izle
make logs
```

## Komutlar

| Komut | Açıklama |
|-------|----------|
| `make up` | Stack'i başlat |
| `make down` | Stack'i durdur |
| `make logs` | Tüm servis loglarını izle |
| `make migrate` | Veritabanı migrationlarını çalıştır |
| `make test` | Testleri çalıştır |
| `make lint` | Ruff ile kod kalitesini kontrol et |
| `make worker-scale count=3` | Worker sayısını ölçeklendir |
| `make dashboard` | RQ Dashboard'u başlat (monitoring profili) |

## Proje Yapısı

```
├── app/
│   ├── bot/                  # aiogram handler, filter, keyboard, middleware
│   │   ├── handlers/         # Komut ve mesaj işleyiciler
│   │   ├── filters/         # Özel filtreler
│   │   ├── keyboards/       # Inline klavyeler
│   │   ├── middlewares/     # Ara katmanlar
│   │   └── setup.py         # Dispatcher yapılandırması
│   ├── db/                   # Veritabanı katmanı
│   │   ├── models/          # SQLAlchemy modelleri
│   │   ├── repositories/    # Veri erişim katmanı
│   │   └── session.py       # Oturum yönetimi
│   ├── services/            # İş mantığı servisleri
│   ├── workers/             # RQ worker ve task tanımları
│   ├── config.py            # Pydantic Settings yapılandırması
│   ├── logging.py           # Yapılandırılmış JSON logging
│   ├── queue.py             # RQ kuyruk fabrikası
│   └── main.py              # Bot giriş noktası
├── migrations/              # Alembic migrationları
├── tests/                   # Testler
├── .env.example             # Örnek yapılandırma
├── Dockerfile               # Çok aşamalı Docker imajı
├── docker-compose.yml       # Servis tanımları
├── pyproject.toml           # Bağımlılıklar ve araç yapılandırması
└── Makefile                 # Yardımcı komutlar
```

## Teknoloji Yığını

- **Python 3.12** — ana çalışma zamanı
- **aiogram 3.x** — Telegram Bot framework
- **PostgreSQL 16** — kalıcı veritabanı
- **Redis 7** — kuyruk ve cache
- **RQ** — dayanıklı iş kuyruğu
- **SQLAlchemy 2.x** — ORM
- **Alembic** — migration yönetimi
- **httpx** — HTTP istemcisi (UstaGPT API)
- **Pydantic Settings 2.x** — yapılandırma yönetimi
- **FFmpeg** — ses dönüşümü (OGG → MP3)
- **Structlog** — yapılandırılmış JSON logging
- **Ruff** — linting ve formatlama
- **pytest** — test framework

## Lisans

MIT
