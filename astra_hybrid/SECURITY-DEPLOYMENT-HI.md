# ASTRA Hybrid v26 — सुरक्षा और तैनाती

## महत्वपूर्ण सुरक्षा बदलाव
- Cloud text/audio request तभी भेजें जब operator ने `ASTRA_ALLOW_CLOUD_TEXT=1` सेट करके अनुमति दी हो। यह consent setting है, सुरक्षा का विकल्प नहीं।
- Personal Cloud token कम-से-कम 32 random characters का रखें; source code, ZIP, logs या Git में न रखें।
- Server default `127.0.0.1` पर bind करता है। Internet exposure के लिए TLS reverse proxy, firewall, rate limiting, request-size limits, backups और OS-level process isolation अनिवार्य हैं।
- API ingestion HTTPS, exact hostname allowlist, redirects बंद, JSON content-type, response-size cap और DNS public-IP precheck लागू करता है।
- **DNS rebinding सीमा:** Python urllib connection के समय अलग DNS lookup कर सकता है। इसलिए production VPS पर egress firewall से केवल approved public API hosts/ports allow करें; cloud metadata, loopback, private और link-local ranges block करें। DNS precheck को अकेली SSRF सुरक्षा न मानें।
- Browser/API/agent सामग्री `pending_review` में जाती है। Approval के बाद भी वह केवल reviewed evidence है; training dataset में जोड़ने से पहले license, transcript, speaker consent, split और dataset preflight पास होना चाहिए।
- Voice quality ratings मॉडल को अपने-आप train नहीं करतीं। वे सिर्फ अलग feedback ledger में जाती हैं।

## इंजन route और environment
- `VAJRA`: local Indic Tiny TTS (`ASTRA_INDIC_TINY_TTS_MODEL_DIR`) या online Edge TTS (`edge-tts` package)। Local model upstream code import करता है; पहले repository review और explicit opt-in जरूरी है।
- `AGNI`: local Piper (`piper`, `PIPER_MODEL_PATH`) या personal cloud Piper (`ASTRA_CLOUD_URL`, `ASTRA_CLOUD_TOKEN`)।
- `VAYU`: local eSpeak NG या personal cloud eSpeak NG।
- `ASTRA`: local personal adapter (`ASTRA_LOCAL_TTS_COMMAND` JSON argv; `{text_file}` और `{output_file}` placeholders) या ElevenLabs (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`)। Local adapter को operator ही install/review करे।
- Online fallback के लिए `ASTRA_ALLOW_CLOUD_TEXT=1` जरूरी है; इससे कहानी का text चुने गए cloud provider तक जाएगा।

## यह रिलीज़ क्या नहीं करती
- VPS/डोमेन खरीदना या cloud deploy करना।
- किसी voice model के weights train/fine-tune करना।
- किसी API/browser data को बिना review model weights में बदलना।
- वास्तविक provider calls या चारों आवाज़ों की quality certify करना; उसके लिए credentials, installed models और live smoke tests चाहिए।


## Piper version note
इस update का AGNI runner maintained `piper-tts` 1.8 command interface (`python -m piper -m MODEL -f OUTPUT -- TEXT`) उपयोग करता है। Voice model और `.onnx.json` config दोनों जरूरी हैं। Package का license GPL-3.0-or-later है; voice model license अलग से जाँचें।
