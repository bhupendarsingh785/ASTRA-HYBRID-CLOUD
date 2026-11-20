# ASTRA HYBRID v26 — Patch लगाने का तरीका

यह ZIP केवल **Hybrid Local + Personal Cloud subsystem** है; पूरा ASTRA master model नहीं है। इसमें `astra_hybrid/`, `deploy/`, `models/` और hybrid tests हैं।

1. पहले अपना मौजूदा ASTRA project और v25 Hybrid folder का backup लें।
2. ZIP को ASTRA project के root folder में extract करें और existing files overwrite होने दें। इससे `astra_hybrid/` के v26 files replace/add होंगे।
3. Python environment में tests चलाएँ: `PYTHONPATH=. pytest -q tests/test_astra_hybrid.py tests/test_astra_hybrid_v26.py`
4. Runtime readiness देखें: `PYTHONPATH=. python -m astra_hybrid.cli status`
5. Personal Cloud के लिए `deploy/README-HI.md` पढ़ें। VPS/domain और अपना secret token आपको स्वयं configure करना होगा।

**जरूरी:** v26 का Hybrid subsystem आपके ASTRA master के SWAR v24 package पर निर्भर है, क्योंकि VAJRA local runner `swar.tools.tiny_tts_render` उपयोग करता है। यह ZIP SWAR model weights या पूरे ASTRA master को शामिल नहीं करता।
