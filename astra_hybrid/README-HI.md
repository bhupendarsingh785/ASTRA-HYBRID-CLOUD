# ASTRA Hybrid Local + Personal Cloud v25

यह additive subsystem चारों named voice engines को local/online execution policy देता है और browser/API/agent research के लिए reviewed knowledge hub जोड़ता है।

## चारों engine की वास्तविक व्यवस्था

| पहचान | मूल इंजन | Local | Online / Personal Cloud |
|---|---|---|---|
| VAJRA | EDGE | Indic Tiny TTS local model (अलग backend; EDGE की आवाज़ की कॉपी नहीं) | EDGE TTS online |
| AGNI | PIPER | Piper local voice model | ASTRA personal cloud पर वही Piper runtime |
| VAYU | ESPEAK | espeak-ng local | ASTRA personal cloud पर espeak-ng runtime |
| ASTRA | ELEVENLABS | licensed/consented Hindi local model (अभी install/train होना बाकी) | ElevenLabs API |

**साफ सीमा:** VAJRA और ASTRA के proprietary online voices अपने-आप local नहीं बनते। Local mode में वैकल्पिक स्वतंत्र Hindi model चलेगा। AGNI/VAYU के local runtimes को personal cloud पर भी चलाया जा सकता है। यह package self-hosted cloud worker देता है जो सही Piper/eSpeak binaries और models मिलने पर AGNI/VAYU की TTS inference कर सकता है; VPS खरीदना, DNS/HTTPS बनाना या server deploy करना यहाँ से नहीं हुआ।

## Route status

```bash
python -m astra_hybrid.cli status
python -m astra_hybrid.cli route VAJRA --mode auto
```

`auto` local-first है। उपलब्ध backend न मिले तो स्पष्ट रूप से unavailable बताता है; fake success नहीं देता।

## Personal cloud control plane

Linux/VPS पर:

```bash
export ASTRA_CLOUD_TOKEN='use-a-long-random-secret-here'
export ASTRA_CLOUD_HOST='127.0.0.1'
export ASTRA_CLOUD_PORT='8765'
python -m astra_hybrid.cloud_server
```

Internet पर खोलने से पहले HTTPS reverse proxy, firewall, backups, monitoring और secret rotation लगाएँ। SQLite database `astra_hybrid/data/knowledge_hub.sqlite3` में है। यह knowledge/control-plane के साथ AGNI (Piper) और VAYU (eSpeak) के लिए TTS endpoint भी देता है। वास्तविक render तभी होगा जब cloud machine पर संबंधित binary और voice model स्थापित हों।

Client configuration (AGNI/VAYU के लिए):

```bash
export ASTRA_CLOUD_URL='https://your-domain.example'
export ASTRA_CLOUD_TOKEN='same-long-random-secret'
```

किसी domain या cloud account को इस package ने register/deploy नहीं किया है।

## API से research data

`config/api_sources.template.json` को कॉपी करके वास्तविक API, HTTPS host allowlist और environment secret सेट करें। केवल read-only GET समर्थित है। API से मिली हर चीज़ `pending_review` में जाती है। API key को JSON, source code या ZIP में न लिखें। API provider की terms, rate limits और copyright का पालन करें।

## Browser और agent से सीखना

मौजूदा `tools/learning_fabric.py` के independent browser agents यथावत हैं। उनके research output को reviewed hub में प्रस्ताव के रूप में भेजें। Agent-to-agent exchange भी पहले pending proposal बनाता है। कोई बाहरी webpage/API/agent instruction सीधे execute नहीं होगी।

```python
from astra_hybrid.knowledge_hub import submit, propose_agent_exchange, review
rid = submit('browser', 'VAJRA-browser', 'VAJRA', 'Hindi pronunciation', 'Reviewed evidence text')
# Human review के बाद ही approved करें:
review(rid, 'approved', 'owner')
```

Approval का अर्थ curated knowledge में स्वीकार करना है, neural model weights train होना नहीं। Actual TTS fine-tuning के लिए licensed speaker-consented audio, transcripts, splits, training recipe और held-out tests अलग से जरूरी हैं।

## Safety / privacy

- Local-first routing; cloud तभी जब endpoint/credentials स्पष्ट हों।
- Raw voice recordings cloud पर स्वतः upload नहीं होते।
- API/browser/agent evidence untrusted और pending रहता है।
- No auto-code-execution, no auto-training, no silent model mutation.
- हर engine का local backend, online backend और status अलग report होता है।

## Remote TTS client

Cloud worker चालू होने और Piper/eSpeak model configure होने के बाद client machine से:

```python
from astra_hybrid.cloud_client import render_remote
render_remote("AGNI", "नमस्ते, यह मेरा निजी क्लाउड है।", "output/agni-cloud.wav")
render_remote("VAYU", "यह दूसरा ऑफलाइन इंजन है।", "output/vayu-cloud.wav")
```

VAJRA और ASTRA के cloud routes क्रमशः EDGE TTS और ElevenLabs API हैं; उनका local mode स्वतंत्र Hindi model पर आधारित है, proprietary voice की local copy नहीं।

## Cloud पर browser/API/agent evidence भेजना

```python
from astra_hybrid.cloud_client import submit_remote_knowledge
submit_remote_knowledge("browser", "VAJRA-browser", "VAJRA", "Hindi prosody", "स्रोत से जाँचा हुआ evidence")
submit_remote_knowledge("agent", "AGNI-agent", "VAYU", "phoneme", "दूसरे agent का review proposal")
```

दोनों रिकॉर्ड cloud पर `pending_review` में रहेंगे। Human approval के बाद ही curated knowledge में स्वीकार होंगे।


## v26 Advanced Hybrid Runtime
- `python -m astra_hybrid.cli status` — चारों engines की local/online readiness।
- `python -m astra_hybrid.cli route VAJRA --mode auto` — route चयन।
- `python -m astra_hybrid.cli speak AGNI "नमस्ते" --out output.wav --mode auto` — वास्तविक TTS execution।
- `python -m astra_hybrid.cli quality-report` — मानव quality ratings का सारांश।
- `ASTRA_ALLOW_CLOUD_TEXT=1` के बिना cloud पर text भेजना बंद रहेगा।
- विस्तृत सुरक्षा और deployment निर्देश `SECURITY-DEPLOYMENT-HI.md` में हैं।

**सीमा:** code-path और mocked tests पास होना वास्तविक voice inference, live API success या cloud deployment का प्रमाण नहीं है।

- `python -m astra_hybrid.cli review-knowledge RECORD_ID approved` — owner-reviewed local evidence; `--cloud` personal cloud inbox के लिए।

- `python -m astra_hybrid.cli knowledge-search "हिंदी उच्चारण" --engine AGNI` — केवल approved ज्ञान खोजें; cloud के लिए `--cloud`।


## Personal Cloud Docker template
- Docker deployment files `deploy/` में हैं: Dockerfile, Compose, Caddy HTTPS reverse proxy और `.env.example`।
- Hindi Piper model `models/hindi.onnx` तथा `models/hindi.onnx.json` अलग से रखना होगा।
- यह सिर्फ deploy template है; VPS/domain पर deploy नहीं हुआ है।
- Piper 1.8 CLI अब `python -m piper -m MODEL -f OUT.wav -- TEXT` format में invoke होता है।
