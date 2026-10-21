"""공개판용: 국립해양조사원 바다낚시지수(7일 예측)를 받아 data/fish-index.json 으로 저장.
GitHub Actions가 하루 두 번 실행(인증키는 저장소 비밀값 DATAGO_KEY — 화면·파일에 나오지 않음).
자료 출처: 국립해양조사원 바다낚시지수 (공공누리 제1유형: 출처 표시 후 자유 이용)"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

key = os.environ.get('DATAGO_KEY', '').strip()
if not key:
    sys.exit('DATAGO_KEY 비밀값이 없어요')
k = key if '%' in key else urllib.parse.quote(key, safe='')
items, page = [], 1
while page <= 10:
    q = urllib.parse.urlencode({'type': 'json', 'gubun': '갯바위', 'pageNo': page, 'numOfRows': 300})
    req = urllib.request.Request(f'https://apis.data.go.kr/1192136/fcstFishingv2/GetFcstFishingApiServicev2?serviceKey={k}&{q}', headers={'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=60).read().decode('utf-8', 'ignore')
    try:
        j = json.loads(raw)
    except ValueError:
        sys.exit('응답이 JSON이 아님: ' + raw[:200])
    body = (j.get('response') or j).get('body') or {}
    it = (body.get('items') or {}).get('item') or []
    it = it if isinstance(it, list) else [it]
    items += it
    if len(items) >= int(body.get('totalCount') or 0) or not it:
        break
    page += 1
if not items:
    sys.exit('받은 자료가 없어요')
keep = ('seafsPstnNm', 'lat', 'lot', 'predcYmd', 'predcNoonSeCd', 'seafsTgfshNm', 'totalIndex', 'tdlvHrCn')
now = datetime.now(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M')
os.makedirs('data', exist_ok=True)
with open('data/fish-index.json', 'w', encoding='utf-8') as f:
    json.dump({'t': now, 'src': '국립해양조사원 바다낚시지수(공공누리 제1유형)', 'items': [{x: i.get(x) for x in keep} for i in items]}, f, ensure_ascii=False, separators=(',', ':'))
print(f'{len(items)}건 저장 ({now})')
