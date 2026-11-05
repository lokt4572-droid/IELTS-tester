import requests, time
from django.conf import settings as s

url = ('https://generativelanguage.googleapis.com/v1beta/models/'
       + s.GEMINI_MODEL + ':generateContent')
configs = {
    'default': None,
    'thinkingLevel=low': {'thinkingConfig': {'thinkingLevel': 'low'}},
    'thinkingLevel=minimal': {'thinkingConfig': {'thinkingLevel': 'minimal'}},
    'thinkingBudget=0': {'thinkingConfig': {'thinkingBudget': 0}},
}
question = 'Explain FALSE vs NOT GIVEN in IELTS Reading in 3 sentences.'

for name, gc in configs.items():
    body = {'contents': [{'role': 'user', 'parts': [{'text': question}]}]}
    if gc:
        body['generationConfig'] = gc
    t = time.time()
    try:
        r = requests.post(url, headers={'x-goog-api-key': s.GEMINI_API_KEY},
                          json=body, timeout=60)
    except Exception as e:
        print(name, 'ERROR', type(e).__name__)
        continue
    dt = round(time.time() - t, 1)
    if r.status_code == 200:
        data = r.json()
        parts = data['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts)
        usage = data.get('usageMetadata', {})
        print(name, 200, dt, 's | thought tokens:',
              usage.get('thoughtsTokenCount'), '| answer chars:', len(text))
    else:
        print(name, r.status_code, dt, 's |', r.text[:200].replace('\n', ' '))