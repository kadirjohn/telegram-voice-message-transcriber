# Ses transkripsiyonu araştırması — 9 Ekim 2026

## Sonuç

Sorun yalnızca prompt kaynaklı değil. Bu projede başlangıçta transkripsiyon endpoint'ine prompt gönderilmiyordu. Konuşma içermeyen seslerin modele gönderilmesi, gereksiz MP3 sıkıştırması ve başarılı HTTP yanıtlarının içerik denetimi olmadan kabul edilmesi halüsinasyon riskini artırıyordu.

Canlı kontrol ayrıca UstaGPT'nin iki Gemini istek yolu arasında önemli bir fark gösterdi: sohbet endpoint'inde `input_audio` ile gönderilen kayıt alakasız cümlelerle yanıtlandı; aynı kayıt native Gemini endpoint'inde `inlineData` ile gönderildiğinde beklenen Türkçe ve İngilizce konuşma yazıldı. Bu gözlem sohbet yolundaki ses aktarımının güvenilir olmadığını gösteriyor; gateway'in sesi tam olarak nerede kaybettiğini açıklamıyor.

## GitHub'daki yaklaşımlar

| Proje | Kaynak kodda görülen yaklaşım | Bu projeye etkisi |
| --- | --- | --- |
| [stder/telegram-voice-to-text-bot](https://github.com/stder/telegram-voice-to-text-bot/blob/main/app/transcriber.py) | Dosyayı doğrudan faster-whisper'a verir. `vad_filter=True`, `condition_on_previous_text=False`; dil ayarı boş bırakılabilir. | Konuşma algılama ve önceki hatalı metni sonraki parçaya taşımama yaklaşımı uygun. Bizde API çağrıları ayrı; önceki çıktı prompt olarak yeniden gönderilmiyor. |
| [gilgamezh/telegram-transcribe-bot](https://github.com/gilgamezh/telegram-transcribe-bot/blob/main/bot.py) | Telegram dosyasını geçici `.oga` dosyasına indirir, doğrudan yerel faster-whisper'a verir. Açık VAD ayarı veya prompt yok. CPU işlemlerini sıraya koyar. | Her botun özel prompt veya yeniden MP3 kodlama kullandığı varsayımı doğru değil. Bu örnek tek başına halüsinasyon önleme çözümü sunmuyor. |
| [aglvetik/AgliX-Speech-Bot](https://github.com/aglvetik/AgliX-Speech-Bot/blob/main/app/stt/model.py) | VAD, sessizlik süresi, beam size ve önceki metin bağlamını ayarlayabilir. Kısa kayıtları Rusçaya sabitler. | VAD yaklaşımı uygun; kısa kayıtları tek dile sabitleme çok dilli kullanımımıza uygun değil. Otomatik algılama korunuyor. |

[faster-whisper](https://github.com/SYSTRAN/faster-whisper#vad-filter), Silero VAD kullanır; varsayılan davranışı iki saniyeden uzun sessizlikleri kaldırmaktır. Bu projede yerel transkripsiyon modeli çalıştırma gereği olmadan WebRTC VAD kullanıldı. İki VAD aynı algoritma değildir; burada kısa iç duraklamalar yaklaşık iki saniyeye kadar korunur, konuşmanın çevresine 300 ms pay bırakılır.

[OpenAI Whisper'ın kaynak açıklaması](https://github.com/openai/whisper/blob/main/whisper/transcribe.py), önceki metnin sonraki pencereye taşınmasını kapatmanın tekrar döngülerini azaltabileceğini, ancak pencereler arası tutarlılığı da etkileyebileceğini belirtir. Bu yerel model ayarı UstaGPT'nin transkripsiyon formunda belgelenmediğinden sunucuya gönderilmiyor. Bağımsız, en fazla 30 saniyelik istekler ve çıktı denetimi kullanılıyor; parça sınırları yine bağlam kaybına yol açabilir.

## Canlı model kontrolü

İlk turdaki iki M4A eki model karşılaştırmasına geçildiğinde Voice Memos'un geçici dosya yollarından artık okunamıyordu. Bu nedenle ilk karşılaştırma aşağıdaki sentetik kayda aittir. Yeniden eklenen iki gerçek kaydın sonraki testi aşağıda ayrıca belirtilmiştir.

Bunun yerine bilinen içerikli, cihazda üretilen 13,66 saniyelik bir kontrol kaydı kullanıldı:

> Merhaba, yarın saat üçte buluşalım. Please bring the blue notebook. See you tomorrow.

Başta, iki dil arasında ve sonda toplam sekiz saniye sessizlik eklendi. İstekler her deneyde modeller arasında sırayla yapıldı. İşlenmiş ses 6,66 saniyelik tek WAV parçasına dönüştü.

| Model | Tam kayıt | Konuşma hazırlanmış kayıt |
| --- | --- | --- |
| gpt-4o-transcribe | HTTP 503, `all_providers_failed` | Aynı hata |
| gpt-4o-mini-transcribe | HTTP 503, `all_providers_failed` | Aynı hata |
| whisper-1 | HTTP 503, `all_providers_failed` | Aynı hata |
| gemini-2.5-flash, native | Beklenen kelimeler; 7,34 sn | `yarın` yerine `yarım`; kalan metin beklenen içerikte; 7,09 sn |
| gemini-2.5-pro, native | Beklenen kelimeler; 17,33 sn | Beklenen kelimeler; 17,38 sn |
| gemini-3.8-flash, native | Beklenen kelimeler; 5,46 sn | Beklenen kelimeler; 4,61 sn |

4o için M4A ve MP3 yüklemeleri de aynı 503 hatasını verdi. Bu denemelerde dosya biçimi değiştirmek sağlayıcı hatasını çözmedi. Bu, 4o'nun genel olarak çalışmadığı anlamına gelmez; test sırasında bu UstaGPT anahtarı ve endpoint üzerinden çalışır bir transkripsiyon alınamadı.

Aynı kontrol kaydı sohbet endpoint'ine Google'ın [OpenAI uyumlu ses biçimi](https://ai.google.dev/gemini-api/docs/openai#audio-understanding) ile gönderildiğinde:

- Gemini 2.5 Flash: `Hey, where's the remote?`
- Gemini 2.5 Pro: `I'm going to turn on some music.`
- Gemini 3.8 Flash: `He's a good kid.`

Bunlar kayıt içeriğiyle ilgisizdi. Bot bu sohbet ses yolunu kullanmıyor. [UstaGPT'nin native Gemini protokolü](https://ustagpt.com.tr/en/docs/gemini-cli) üzerinden `POST /v1beta/models/{model}:generateContent`, `x-goog-api-key` başlığı ve `inlineData` ses içeriği kullanılıyor. Ayrı Google API anahtarı gerekmiyor.

Tek sentetik kayıttan genel doğruluk sıralaması veya VAD'nin kelime hatasına neden olduğu sonucu çıkarılamaz. Gürültülü, fısıltılı, aksanlı ve aynı cümle içinde dil değiştiren gerçek kayıtlar ayrıca karşılaştırılmalı. Konuşma algılama bazı gürültüleri konuşma sayabilir veya çok sessiz konuşmayı kaçırabilir; tekrar/uzunluk denetimi de makul görünen kısa halüsinasyonları yakalayamaz.

## Uygulanan değişiklikler

- Sessizlik ve düşük seviyeli sabit gürültü, yeterli konuşma yoksa API'ye gönderilmiyor.
- MP3'e tekrar sıkıştırmak yerine mono 16 kHz PCM WAV hazırlanıyor; uzun kayıtlar sınırlı parçalara ayrılıyor.
- Boş, aşırı uzun veya uzun tekrar döngüsü içeren çıktı kullanıcıya gösterilmeden sonraki model deneniyor.
- Dil algılama otomatik kalıyor; grup ayarları yeni işlere aktarılıyor.
- Gemini native ses desteği eklendi. Kullanıcının tercihi ve sonraki gerçek kayıt testleriyle varsayılan `gemini-3.8-flash` olarak güncellendi; yedekler `gpt-4o-transcribe,gpt-4o-mini-transcribe`. Bu seçim UstaGPT üzerinden çalıştığı doğrulanan seçeneği kullanır, doğruluk üstünlüğü iddiası değildir.
- Zamanlanmış yeniden denemeler sonraki modelden devam ediyor; uzun sonuçlar kesilmeden Telegram'a aktarılıyor.
- Kuyrukta işin süresi kayıt uzunluğuna ve parça sayısına göre hesaplanıyor; uzun kayıtların çoklu API çağrıları eski sabit süre sınırına takılmıyor.

## Sunucuda ayarlar

Mevcut `.env` Git tarafından güncellenmez. Kod sunucuya aktarıldıktan sonra şu alanları ayarlayın:

```dotenv
USTAGPT_PRIMARY_MODEL=gemini-3.8-flash
USTAGPT_FALLBACK_MODELS=gpt-4o-transcribe,gpt-4o-mini-transcribe
USTAGPT_LANGUAGE=auto
```

Kayıtlı grup tercihleri varsa grup içinde `/model_set gemini-3.8-flash` ve `/language_set auto` kullanın.

```bash
make deploy
```

## Gemini kullanan botların kaynak incelemesi

İlk araştırma Whisper tabanlı örneklere ağırlık vermişti. Sonraki turda Gemini kullanan şu projelerin ses gönderen kodu ayrıca incelendi:

| Proje | Kaynakta görülen yöntem | Bizim kullanımımız için anlamı |
| --- | --- | --- |
| [ket0x4/gemini-speech2text-telegram](https://github.com/ket0x4/gemini-speech2text-telegram/blob/master/src/services/gemini.ts) | 20 MB altındaki sesi Base64 ve MIME türüyle doğrudan gönderir; büyük dosyayı Files API'ye yükleyip işlem sonunda siler. Google Interactions ve özel `gemini-3.5-transcribe` kullanır. Dil ipuçları isteğe bağlıdır. | Gerçek ses içeriği ile dosya türü birlikte aktarılmalı. Google'a özgü ayrı dosya yükleme/transkripsiyon yolunu UstaGPT'ye destek doğrulamadan taşımamak gerekir. |
| [Hormold/voiceoverbot](https://github.com/Hormold/voiceoverbot/blob/main/src/modules/aiService.ts) | Google sağlayıcısına gerçek ses Buffer'ını `file` parçası olarak verir. Dil koruyan sistem talimatı ve Zod şemalı `outputTranscription` aracıyla sonuç çıkarır. Ayrıca dolgu sözcüklerini temizler ve özet üretir. | Yapısal çıktı kontrolü yanıt biçimini denetler; metnin sesle aynı olduğunun kanıtı değildir. Dolgu temizleme/özetleme bizim birebir transkripsiyon amacımıza eklenmedi. |
| [winniesi/tg-gemini-bot](https://github.com/winniesi/tg-gemini-bot/blob/main/api/gemini.py) | Google SDK'sında `Part.from_bytes` ile dosya içeriğini ve MIME türünü `generate_content` çağrısına ekler. Geçici hatalarda sınırlı yeniden deneme kullanır. Medya isteği sohbet geçmişinden ayrı bir çağrıdır. | Kısa, ayrı bir transkripsiyon talimatı ve gerçek dosya parçası kullanılmalı; sohbet geçmişi transkripsiyona karıştırılmamalı. |

Bu örneklerin incelenen gönderim kodunda ses halüsinasyonunu tamamen engelleyen ortak bir denetim yok. Bizim VAD ve tekrar/uzunluk denetimimiz ek korumadır; Gemini için doğru native ses protokolünün yerini tutmaz. [Google'ın ses belgeleri](https://ai.google.dev/gemini-api/docs/audio) de sesin dosya/inline içerik olarak aktarılmasını gösterir.

## Yeniden eklenen gerçek kayıtların UstaGPT testi

9 Ekim 2026'da ekler önce proje dışındaki çalışma klasörüne kopyalandı. Ses dosyaları ve tam transkripsiyonlar Git'e eklenmedi. Otomatik dil algılama korunarak her deneyde modeller sırayla çağrıldı.

| Girdi | Gemini 3.8 Flash, tam WAV | Gemini 3.8 Flash, bot hazırlığı | Gemini 3.8 Flash, orijinal M4A |
| --- | --- | --- | --- |
| 35,2 saniyelik ilk kayıt | Türkçe ve İngilizce metin; 40,89 sn | 29,73 + 5,20 saniyelik iki parça; metin büyük ölçüde aynı; 10,58 sn | Metin büyük ölçüde aynı; 16,03 sn |
| 24,128 saniyelik ikinci kayıt | Almanca metin; 90,75 sn | 24,128 saniyelik tek parça; bazı sözcük ayrımları farklı; 72,96 sn | Almanca metin; bazı ifadeler farklı; 8,31 sn |

`gpt-4o-transcribe`, `gpt-4o-mini-transcribe` ve `whisper-1`, her iki tam WAV kaydında HTTP 503 / `all_providers_failed` döndürdü. Bu nedenle modeller arasında kelime doğruluğu ölçülemedi. Referans metin de yok; özellikle Almanca çıktılardaki farklı/belirsiz ifadeler doğrulanmış konuşma gibi değerlendirilmemeli. Orijinal M4A'nın daha kısa yanıt süresi tek deney gözlemidir; dosya biçimi dışında sağlayıcı yükü ve model değişkenliği de süreyi etkileyebilir.

[OpenAI'nin 4o Transcribe model belgesi](https://developers.openai.com/api/docs/models/gpt-4o-transcribe), özgün Whisper'a göre doğruluk iyileşmesi bildirir. Bu, Gemini 3.8 Flash'a karşı bir karşılaştırma değildir ve UstaGPT'deki mevcut sağlayıcı hatasını çözmez. Primary seçimimiz çalıştığı doğrulanan 3.8 Flash'tır; diğerlerinin daha düşük doğrulukta olduğu sonucu çıkarılmadı.

Sunucu kurulumunda yalnızca bot/worker başlatmak yerine `make deploy` kullanılmalı. Bu komut önce PostgreSQL/Redis sağlığını bekler, sonra `.env` içindeki `DATABASE_URL` ile migration çalıştırır ve uygulamayı başlatır. Kodun uzak depoya push edilmesi gerekir; yerel commit tek başına sunucudaki `git pull` ile alınamaz.
