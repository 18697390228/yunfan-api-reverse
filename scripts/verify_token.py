#!/usr/bin/env python3
"""验证 token：读本地 token 文件，调一次库存接口，只打印状态与条数，不打印 token。"""
import json, requests, os

tok = json.load(open(os.path.expanduser('~/workspace/kemai/yf_token_189.json')))
API = 'https://yunfan-api.kemai.com.cn'
h = {'token': tok['token'], 'loginName': tok['loginName'],
     'shopAdminId': tok['shopAdminId']}
r = requests.post(f'{API}/web/api/stock/report/stock/getListData',
    headers=h,
    json={'page': 1, 'rows': 1, 'params': {'tabSwitchType': 1}},
    timeout=20).json()
print('code:', r.get('code'), 'msg:', r.get('msg'))
data = r.get('data', {})
print('data keys:', list(data.keys()) if isinstance(data, dict) else type(data))
lst = data.get('results') or data.get('list') or data.get('records') or []
if isinstance(lst, list) and lst:
    print('rows returned:', len(lst))
    print('first item code:', lst[0].get('itemCode'), 'name:', lst[0].get('itemName'))
else:
    print('total field:', data.get('total'), 'rows field:', data.get('rows'))
