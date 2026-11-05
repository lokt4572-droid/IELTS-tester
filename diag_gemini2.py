import requests, time
from django.conf import settings as s

H = {'x-goog-api-key': s.GEMINI_API_KEY}
r = requests.get('https://generativelanguage.googleapis.com/v1beta/models',
                 headers=H, params={'pageSize': 100}, timeout=20)
names = [m['name'].split('/', 1)[1] for m in r.json().get('models', [])
         if 'generateContent' in m.get('supportedGenerationMethods', [])]
skip = ('image', 'tts', 'audio', 'live', 'embedding', 'robotics')
cands = [n for n in names
         if ('flash' in n or 'lite' in n) and not any(k in n for k in skip)][:5]
print('testing:', cands)

body = {
    'contents': [{'role': 'user', 'parts': [{'text':
        'Explain FALSE vs NOT GIVEN in IELTS Reading in 3 sentences.'}]}],
    'generationConfig': {'thinkingConfig': {'thinkingBudget': 0}},
}
for model in cands:
    url = ('https://generativelanguage.googleapis.com/v1beta/models/'
           + model + ':generateContent')
    out = []
    for _ in range(3):
        t = time.time()
        try:
            resp = requests.post(url, headers=H, json=body, timeout=30)
            out.append('%s/%ss' % (resp.status_code, round(time.time() - t, 1)))
        except Exception as e:
            out.append(type(e).__name__)
    print(model, '->', ', '.join(out))