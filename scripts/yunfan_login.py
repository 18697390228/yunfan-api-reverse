#!/usr/bin/env python3
"""云帆登录模块（供每日同步用）。
凭证只走环境变量：
  YF_SHOP（商户号，默认 213261）
  YF_LOGIN_MODE（1=账号登录，4=用户编码登录，默认 4）
  YF_ACCOUNT（账号登录用，手机号/账号）
  YF_USERCODE（用户编码登录用，默认 1006）
  YF_PWD（密码，必填）
token 只返回给调用方（内存），不打印、不写文件、不进日志。
滑块最多试 3 次（每次重新取图），3 次不过返回 None。
注意：301544（会话冲突）时不自动加 continueLogin 顶号，须用户明确授权才顶。
依赖：requests、opencv-python（cv2）、numpy、Pillow（Ubuntu 上用 apt 装 python3-requests python3-opencv python3-numpy python3-pil）。
"""
import base64, io, os
import requests
import cv2
import numpy as np
from PIL import Image

API = 'https://yunfan-api.kemai.com.cn'
SHOP = os.environ.get('YF_SHOP', '213261')
LOGIN_MODE = int(os.environ.get('YF_LOGIN_MODE', '4'))
ACCOUNT = os.environ.get('YF_ACCOUNT', '')
USERCODE = os.environ.get('YF_USERCODE', '1006')
PWD = os.environ.get('YF_PWD', '')

def login_name():
    return ACCOUNT if LOGIN_MODE == 1 else USERCODE

def _solve_x(new_b64, src_b64):
    piece = np.array(Image.open(io.BytesIO(base64.b64decode(new_b64))).convert('RGBA'))
    alpha = piece[:, :, 3]
    ys, xs = np.where(alpha > 10)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    mask_tpl = (alpha[y0:y1, x0:x1] > 10).astype(np.float32)
    bg = np.array(Image.open(io.BytesIO(base64.b64decode(src_b64))).convert('RGB'))
    white = bg.astype(np.float32).mean(axis=2) / 255.0
    res = cv2.matchTemplate(white, mask_tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    return maxloc[0] + x0, float(maxv)

def login(max_try=3):
    """返回 token 字符串；失败返回 None（不抛错，由调用方决定退出码）。"""
    if not PWD:
        print('LOGIN_FAIL: YF_PWD 未设置', flush=True)
        return None
    for attempt in range(1, max_try + 1):
        try:
            d = requests.get(f'{API}/validate/initImg', timeout=15).json()['data']
            x, conf = _solve_x(d['newImage'], d['sourceImage'])
            r = requests.post(f'{API}/validate/checkLogin',
                json={'sliderToken': d['sliderToken'], 'x': int(x), 'y': 5},
                timeout=15).json()
            if r.get('code') != 0:
                print(f'LOGIN_FAIL: 滑块第 {attempt} 次未通过 ({r.get("msg")})', flush=True)
                continue
            body = {'shopAdminId': SHOP, 'loginMode': LOGIN_MODE,
                    'password': PWD, 'webLoginCheckType': '2', 'sourcePlat': 2,
                    'sliderToken': d['sliderToken'], 'x': int(x), 'y': 5}
            if os.environ.get('YF_CONTINUE_LOGIN') == '1':
                body['continueLogin'] = 1
            if LOGIN_MODE == 1:
                body['username'] = ACCOUNT
            else:
                body['userCode'] = USERCODE
            r = requests.post(f'{API}/login', json=body, timeout=15).json()
            if r.get('code') == 0:
                token = r['data'].get('token', '')
                print(f'LOGIN_OK (第 {attempt} 次，token 长度 {len(token)})', flush=True)
                return token
            if str(r.get('code')) == '301544':
                print('LOGIN_FAIL: 301544 会话冲突（对方会话在线），未开顶号开关，不自动顶号', flush=True)
                return None
            print(f'LOGIN_FAIL: 第 {attempt} 次登录失败 ({r.get("msg")})', flush=True)
        except Exception as e:
            print(f'LOGIN_FAIL: 第 {attempt} 次异常 {e}', flush=True)
    return None
