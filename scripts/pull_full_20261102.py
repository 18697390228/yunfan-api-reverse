#!/usr/bin/env python3
"""云帆 M3 禹州鲜佳全量拉取（镜像系统 phase 1），2026-11-02 启动。
- token 只从环境变量 YF_TOKEN 读，绝不打印、绝不写文件、绝不进日志。
- headers：token + loginName=1006（用户编码登录）+ shopAdminId=213261 + 商户名。
- 输出：~/workspace/supermarket-core/pull_20261102/（.jsonl 增量落盘 + 阶段完成转 .json）。
- 断点：每阶段完成写 .done，重跑跳过已完成阶段。
- 失败策略：token 失效码 → 立即停（exit 2）；429 → 立即停（exit 3）；单项失败记 log 继续。
- 节流：顺序调用，页间 0.05s，单据明细 0.02s，不并发（不给用户在线会话添负担）。
"""
import json, os, sys, time, urllib.parse
from datetime import datetime
import requests

TOKEN = os.environ['YF_TOKEN']
API = 'https://yunfan-api.kemai.com.cn'
BRANCH = '80996731'
OUT = os.path.expanduser('~/workspace/supermarket-core/pull_20261102')
os.makedirs(OUT, exist_ok=True)

H = {'token': TOKEN, 'loginName': '1006', 'shopAdminId': '213261',
     'merchantName': urllib.parse.quote('鲜佳超市'),
     'Content-Type': 'application/json; charset=utf-8'}
AUTH_FAIL = {'140001', '140002', '301537', '301543', '301544'}
LOG = open(os.path.join(OUT, 'progress.log'), 'a', encoding='utf-8')

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
        log(f'TOKEN_FAIL code={code}，立即停（不自动重登，不顶用户会话）'); sys.exit(2)
    return j

def paged(url, body_fn, rows_key='results', rows=1000, label=''):
    """通用分页：body_fn(page) -> body；返回全部行列表；每页增量写 .jsonl。"""
    out_jsonl = os.path.join(OUT, f'{label}.jsonl')
    all_rows, page = [], 1
    with open(out_jsonl, 'w', encoding='utf-8') as f:
        while True:
            j = post(url, body_fn(page, rows))
            if str(j.get('code', '')) != '0':
                log(f'{label} page {page} code={j.get("code")} msg={j.get("msg")}，本阶段记失败继续下一阶段')
                return all_rows, False
            data = j.get('data', {}) or {}
            batch = data.get(rows_key) or data.get('list') or []
            for row in batch:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            all_rows.extend(batch)
            log(f'{label} page {page}: +{len(batch)} 累计 {len(all_rows)}')
            if len(batch) < rows:
                break
            page += 1
            time.sleep(0.05)
    with open(os.path.join(OUT, f'{label}.json'), 'w', encoding='utf-8') as f:
        json.dump(all_rows, f, ensure_ascii=False)
    return all_rows, True

def done(phase):
    open(os.path.join(OUT, f'{phase}.done'), 'w').write(datetime.now().isoformat())

def is_done(phase):
    return os.path.exists(os.path.join(OUT, f'{phase}.done'))

