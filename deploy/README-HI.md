# Personal Cloud — Docker तैनाती (Hindi)

यह deployment template है; इसे अभी किसी VPS पर deploy नहीं किया गया है।

## जरूरतें
- Ubuntu/Debian x86_64 या ARM64 VPS, Docker Engine + Docker Compose plugin
- Domain का DNS A/AAAA record VPS की public IP पर
- वैध Hindi Piper `.onnx` model और साथ की `.onnx.json` config, दोनों `models/` में
- Piper voice/model की license और commercial-use शर्तें अलग से जाँचें

## Setup
1. `deploy/.env.example` को `deploy/.env` नाम से copy करें।
2. `ASTRA_DOMAIN` में अपना domain लिखें।
3. `ASTRA_CLOUD_TOKEN` में कम-से-कम 48 अक्षरों का random secret रखें; इसे chat/Git/ZIP में न भेजें।
4. Hindi Piper model को `models/hindi.onnx` और config को `models/hindi.onnx.json` नाम से रखें।
5. `deploy/` folder में `docker compose up -d --build` चलाएँ।
6. `https://YOUR_DOMAIN/health` पर health response जाँचें। यह endpoint केवल service status दिखाता है; TTS readiness के लिए authenticated route/engine status जाँचें।

## उपलब्ध Cloud TTS
- AGNI: Piper Hindi voice model मिलने पर
- VAYU: image में espeak-ng installed है
- VAJRA और ASTRA के online providers उनके client machine से Edge TTS/ElevenLabs API के जरिए चलते हैं; यह cloud worker endpoint उन्हें local रूप में host नहीं करता।

## Security
- App container का port public host पर publish नहीं है; केवल Caddy HTTPS reverse proxy तक internal network से पहुँचा जा सकता है।
- `.env` को private रखें, token rotate करें, VPS firewall में केवल SSH/80/443 allow करें।
- `astra_data` Docker named volume में SQLite knowledge DB रहती है; नियमित encrypted backup लें।
- API ingestion के लिए अलग outbound egress firewall policy रखें; allowlist/DNS precheck अकेले DNS rebinding का पूर्ण समाधान नहीं है।
- Piper package `piper-tts==1.8.0` GPL-3.0-or-later है। Commercial distribution/embedding से पहले license obligations की समीक्षा करें।
