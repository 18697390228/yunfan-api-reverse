#!/usr/bin/env python3
"""云帆 M3 第二轮单据拉取（RO/LC/QC/OR/OC/PQ），2026-11-02。
token 只从环境变量 YF_TOKEN 读，绝不打印、绝不写文件。
基址均经 2026-11-02 实测验证（RO 须带 dateType:"1"）。
输出：~/workspace/supermarket-core/pull_20261102/doc_headers_<TYPE>.json + doc_details_<TYPE>.jsonl。
失败策略：token 失效码 → 立即停（exit 2）；429 → 立即停（exit 3）。
"""
import json, os, sys, time, urllib.parse
import requests
from datetime import datetime

TOKEN = os.environ['YF_TOKEN']
API = 'https://yunfan-api.kemai.com.cn'
OUT = os.path.expanduser('~/workspace/supermarket-core/pull_20261102')
H = {'token': TOKEN, 'loginName': '1006', 'shopAdminId': '213261',
     'merchantName': urllib.parse.quote('鲜佳超市'),
     'Content-Type': 'application/json; charset=utf-8'}
AUTH_FAIL = {'140001', '140002', '301537', '301543', '301544'}
LOG = open(os.path.join(OUT, 'progress_round2.log'), 'a', encoding='utf-8')

def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    LOG.write(line + '\n'); LOG.flush()

def post(url, body, timeout=30):
    r = requests.post(url, headers=H, json=body, timeout=timeout)
    if r.status_code == 429:
        log('RATE_LIMIT 429，立即停'); sys.exit(3)
    j = r.json()
    code = str(j.get('code', ''))
    if code in AUTH_FAIL:
        log(f'TOKEN_FAIL code={code}，立即停'); sys.exit(2)
    return j

DOC_TYPES = {
    'RO': ('/web/api/stock/purchaseOut', {'dateType': '1'}),
    'LC': ('/web/api/stock/use', {}),
    'QC': ('/web/api/stock/otherOutOrder', {}),
    'OR': ('/web/api/stock/supplierIn', {}),
    'OC': ('/web/api/stock/supplierOut', {}),
    'PQ': ('/web/api/stock/quickCheck', {}),
}
D0, D1 = '2026-08-01', '2026-11-02'
for dtype, (base, extra) in DOC_TYPES.items():
    done_flag = os.path.join(OUT, f'doc_{dtype}.done')
    if os.path.exists(done_flag):
        log(f'{dtype} 已完成，跳过'); continue
    # 列表（分页）
    headers, page = [], 1
    jl_path = os.path.join(OUT, f'doc_headers_{dtype}.jsonl')
    with open(jl_path, 'w', encoding='utf-8') as f:
        while True:
            params = {'operDateFrom': f'{D0} 00:00:00', 'operDateTo': f'{D1} 23:59:59'}
            params.update(extra)
            j = post(f'{API}{base}/getListData',
                     {'page': page, 'rows': 100, 'params': params})
            if str(j.get('code', '')) != '0':
                log(f'{dtype} 列表 page {page} code={j.get("code")} msg={j.get("msg")}，本类型记失败')
                break
            data = j.get('data', {}) or {}
            batch = data.get('results') or data.get('list') or []
            for row in batch:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            headers.extend(batch)
            log(f'{dtype} 列表 page {page}: +{len(batch)} 累计 {len(headers)}')
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.05)
    with open(os.path.join(OUT, f'doc_headers_{dtype}.json'), 'w', encoding='utf-8') as f:
        json.dump(headers, f, ensure_ascii=False)
    # 明细
    det_path = os.path.join(OUT, f'doc_details_{dtype}.jsonl')
    n_ok, n_fail = 0, 0
    with open(det_path, 'w', encoding='utf-8') as f:
        for i, hrow in enumerate(headers):
            did = hrow.get('id')
            if not did:
                n_fail += 1; continue
            try:
                j = post(f'{API}{base}/doLoadEntity', {'id': str(did)})
                if str(j.get('code', '')) == '0':
                    f.write(json.dumps({'sheetNo': hrow.get('sheetNo'), 'id': str(did),
                                        'entity': (j.get('data') or {}).get('entity')},
                                       ensure_ascii=False) + '\n')
                    n_ok += 1
                else:
                    n_fail += 1
                    log(f'{dtype} doLoadEntity {hrow.get("sheetNo")} code={j.get("code")}')
            except Exception as e:
                n_fail += 1
                log(f'{dtype} doLoadEntity {hrow.get("sheetNo")} 异常：{e}')
            if (i + 1) % 200 == 0:
                f.flush(); log(f'{dtype} 明细进度：{i+1}/{len(headers)} 成功 {n_ok} 失败 {n_fail}')
            time.sleep(0.02)
    log(f'{dtype} 完成：单据头 {len(headers)} 张，明细成功 {n_ok} 失败 {n_fail}')
    open(done_flag, 'w').write(datetime.now().isoformat())
log('第二轮全部完成')
LOG.close()
