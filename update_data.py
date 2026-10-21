"""공개판 자료 모으기 — GitHub Actions가 하루 두 번 실행 (06:30·17:30 한국 시각)
1. data/wx.json : 기본 포인트(항구 41곳)와 지도 색 격자의 2주 예보(Open-Meteo, 키 없음).
   사용자 브라우저마다 수백 번씩 날씨 서버를 부르지 않게(같은 와이파이·회사망은 요청 한도를 같이 씀) 한 번 모아 나눠 줌.
2. data/fish-index.json : 국립해양조사원 바다낚시지수 7일(공공누리 제1유형). 인증키는 저장소 비밀값 DATAGO_KEY — 없으면 이 단계만 건너뜀.
포인트 목록·격자 범위는 index.html 안의 STATIONS·G를 그대로 읽어 씀(한 곳에서만 고치게)."""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
html = open('index.html', encoding='utf-8').read()
os.makedirs('data', exist_ok=True)


def get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'fishing-weather (github.com/kzwp75c8yp-cpu/fishing-weather)'})
            return urllib.request.urlopen(req, timeout=90).read().decode('utf-8', 'ignore')
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(20 * (k + 1))


# ── 1. 날씨 (Open-Meteo) ──
spots = [{'id': 'bt' + bt, 'lat': float(la), 'lon': float(lo)} for bt, la, lo in re.findall(r"\{n:'[^']+',bt:(\d+),lat:([\d.]+),lon:([\d.]+)\}", html)]
g = dict((k, float(v)) for k, v in re.findall(r'(lat0|lon0|dl|rows|cols):([\d.]+)', re.search(r'const G=\{[^}]*\}', html).group(0)))
grid = [{'id': f'g{r}_{c}', 'lat': round(g['lat0'] + r * g['dl'], 3), 'lon': round(g['lon0'] + c * g['dl'], 3)}
        for r in range(int(g['rows'])) for c in range(int(g['cols']))]
OM, OMM = 'https://api.open-meteo.com/v1/forecast', 'https://marine-api.open-meteo.com/v1/marine'
q = lambda pts: 'latitude=' + ','.join(str(p['lat']) for p in pts) + '&longitude=' + ','.join(str(p['lon']) for p in pts)
lst = lambda x: x if isinstance(x, list) else [x]


def marine(pts):
    M = lst(json.loads(get(f'{OMM}?{q(pts)}&daily=wave_height_max&hourly=sea_surface_temperature&timezone=Asia%2FSeoul&forecast_days=14')))
    out = {}
    for p, m in zip(pts, M):
        if not m.get('daily'):
            continue
        sst = {}
        for t, v in zip(m['hourly']['time'], m['hourly']['sea_surface_temperature']):
            if v is not None:
                sst.setdefault(t[:10], []).append(v)
        out[p['id']] = {d: [w, round(sum(sst[d]) / len(sst[d]), 2) if d in sst else None] for d, w in zip(m['daily']['time'], m['daily']['wave_height_max'])}
    return out


def forecast(pts, full):
    v = 'wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum' + (',temperature_2m_max,temperature_2m_min,weather_code' if full else '')
    F = lst(json.loads(get(f'{OM}?{q(pts)}&daily={v}&wind_speed_unit=ms&timezone=Asia%2FSeoul&forecast_days=14')))
    out = {}
    for p, f in zip(pts, F):
        d = f.get('daily') or {}
        out[p['id']] = {t: [d[k][i] for k in v.split(',')] for i, t in enumerate(d.get('time', []))}
    return out


wx = {'ts': int(time.time() * 1000), 't': now.strftime('%m/%d %H:%M'), 'day': now.strftime('%Y-%m-%d'),
      'f': {'spot': ['wind', 'gust', 'rain', 'tmax', 'tmin', 'code', 'wave', 'sst'], 'grid': ['wave', 'sst', 'wind', 'gust', 'rain']},
      'spots': {}, 'grid': {}}
sm, sf = marine(spots), forecast(spots, True)
for p in spots:
    days = sorted(set(sf.get(p['id'], {})) | set(sm.get(p['id'], {})))
    wx['spots'][p['id']] = {d: (sf.get(p['id'], {}).get(d) or [None] * 6) + (sm.get(p['id'], {}).get(d) or [None, None]) for d in days}
time.sleep(5)
gm = marine(grid)
sea = [p for p in grid if p['id'] in gm and any(v[0] is not None for v in gm[p['id']].values())]   # 육지 칸은 파고가 없음
time.sleep(5)
gf = forecast(sea, False)
for p in sea:
    wx['grid'][p['id']] = {d: gm[p['id']][d] + (gf.get(p['id'], {}).get(d) or [None] * 3) for d in gm[p['id']]}
json.dump(wx, open('data/wx.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f"날씨: 포인트 {len(wx['spots'])}곳, 바다 칸 {len(wx['grid'])}개 ({wx['t']})")

# ── 2. 바다낚시지수 (선택) ──
key = os.environ.get('DATAGO_KEY', '').strip()
if not key:
    print('DATAGO_KEY 없음 — 바다낚시지수는 건너뜀')
    sys.exit(0)
k = key if '%' in key else urllib.parse.quote(key, safe='')
items, page = [], 1
try:
    while page <= 10:
        qs = urllib.parse.urlencode({'type': 'json', 'gubun': '갯바위', 'pageNo': page, 'numOfRows': 300})
        raw = get(f'https://apis.data.go.kr/1192136/fcstFishingv2/GetFcstFishingApiServicev2?serviceKey={k}&{qs}')
        body = (json.loads(raw).get('response') or {}).get('body') or json.loads(raw).get('body') or {}
        it = lst((body.get('items') or {}).get('item') or [])
        items += it
        if len(items) >= int(body.get('totalCount') or 0) or not it:
            break
        page += 1
except Exception as e:
    print('바다낚시지수 받기 실패(해외 서버 차단일 수 있음):', str(e)[:150])
    sys.exit(0)   # 날씨 파일은 그대로 올라가게 실패로 끝내지 않음
# 지점별로 묶어 크기 줄이기: places[이름] = [위도, 경도, {날짜|오전오후: {대상어: 지수}}]
places = {}
for i in items:
    p = places.setdefault(i['seafsPstnNm'], [i['lat'], i['lot'], {}])
    p[2].setdefault(f"{i['predcYmd']}|{i['predcNoonSeCd']}", {})[i['seafsTgfshNm']] = i['totalIndex']
json.dump({'t': now.strftime('%m/%d %H:%M'), 'src': '국립해양조사원 바다낚시지수(공공누리 제1유형)', 'places': places},
          open('data/fish-index.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'바다낚시지수: {len(items)}건, 지점 {len(places)}곳')
