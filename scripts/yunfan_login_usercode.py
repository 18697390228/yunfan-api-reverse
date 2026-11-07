#!/usr/bin/env python3
"""云帆用户编码登录（M3），抓取 token。
口径见 skill login.md：loginMode=4，userCode 字段。
凭证一律走环境变量：YF_SHOP（商户号）、YF_USERCODE（用户编码）、YF_PWD（密码）。
token 只打印是否成功，不打印 token 值；如需保存由调用方决定（默认不写文件）。
"""
import json, base64, requests, cv2, numpy as np
from PIL import Image
import io, os

SHOP = os.environ.get('YF_SHOP', '')
USERCODE = os.environ.get('YF_USERCODE', '')
PWD = os.environ.get('YF_PWD', '')
API = 'https://yunfan-api.kemai.com.cn'

def solve_x(new_b64, src_b64):
    piece = np.array(Image.open(io.BytesIO(base64.b64decode(new_b64))).convert('RGBA'))
    alpha = piece[:,:,3]
    ys, xs = np.where(alpha > 10)
    y0, y1, x0, x1 = ys.min(), ys.max()+1, xs.min(), xs.max()+1
    mask_tpl = (alpha[y0:y1, x0:x1] > 10).astype(np.float32)
    bg = np.array(Image.open(io.BytesIO(base64.b64decode(src_b64))).convert('RGB'))
    white = bg.astype(np.float32).mean(axis=2) / 255.0
    res = cv2.matchTemplate(white, mask_tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    return maxloc[0] + x0, float(maxv)

d = requests.get(f'{API}/validate/initImg', timeout=15).json()['data']
x, conf = solve_x(d['newImage'], d['sourceImage'])
print(f'x={x} conf={conf:.3f}', flush=True)

r = requests.post(f'{API}/validate/checkLogin',
    json={'sliderToken': d['sliderToken'], 'x': int(x), 'y': 5}, timeout=15).json()
print('checkLogin:', r.get('code'), r.get('msg'), flush=True)
if r.get('code') != 0:
    print('FAIL_SLIDER'); raise SystemExit(1)

body = {'shopAdminId': SHOP, 'userCode': USERCODE, 'loginMode': 4,
        'password': PWD, 'webLoginCheckType': '2', 'sourcePlat': 2,
        'sliderToken': d['sliderToken'], 'x': int(x), 'y': 5}
r = requests.post(f'{API}/login', json=body, timeout=15).json()
print('login:', r.get('code'), r.get('msg'), flush=True)
if r.get('code') == 0:
    token = r['data'].get('token', '')
    print(f'LOGIN_OK token_len={len(token)}', flush=True)
    # token 只写本地文件（0600），不打印值、不进聊天记录、不进记忆
    out = os.environ.get('YF_TOKEN_OUT', os.path.expanduser('~/workspace/kemai/yf_token_189.json'))
    json.dump({'token': token, 'shopAdminId': SHOP, 'loginName': USERCODE},
              open(out, 'w'))
    os.chmod(out, 0o600)
    print(f'token saved to {out} (0600)', flush=True)
else:
    print('FAIL_LOGIN', r.get('msg'))
