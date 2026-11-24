import json, time, urllib.request as u
from django.conf import settings as s
for m in ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]:
    t = time.time()
    cuerpo = json.dumps({"model": m, "messages": [{"role": "user", "content": "Responde JSON {\"ok\":true}"}], "response_format": {"type": "json_object"}}).encode()
    r = u.Request(s.GUIOS_AI_BASE_URL + "/chat/completions", data=cuerpo, headers={"Authorization": "Bearer " + s.GUIOS_AI_API_KEY, "Content-Type": "application/json"})
    try:
        u.urlopen(r, timeout=90).read()
        print(m, "OK", round(time.time() - t, 1), "s")
    except Exception as e:
        print(m, "FALLA", repr(e))