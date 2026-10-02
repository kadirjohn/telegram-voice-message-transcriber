# MEDIA.md — Yapılacaklar Listesi

Bu dosya 2 Ekim 2026 oturumunda tespit edilen, **henüz çözülmemiş** sorunları içerir.
Her başlıkta: belirti, kök neden, kanıt, önerilen çözüm, risk.

Durum legendi:
- `[ ]` açık
- `[~]` kısmen çözüldü
- `[x]` çözüldü (detay aşağıda, referans commit)

---

## 1. `with_scheduler=True` için regresyon testi yok — EN KRİTİK

**Durum:** `[ ]` açık

### Belirti
Sesli mesaj alınıyor, bot "⏳ Sesli mesaj sıraya alındı." diyor, ardından hiçbir şey gelmiyor.
İş `RETRY_WAIT` durumunda sonsuza dek sıkışıyor, kullanıcı hata mesajı da almıyor.

### Kök neden
`app/workers/worker.py:51` içinde `worker.work(with_scheduler=True)` çağrılıyor.
Bu parametre olmadan RQ'nun scheduler'ı hiç çalışmıyor.

Retry'lanan işler `queue.enqueue_in()` ile doğrudan kuyruğa girmez,
`ScheduledJobRegistry`'ye konur ve scheduler'ın onları kuyruğa taşıması gerekir.
RQ 2.12'de `Worker.work()` parametresiz çağrıldığında `with_scheduler=False` gelir.

### Kanıt (23:11 UTC, düzeltme öncesi)
```
rq:scheduled:transcriptions: 6 iş (en eskisi 31 dakika geçmiş tarihli)
rq:queue:transcriptions:     0
```
Kuyruk tamamen boş, zamanlanmış işler hiç taşınmıyor. Worker logunda scheduler satırı yok.
Düzeltme sonrası: `Scheduler for transcriptions started with PID 7`, registry 0'a indi.

### Çözüm
`tests/unit/test_worker.py` oluştur: `worker.work` çağrısını patch'le, parametrenin
`with_scheduler=True` olduğunu doğrula.

### Risk
Parametre düşerse sistem tekrar sessizce çöker ve kimse fark etmez.
Bu hatayı bir kez yaşadık, kullanıcı fark etti.

---

## 2. `STORE_TRANSCRIPTS` ayarı hiç kullanılmıyor

**Durum:** `[ ]` açık

### Belirti
`transcription_jobs.transcript_text` sütunu her zaman NULL.
217 SUCCEEDED iş, 0 transkript metni.

### Kök neden
Ayar `app/config.py:70` ve `.env.example:35`'te tanımlı, `README.md:163`
"Transcript storage is configurable via STORE_TRANSCRIPTS and
TRANSCRIPT_RETENTION_HOURS" diyor — ama kodda **hiçbir yerde referansı yok**.
`app/workers/tasks.py` yalnızca `delivery.edit_status(...)` çağırıyor,
veritabanına yazmıyor.

### Not
`TRANSCRIPT_RETENTION_HOURS` de aynı durumda — tanımlı, kullanılmıyor.
Temizlik görevi de yok (cron/cleanup bulunamadı).

### Çözüm (iki seçenek, biri seçilmeli)
1. **Implementasyon:** `JobRepository`'ye `save_transcript()` ekle, `tasks.py`'de
   `SUCCEEDED` güncellemesinden sonra çağır. `TRANSCRIPT_RETENTION_HOURS` için
   eski kayıtları temizleyen bir iş ekle.
2. **Ayarı kaldır:** `STORE_TRANSCRIPTS`, `TRANSCRIPT_RETENTION_HOURS` ayarlarını ve
   README satırını sil. Transkript kasıtlı olarak sadece Telegram'da tutuluyorsa
   bu daha dürüst bir davranış.

### Risk
Şu anki hali kullanıcıya yanlış bilgi veriyor: ayar var gibi görünüyor,
hiçbir şey yapmıyor.

---

## 3. Docker log rotasyonu yok

**Durum:** `[ ]` açık

### Belirti
Log dosyaları sınırsız büyür. Disk yavaşça dolar.

### Kanıt
```
docker inspect tvmt-worker → {"Type":"json-file","Config":{}}
```
`Config` boş → `max-size` / `max-file` tanımlı değil.
json-file sürücüsünün varsayılanında sınır yoktur.

Log yolları: `/volume/docker/containers/<id>/<id>-json.log`
(bu kullanıcı tarafından okunamıyor, `sudo` yok)

### Mevcut durum
Disk %38 dolu, 89 GB boş. Acil değil.

