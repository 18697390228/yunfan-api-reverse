#!/usr/bin/env python3
"""探活：PI 单据列表 + doLoadEntity 体格式确认。只打印状态与结构，不打印 token。"""
import json, requests, os, urllib.parse

TOKEN = os.environ['YF_TOKEN']
API = 'https://yunfan-api.kemai.com.cn'
H = {'token': TOKEN, 'loginName': '1006', 'shopAdminId': '213261',
     'merchantName': urllib.parse.quote('鲜佳超市'),
     'Content-Type': 'application/json; charset=utf-8'}

# 1. PI 列表（10 月，取 2 条）
r = requests.post(f'{API}/web/api/stock/purchaseIn/getListData', headers=H,
    json={'page': 1, 'rows': 2, 'params': {'operDateFrom': '2026-10-01 00:00:00',
          'operDateTo': '2026-10-31 23:59:59', 'dateType': '1'}}, timeout=20).json()
print('PI list code:', r.get('code'), 'msg:', r.get('msg'))
data = r.get('data', {})
rows = data.get('results') or data.get('list') or []
print('PI rows:', len(rows), 'data keys:', list(data.keys()) if isinstance(data, dict) else type(data))
if not rows:
    print('NO PI ROWS, stop'); raise SystemExit(0)
row = rows[0]
print('first row keys:', list(row.keys())[:20])
print('sheetNo:', row.get('sheetNo'), '| id:', row.get('id'), '| sheetId:', row.get('sheetId'))
num_id = row.get('id') or row.get('sheetId')
if not num_id:
    print('NO NUMERIC ID FOUND'); raise SystemExit(0)

# 2. doLoadEntity（体格式 {"id": num}）
for body in [{'id': num_id}]:
    r2 = requests.post(f'{API}/web/api/stock/purchaseIn/doLoadEntity', headers=H,
        json=body, timeout=20).json()
    print('doLoadEntity body', body, '-> code:', r2.get('code'), 'msg:', r2.get('msg'))
    d2 = r2.get('data', {})
    if isinstance(d2, dict):
        print('  data keys:', list(d2.keys())[:20])
        for k in ('details', 'detailList', 'items'):
            if k in d2:
                print('  details field:', k, 'len:', len(d2[k]) if isinstance(d2[k], list) else type(d2[k]))
