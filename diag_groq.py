import requests
from django.conf import settings as s

SYSTEM = (
    "You are an IELTS Writing examiner. Return ONLY valid JSON like: "
    '{"criteria":{"task_response":{"band":0,"comment":""},'
    '"coherence_cohesion":{"band":0,"comment":""},'
    '"lexical_resource":{"band":0,"comment":""},'
    '"grammatical_range_accuracy":{"band":0,"comment":""}}} '
    "Bands are numbers from 0 to 9 in steps of 0.5."
)
ESSAY = ("Some people think technology make life easier. I agree because "
         "technology help people. For example phones is useful. "
         "In conclusion technology is good.")

for max_tokens in (2000, 6000):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": "Bearer " + s.GROQ_API_KEY},
        json={
            "model": s.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": ESSAY},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    print("--- max_tokens", max_tokens, "| model", s.GROQ_MODEL, "| status", r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
        continue
    d = r.json()
    choice = d["choices"][0]
    msg = choice["message"]
    print("finish_reason:", choice.get("finish_reason"))
    print("usage:", d.get("usage"))
    print("content:", repr((msg.get("content") or "")[:800]))
    print("reasoning length:", len(msg.get("reasoning") or ""))