### Çözüm
`docker-compose.yml`'de her servise:
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```
Uygulama kodunda değişiklik gerekmez.

---

## 4. Log gürültüsü — gerçek hataları gizliyor

**Durum:** `[ ]` açık

### Ölçüm
- Bot loglarının **%99'u** `health_check_ok` (30 saniyede bir, ~2880 kayıt/gün)
- Worker loglarının **~%74'ü** RQ'nın `Worker ...: cleaning registries for queue` mesajı

### Kök neden
- `app/main.py:17-28` — health check her 30 saniyede `INFO` seviyesinde logluyor.
  Compose zaten postgres/redis için healthcheck tanımlı, worker için de `restart: unless-stopped` var.
- `app/logging.py:60` — susturma listesi `httpx, httpcore, urllib3, aiogram` içeriyor,
  **`rq` yok**.

### Etki
Bu oturumda bir production hatası bulmak için log gürültüsünün arasından kazımak gerekti.
`scheduled_retry` sayısının 222 iş boyunca 0 olduğu fark edilmesi uzun sürdü.

### Çözüm
1. `app/logging.py:60` listesine `"rq"` ekle.
2. `app/main.py`'de health check'i `INFO` yerine `DEBUG` yap, ya da aralığı
   30 sn'den 5 dakikaya çıkar. Alternatif: yalnızca durum değişince logla.

### Not
Format da karışık: structlog event'leri JSON, stdlib/RQ/aiogram mesajları düz metin.
`logging.basicConfig(format="%(message)s")` yüzünden. Log aggregation varsa sorun olur.

---

## 5. `model_chain` veritabanına yazılıyor — eski işler yeni sırayı görmüyor

**Durum:** `[ ]` açık

### Belirti
Model sırası değiştirildiğinde, **bekleyen veya başarısız eski işler** eski sırayı kullanıyor.
`current_attempt` eski sıralamaya göre bir indeks olduğu için yeni modelleri atlıyor.

### Gerçek örnek (bu oturumda yaşandı)
6 iş `RETRY_WAIT`'te sıkışmıştı. Scheduler düzeltmesi sonrası kurtarılırken,
`current_attempt=2` ile resume eden işler `model_chain[2]`'den başladı —
Gemini 0. sıraya taşınmış olduğu için atlandı, doğrudan `gpt-4o-*` modellerine
düştü ve hepsi 502 verdi. 3 iş elle yeniden kuyruğa alınıp `model_chain` Gemini-only
olarak düzeltildi, ancak bu elle yapılan bir işlemdi.

### Kök neden
`app/bot/handlers/voice.py` → `model_chain` iş oluşturulurken DB'ye yazılıyor.
`app/workers/tasks.py:60` → `model_chain = job.model_chain or []` ile okunuyor.

### Çözüm
Zinciri çalışma anında çöz. `tasks.py:60`'ı her zaman ayarlardan türetecek şekilde
değiştir (`default_model_chain()`), DB'deki `model_chain` alanını ya tamamen
kullanmayı bırak ya da yalnızca "hangi modeller denendi" bilgisi olarak kullan.

### Alternatif (daha küçük değişiklik)
`model_chain` değiştiğinde bekleyen işlerin `model_chain` ve `current_attempt`
sütunlarını güncelleyen bir migration/fixture.

### Risk
Model sırasını değiştirmek her seferinde elle iş onarımı gerektirecek.
Bu oturumda iki kez oldu.

---

## 6. Kırık testler ve bozuk `make test`

**Durum:** `[ ]` açık

### 6a. `make test` hiç çalışmamış
`Makefile:31` → `docker compose run --rm bot pytest`
Ama `pytest` production imajında kurulu değil. `Dockerfile:16-17` `pip install .`
çalıştırıyor, `[project.optional-dependencies] dev` grubunu kurmuyor.

**Çözüm:** Dockerfile'da ayrı bir test aşaması, veya `make test` hedefini
`pip install '.[dev]'` yapacak şekilde düzelt.

### 6b. `test_extract_transcript_empty_json` — kırık
`tests/unit/test_ustagpt_client.py:49-57`

Test, `{}` JSON yanıtından `""` bekliyor. Ama `ustagpt_client.py:127-129`
`text` `str` değilse `response.text.strip()`'e düşüyor. `MagicMock(spec=httpx.Response)`
kullanıldığı için bu bir Mock nesnesi döndürüyor, `assert result == ""` patlıyor.

**Not:** Test, kodun gerçekleştirdiği davranışı değil varsaydığı davranışı test ediyor.
Kodda da bir tartışmalı nokta var: UstaGPT JSON dönerse ama `text` alanı yoksa
ham JSON'u transkript olarak döndürür.

**Çözüm:** Testi gerçek davranışa göre düzelt (`response.text` mock'la), ya da
kodu sıkılaştır (`text` yoksa boş string dön).

### 6c. `test_safe_error_redacts_secrets` — kırık
`tests/unit/test_ustagpt_client.py:115-130`

Test `"API key"` **kelimesinin** sonuçta geçmediğini iddia ediyor.
Ama `_safe_error` (`ustagpt_client.py:137-143`) `message` alanını bilerek dahil ediyor
ve UstaGPT'in kendi mesajı *"Missing or invalid API key"* diyor.

Sırın kendisi sızmıyor, sadece kelime geçiyor. Testin niyeti sızdırmamak,
ama assertion'ı çok kaba.

**Çözüm:** Gerçek anahtar değerinin sızmadığını assert et, `"API key"` kelimesini değil.

### Durum
`2 failed, 63 passed` — bu iki test HEAD'den beri kırık, atlanmış durumda.

---

## 7. Lockfile yok — build tekrarlanabilir değil

**Durum:** `[ ]` açık

### Belirti
Rebuild'da sürümler sessizce değişti. RQ `2.10.0 → 2.12.0` atladı.

### Kök neden
`pyproject.toml:9-20` bağımlılıkları `>=` ile aralık olarak yazıyor
(`rq>=2.0,<3` gibi). Hiçbir lockfile yok: `uv.lock`, `poetry.lock`,
`requirements.txt`, `Pipfile.lock` — hiçbiri yok.

`Dockerfile:16` her build'de `pip install .` çalıştırıyor → her seferinde
güncel sürümleri çekiyor.

### Risk
Production'a bir rebuild atıldığında hiçbir şey değişmemiş gibi görünür,
ama içinde farklı sürümler olur. Bugün oltu.

### Çözüm
`uv` veya `poetry` ile lockfile üret, Dockerfiles'ı lockfile'ı kullacak şekilde düzelt.

---

## 8. Container image boyutu (664 MB) — ertelenmiş, düşük aciliyet

**Durum:** `[~]` ölçüldü, uygulanmadı — 3 Ekim 2026'da "disk tamam, bırak" kararıyla kapatıldı

### Ölçüm (arm64, host aarch64)

```
bot image      664 MB
worker image   664 MB   (ikisi de aynı Dockerfile'dan)
postgres       288 MB   (bu projeye ait değil, paylaşımlı tag)
redis           42 MB
```

Container içi dağılım:

```
/usr                     634 MB
  /usr/lib               430 MB
    /usr/lib/aarch64-linux-gnu  428 MB
      libLLVM.so.19.1           118 MB   ← x265 VIDEO codec'inin JIT'i
      libgallium-25.0.7         34 MB   ← OpenGL
      libz3.so.4                 26 MB
      libcodec2.so.1.2           17 MB
      libavcodec.so.61           14 MB   ← ffmpeg (GEREKLİ)
      libavfilter.so.10          13 MB   ← ffmpeg (GEREKLİ)
      libx265.so.215              9 MB   ← video codec (GEREKSIZ)
      libplacebo.so.349           9 MB
/usr/local              140 MB   (Python base 132 + pip paketleri ~108)
/usr/share               29 MB
/usr/bin                 30 MB
ffmpeg binary'i           1 MB
```

`python:3.12-slim` base tek başına 149 MB. Yani 664 - 149 = ~515 MB bizim eklediğimiz.

### Kırılabilecek olan
`libLLVM` (118 MB) + `libx265` (9 MB) + mesa/OpenGL (`libgallium` 34 MB, `libplacebo` 9 MB) +
`libz3` (26 MB) → **~200 MB tamamen gereksiz**. Bunların tamamı Debian `ffmpeg`
paketinin video codec ve grafik bağımlılıklarından geliyor. Proje sadece ses
decode + mp3 encode yapıyor.

Paket listesi ölçümü (site-packages): sqlalchemy 29 MB, psycopg2 16 MB, pip 14 MB,
aiogram 10 MB, aiohttp 9 MB, pydantic_core 5 MB — bunlar gerekli, `pip` 14 MB
ise kurulumdan sonra silinebilir.

### Önerilen çözüm: statik ffmpeg
`/usr/local/bin/ffmpeg` olarak statik build (~40 MB, tek dosya). Tüm formatları
destekler (OGG/Opus, M4A, MP3, FLAC, WAV), hiçbir `.so` bağımlılığı yok.
`audio_converter.py` değişmeden çalışır, `ffmpeg` komutu aynı kalır.

Tahmini sonuç: **664 MB → ~250 MB**

### Neden ertelendi
Disk baskısı yok. Bu oturumda 8.9 GB dangling image + build cache temizliği yapıldı,
gereksiz yer sorunu kalmadı. Image boyutu bir konfor meselesi, sorun değil.

### Dikkat edilecek kısıt
**Format desteği korunmalı.** Telegram sesli mesajları OGG/Opus gelir ama
M4A/MP3/FLAC da gelebilir. Debian `ffmpeg` paketinden codec'leri teker teker
çıkarmak (`libavcodec61 libavformat61 libavutil59 libmp3lame0 libopus0 libogg0`)
yalnızca ~430 MB'a indiriyor (ölçüldü) ve `ffmpeg`/`ffprobe` binary'leri
gittiği için `audio_converter.py`'de subprocess değişikliği gerekiyor.
Statik build bu riski ortadan kaldırır — bu yüzden tercih edildi.

### Geri dönüş notu
`git checkout Dockerfile` ile geri alınabilir, kod değişikliği gerekmez.

---

## 9. Temizlik yapılırken diğer projelere dikkat

**Durum:** `[x]` çözüldü (2026-10-03)

Bu oturumda disk temizliği yapılırken `docker image prune` komutunun **tüm
projeleri** kapsadığı doğrulandı — projeler arası ayrım yok.

Kontrol edilmeden silinmesi tehlikeli bulunan image:

```
4db228bee7e7  272MB  postgres:16-alpine (eski, 14 Mayıs)
  → filesfly-db container'ı BU image'a dayanıyor (Up 3 days)
```

Silinmedi. Docker çalışan container'ın kullandığı image'ı zaten prune'da
atlıyor, ama bilerek doğrulandı.

**Kural:** `docker image prune -f` çalıştırmadan önce
`docker images -f "dangling=true"` çıktısını al ve her image'ın
`docker ps -a` içinde kullanıcısını doğrula:

```bash
docker inspect <container> --format '{{.Image}}' | grep <image-id>
```

Bu oturumda 14 dangling image silindi (12 × 664 MB + 2 × 650 MB, hepsi bu
projeye ait), `filesfly`'nin postgres image'ı korundu. Kazanç: ~8.9 GB.

### Not
`docker system df` çıktısındaki `RECLAIMABLE` değeri yanıltıcıdır: silinen
katmanlar diğer image'larla paylaşıldığı için gerçek kazanç (652 MB) toplam
silinen image boyutundan (8.9 GB) çok daha küçüktür.

---

## Çözülenler (referans)

| Commit | Konu |
|---|---|
| `60dcd31` | Eksik `USTAGPT_RETRY_DELAY_SECONDS` ayarı + retry zincirinin kaldığı yerden devam etmesi |
| `7d7a750` | `response_format` varsayılanı `json`; `/job_retry` kolonlu `job_id` hatası |
| `d059de3` | Gemini chat endpoint'i (base64) model zincirine eklendi |
| `4158277` | Varsayılan model `gemini-3.8-flash` |
| `13cfd06` | RQ scheduler açıldı — retry işleri artık kuyruğa taşınıyor |
| `00097bb` | Prompt "Türkçeye çevir" yerine "olduğu dilde yazıya dök" |
| `4383f13` | MEDIA.md — açık sorunlar listesi |

---

## UstaGPT tarafındaki açık sorunlar

Bunlar bizim kodumuzda değil, ayrı takip gerektiriyor.

1. **`/v1/audio/transcriptions` 502 dönüyor.** `whisper-1`, `gpt-4o-mini-transcribe`,
   `gpt-4o-transcribe` — üçü de. `/v1/models` ve `/v1/chat/completions` 200 çalışıyor,
   yani sorun endpoint'e özgü. 1 Ekim 08:36'dan beri (rapor anında) devam ediyordu.
2. **`response_format=text` / `srt` / `vtt` daima 502.** `json` ve parametresiz
   istek 200. 4/4 tekrarlandı. Bu ayrı bir hata, endpoint düzelse bile devam eder.
   400 + JSON hata dönmeleri önerildi (502 "geçici" sinyali veriyor, kalıcı hata değil).
3. **Rapor dosyaları:** `/tmp/opencode/USTAGPT_HATA_BILDIRIMI.md` (uzun rapor),
   `/tmp/opencode/ustagpt_repro.py` (reproducer script).

### Çalışma zamanı notu
UstaGPT toparlanınca `whisper-1` otomatik olarak ikinci sıradan devreye girecek —
zincir sırası config ile yönetiliyor, kod değişikliği gerekmez.