def month_range(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last = (datetime(nm[0], nm[1], 1) - datetime(y, m, 1)).days
    return f'{ym}-01', f'{ym}-{last:02d}'

MONTHS = ['2026-08', '2026-09', '2026-10', '2026-11']
TODAY = '2026-11-02'

# ---------- 1. 主数据 ----------
if not is_done('items'):
    rows, ok = paged(f'{API}/web/api/product/item/getListData',
        lambda p, r: {'page': p, 'rows': r, 'params': {}}, label='items')
    log(f'items 完成：{len(rows)} 条 ok={ok}'); done('items') if ok else None
if not is_done('categories'):
    rows, ok = paged(f'{API}/web/api/product/category/getListData',
        lambda p, r: {'page': p, 'rows': r, 'params': {}}, label='categories')
    log(f'categories 完成：{len(rows)} 条 ok={ok}'); done('categories') if ok else None

# ---------- 2. 出入库流水（分月） ----------
for ym in MONTHS:
    d0, d1 = month_range(ym)
    if ym == '2026-11': d1 = TODAY
    ph = f'stockinout_{ym}'
    if is_done(ph): continue
    rows, ok = paged(f'{API}/web/api/stock/report/stockinout/getListData',
        lambda p, r, d0=d0, d1=d1: {'page': p, 'rows': r, 'params': {
            'operDateFrom': f'{d0} 00:00:00', 'operDateTo': f'{d1} 23:59:59',
            'branchId': BRANCH}}, label=ph)
    log(f'{ph} 完成：{len(rows)} 行 ok={ok}'); done(ph) if ok else None

# ---------- 3. 单品销售（分月，groupBys=["item"]） ----------
for ym in MONTHS:
    d0, d1 = month_range(ym)
    if ym == '2026-11': d1 = TODAY
    ph = f'sales_{ym}'
    if is_done(ph): continue
    def sales_body(p, r, d0=d0, d1=d1):
        return {'page': p, 'rows': r, 'params': {
            'code': 'retailSalesSummarySummary',
            'columnList': ['index', 'item_barcode', 'item_name', 'sale_qty', 'unit_name', 'sale_amt'],
            'dynamicColumnMap': {}, 'groupBys': ['item'],
            'params': {'dateType': '1', 'gmtSaleStart': f'{d0} 00:00:00',
                       'gmtSaleEnd': f'{d1} 23:59:59', 'saleFlag': '0', 'swapFlag': '0'},
            'queryType': '3', 'reportId': '29'}}
    rows, ok = paged(f'{API}/web/api/report/builtInReport/retailSalesSummarySummary/query',
        sales_body, label=ph)
    log(f'{ph} 完成：{len(rows)} 行 ok={ok}'); done(ph) if ok else None

# ---------- 4. 当前库存快照 ----------
if not is_done('stock_snapshot'):
    rows, ok = paged(f'{API}/web/api/stock/report/stock/getListData',
        lambda p, r: {'page': p, 'rows': r, 'params': {'tabSwitchType': 1}}, label='stock_snapshot')
    log(f'stock_snapshot 完成：{len(rows)} 条 ok={ok}'); done('stock_snapshot') if ok else None

# ---------- 5. 101 日报（分月） ----------
for ym in MONTHS:
    ph = f'report101_{ym}'
    if is_done(ph): continue
    rows, ok = paged(f'{API}/web/api/report/businessAnalysis/get101ListData',
        lambda p, r, ym=ym: {'page': p, 'rows': r, 'params': {
            'businessMonth': ym, 'branchId': BRANCH}}, label=ph)
    log(f'{ph} 完成：{len(rows)} 行 ok={ok}'); done(ph) if ok else None

# ---------- 6. 单据头 + 明细 ----------
DOC_TYPES = {
    'PI': '/web/api/stock/purchaseIn',
    'PH': '/web/api/stock/checkPlan',
    'PD': '/web/api/stock/check/input',
    'TA': '/web/api/shop/retailPrice',
    'TH': '/web/api/shop/purchasePriceChange',
    'TG': '/web/api/shop/compositePriceChange',
    'CJ': '/web/api/purchase/purchasePlanOrder',
}
D0, D1 = '2026-08-01', TODAY
for dtype, base in DOC_TYPES.items():
    ph = f'doc_{dtype}'
    if is_done(ph): continue
    def doc_body(p, r):
        params = {'operDateFrom': f'{D0} 00:00:00', 'operDateTo': f'{D1} 23:59:59'}
        if dtype == 'PI': params['dateType'] = '1'
        return {'page': p, 'rows': r, 'params': params}
    headers, ok = paged(f'{API}{base}/getListData', doc_body, rows=100, label=f'doc_headers_{dtype}')
    log(f'{dtype} 单据头：{len(headers)} 张 ok={ok}')
    if not ok:
        continue
    # 明细：逐单 doLoadEntity（id 为字符串原样传）
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
            except Exception as e:
                n_fail += 1
                log(f'{dtype} doLoadEntity {hrow.get("sheetNo")} 异常：{e}')
            if (i + 1) % 200 == 0:
                f.flush(); log(f'{dtype} 明细进度：{i+1}/{len(headers)} 成功 {n_ok} 失败 {n_fail}')
            time.sleep(0.02)
    log(f'{dtype} 明细完成：成功 {n_ok} 失败 {n_fail}'); done(ph)

# ---------- 7. 未知单据类型探活（只记结果，不写业务数据） ----------
PROBES = {
    'RO': ['/web/api/stock/purchaseReturn', '/web/api/stock/purchaseOut'],
    'LC': ['/web/api/stock/requisition', '/web/api/stock/materialRequisition'],
    'QC': ['/web/api/stock/otherOut', '/web/api/stock/miscellaneousOut'],
    'OR': ['/web/api/stock/supplierIn', '/web/api/stock/supplierTransferIn'],
    'OC': ['/web/api/stock/supplierOut', '/web/api/stock/supplierTransferOut'],
    'PQ': ['/web/api/stock/check/fastCheck', '/web/api/stock/quickCheck'],
    'TO': ['/web/api/stock/transfer', '/web/api/stock/allocation'],
}
probe_out = {}
for dtype, bases in PROBES.items():
    for base in bases:
        try:
            j = post(f'{API}{base}/getListData',
                {'page': 1, 'rows': 5, 'params': {'operDateFrom': '2026-10-01 00:00:00',
                 'operDateTo': '2026-10-31 23:59:59'}})
            data = j.get('data', {}) or {}
            n = len(data.get('results') or data.get('list') or [])
            probe_out[f'{dtype}:{base}'] = {'code': j.get('code'), 'rows': n}
            log(f'PROBE {dtype} {base} -> code={j.get("code")} rows={n}')
        except Exception as e:
            probe_out[f'{dtype}:{base}'] = {'error': str(e)}
            log(f'PROBE {dtype} {base} 异常：{e}')
with open(os.path.join(OUT, 'probe_results.json'), 'w', encoding='utf-8') as f:
    json.dump(probe_out, f, ensure_ascii=False, indent=1)
log('全部阶段完成')
LOG.close()
