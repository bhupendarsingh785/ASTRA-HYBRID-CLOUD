# ASTRA HYBRID v26 — Advanced Runtime Update

यह v25 पर additive update है। चारों engines (VAJRA, AGNI, VAYU, ASTRA) के लिए वास्तविक local/online synthesis runner, privacy-consent gate, सीमित fallback, safer API ingestion, cloud review endpoint और voice-quality feedback ledger जोड़ा गया है।

## प्रमुख बदलाव
1. Router अब केवल route बताने तक सीमित नहीं: `tts_runtime.synthesize()` selected provider चलाता है, output को validate/atomically save करता है और अनुमति होने पर ही fallback करता है।
2. Cloud text transfer default रूप से बंद है; `ASTRA_ALLOW_CLOUD_TEXT=1` explicit operator consent है।
3. API ingestion exact allowlisted HTTPS host, redirect rejection, JSON content type, response-size limit और DNS public-IP precheck करता है। Production में egress firewall अभी भी जरूरी है।
4. Cloud server में 32-character token requirement, loopback-only default bind, concurrent TTS cap और human knowledge review endpoint है।
5. Quality feedback पांच dimensions पर ratings रखता है; auto-training नहीं करता।
6. Approved knowledge को engine/topic के अनुसार local या personal cloud से खोजकर retrieval में उपयोग किया जा सकता है।
7. Owner CLI से local या cloud knowledge proposal को approve/reject कर सकता है।
6. ASTRA local voice को operator-configured adapter से जोड़ा जा सकता है; यह model weights के साथ bundled नहीं है।

## चारों engines
- VAJRA: local Indic Tiny TTS / online Edge TTS
- AGNI: local Piper / personal cloud Piper
- VAYU: local eSpeak NG / personal cloud eSpeak NG
- ASTRA: operator local adapter / online ElevenLabs API

## स्पष्ट सीमाएँ
यह update deploy किया हुआ VPS, API credentials, local model weights या trained personal voice नहीं देता। Provider integration को वास्तविक उपयोग से पहले credentials/models के साथ smoke-test करना होगा। DNS precheck alone DNS-rebinding-proof नहीं है; production egress firewall आवश्यक है।
