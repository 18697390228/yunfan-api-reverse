#!/usr/bin/env python3
"""Round-2 探活：RO/LC/QC/OR/OC/PQ 列表调用验证。token 只走环境变量，不打印不落盘。"""
import requests, os, urllib.parse, sys

TOKEN = os.environ['YF_TOKEN']
API = 'https://yunfan-api.kemai.com.cn'
H = {'token': TOKEN, 'loginName': '1006', 'shopAdminId': '213261',
     'merchantName': urllib.parse.quote('鲜佳超市'),
     'Content-Type': 'application/json; charset=utf-8'}
AUTH_FAIL = {'140001', '140002', '301537', '301543', '301544'}

def probe(base, params, label):
    try:
        r = requests.post(f'{API}{base}/getListData', headers=H,
            json={'page': 1, 'rows': 5, 'params': params}, timeout=20).json()
    except Exception as e:
        print(f'{label}: 请求异常 {e}'); return None
    code = str(r.get('code', ''))
    if code in AUTH_FAIL:
        print(f'{label}: TOKEN_FAIL {code}，停'); sys.exit(2)
    data = r.get('data', {}) or {}
    rows = data.get('results') or data.get('list') or []
    first = rows[0] if rows else None
    info = ''
    if first:
        info = f" sheetNo={first.get('sheetNo')} id={first.get('id')} keys={list(first.keys())[:8]}"
    print(f'{label}: code={code} msg={r.get("msg")} rows={len(rows)}{info}')
    return code, len(rows)

OCT = {'operDateFrom': '2026-10-01 00:00:00', 'operDateTo': '2026-10-31 23:59:59'}
BR = '80996731'
print('--- RO /web/api/stock/purchaseOut 参数变体 ---')
for label, extra in [('plain', {}), ('+branchId', {'branchId': BR}),
                     ('+dateType', {'dateType': '1'}),
                     ('+branchId+dateType', {'branchId': BR, 'dateType': '1'})]:
    p = dict(OCT); p.update(extra)
    res = probe('/web/api/stock/purchaseOut', p, f'RO {label}')
    if res and res[0] == '0' and res[1] > 0:
        print(f'RO VERIFIED with {label}'); break
print('--- LC /web/api/stock/use ---')
for label, extra in [('plain', {}), ('+branchId', {'branchId': BR})]:
    p = dict(OCT); p.update(extra)
    res = probe('/web/api/stock/use', p, f'LC {label}')
    if res and res[0] == '0' and res[1] > 0:
        print(f'LC VERIFIED with {label}'); break
print('--- QC /web/api/stock/otherOutOrder ---')
for label, extra in [('plain', {}), ('+branchId', {'branchId': BR})]:
    p = dict(OCT); p.update(extra)
    res = probe('/web/api/stock/otherOutOrder', p, f'QC {label}')
    if res and res[0] == '0' and res[1] > 0:
        print(f'QC VERIFIED with {label}'); break
print('--- OR/OC/PQ 复核 ---')
probe('/web/api/stock/supplierIn', OCT, 'OR plain')
probe('/web/api/stock/supplierOut', OCT, 'OC plain')
probe('/web/api/stock/quickCheck', OCT, 'PQ plain')
print('探活结束')
