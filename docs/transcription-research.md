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

Kullanıcının iki örnek M4A eki ilk incelemede 3,05 ve 35,2 saniye olarak okunmuştu. Model karşılaştırmasına geçildiğinde Voice Memos'un geçici dosya yolları artık okunamıyordu. **Bu iki gerçek kayıt için transkripsiyon sonucu elde edilmedi.** Tekrar eklenmeleri gerekiyor.

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
- Gemini native ses desteği ve üç Gemini model seçeneği eklendi. Varsayılan `gemini-2.5-flash`; yedekler `gpt-4o-transcribe,gpt-4o-mini-transcribe`. Bu seçim kontrol sırasında çalışan daha düşük maliyetli Gemini seçeneğini kullanır, doğruluk üstünlüğü iddiası değildir.
- Zamanlanmış yeniden denemeler sonraki modelden devam ediyor; uzun sonuçlar kesilmeden Telegram'a aktarılıyor.
- Kuyrukta işin süresi kayıt uzunluğuna ve parça sayısına göre hesaplanıyor; uzun kayıtların çoklu API çağrıları eski sabit süre sınırına takılmıyor.

## Sunucuda ayarlar

Mevcut `.env` Git tarafından güncellenmez. Kod sunucuya aktarıldıktan sonra şu alanları ayarlayın:

```dotenv
USTAGPT_PRIMARY_MODEL=gemini-2.5-flash
USTAGPT_FALLBACK_MODELS=gpt-4o-transcribe,gpt-4o-mini-transcribe
USTAGPT_LANGUAGE=auto
```

Kayıtlı grup tercihleri varsa grup içinde `/model_set gemini-2.5-flash` ve `/language_set auto` kullanın. Daha güçlü Gemini seçeneklerini denemek için `/model_set gemini-2.5-pro` veya `/model_set gemini-3.8-flash` kullanılabilir.

```bash
docker compose up --build -d bot worker
```
