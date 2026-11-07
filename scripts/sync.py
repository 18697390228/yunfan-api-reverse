#!/usr/bin/env python3
"""禹州鲜佳数据镜像 · 阿里云每日同步。
用法：
  python3 sync.py                 # 同步昨天（默认）
  python3 sync.py --date 2026-11-03
  python3 sync.py --backfill      # 首跑：2026-08-01 → 今天全量重拉（约 1–2 小时，后台跑）
凭证：只走环境变量（systemd 用 EnvironmentFile=/opt/supermarket-mirror/.env）：
  YF_SHOP=213261  YF_USERCODE=1006  YF_PWD=（密码，0600 文件，用户在服务器上自己写）
token：登录后只放内存，当次用完即丢，不写盘、不打日志。
退出码：0=拉取入库成功（对账 PASS/FAIL 写进日报，不影响退出码）；
  2=登录/token 失效；3=被限流（429，停下来等次日）。
数据口径（与本地镜像库一致，金额/数量原始值均 ×10000，入库时 ÷10000）：
  流水 /web/api/stock/report/stockinout/getListData（operDateFrom/To + branchId）
  销售 /web/api/report/builtInReport/retailSalesSummarySummary/query（groupBys=["item"]，sale_amt=毛额）
  库存 /web/api/stock/report/stock/getListData（params {"tabSwitchType":1}，分页拉空为止）
  101  /web/api/report/businessAnalysis/get101ListData（businessMonth + branchId；saleAmt=净额，refundAmt=退货）
  单据 {base}/getListData（operDateFrom/To；PI/RO 另须 dateType:"1"）+ {base}/doLoadEntity {"id": 字符串}
"""
import argparse, json, os, sqlite3, sys, time, urllib.parse
from datetime import date, timedelta
import requests

BASE_DIR = os.environ.get('MIRROR_DIR', '/opt/supermarket-mirror')
DB_PATH = os.environ.get('MIRROR_DB', os.path.join(BASE_DIR, 'mirror.db'))
API = 'https://yunfan-api.kemai.com.cn'
SHOP = os.environ.get('YF_SHOP', '213261')
BRANCH = '80996731'
AUTH_FAIL = {'140001', '140002', '301537', '301543', '301544'}

DOC_TYPES = {
    'PI': ('/web/api/stock/purchaseIn', {'dateType': '1'}),
    'PH': ('/web/api/stock/checkPlan', {}),
    'PD': ('/web/api/stock/check/input', {}),
    'TA': ('/web/api/shop/retailPrice', {}),
    'TH': ('/web/api/shop/purchasePriceChange', {}),
    'TG': ('/web/api/shop/compositePriceChange', {}),
    'CJ': ('/web/api/purchase/purchasePlanOrder', {}),
    'RO': ('/web/api/stock/purchaseOut', {'dateType': '1'}),
    'LC': ('/web/api/stock/use', {}),
    'QC': ('/web/api/stock/otherOutOrder', {}),
    'OR': ('/web/api/stock/supplierIn', {}),
    'OC': ('/web/api/stock/supplierOut', {}),
    'PQ': ('/web/api/stock/quickCheck', {}),
}

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def pick(row, *names):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return None

def fnum(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

class Yunfan:
    def __init__(self, token):
        self.h = {'token': token, 'loginName': os.environ.get('YF_USERCODE', '1006'),
                  'shopAdminId': SHOP,
                  'merchantName': urllib.parse.quote('鲜佳超市'),
                  'Content-Type': 'application/json; charset=utf-8'}

    def post(self, url, body, timeout=30):
        r = requests.post(url, headers=self.h, json=body, timeout=timeout)
        if r.status_code == 429:
            log('RATE_LIMIT 429，立即停')
            sys.exit(3)
        j = r.json()
        code = str(j.get('code', ''))
        if code in AUTH_FAIL:
            log(f'TOKEN_FAIL code={code}，立即停')
            sys.exit(2)
        return j

    def list_paginated(self, path, params, rows=1000):
        out, page = [], 1
        while True:
            j = self.post(f'{API}{path}/getListData',
                          {'page': page, 'rows': rows, 'params': params})
            if str(j.get('code', '')) != '0':
                log(f'{path} page {page} code={j.get("code")} msg={j.get("msg")}')
                break
            data = j.get('data', {}) or {}
            batch = data.get('results') or data.get('list') or []
            out.extend(batch)
            if len(batch) < rows:
                break
            page += 1
            time.sleep(0.05)
        return out

def init_db(con):
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    if os.path.exists(schema_path):
        con.executescript(open(schema_path, encoding='utf-8').read())
    else:
        # 最小建表（schema.sql 缺失时兜底，与本地库列名一致）
        con.executescript('''
        CREATE TABLE IF NOT EXISTS dwd_stock_moves (
            yunfan_row_id TEXT PRIMARY KEY, branch_id TEXT, item_code TEXT,
            sheet_type TEXT, sheet_no TEXT, business_sheet_no TEXT,
            business_sheet_type TEXT, oper_date TEXT, oper_time TEXT, qty REAL,
            cost_price REAL, cost_amt REAL, retail_price REAL, retail_amt REAL,
            balance_start_qty REAL, balance_end_qty REAL,
            balance_start_amt REAL, balance_end_amt REAL, balance_price REAL,
            inout_flag INTEGER);
        CREATE TABLE IF NOT EXISTS dwd_doc_headers (
            doc_type TEXT, doc_no TEXT, branch_id TEXT, oper_date TEXT,
            status TEXT, supplier_code TEXT, supplier_name TEXT, creator TEXT,
            create_time TEXT, approver TEXT, approve_time TEXT,
            PRIMARY KEY (doc_type, doc_no));
        CREATE TABLE IF NOT EXISTS dwd_doc_details (
            doc_type TEXT, doc_no TEXT, line_no INTEGER, item_code TEXT,
            item_name TEXT, qty REAL, price REAL, cost_price REAL, amt REAL,
            unit_name TEXT, PRIMARY KEY (doc_type, doc_no, line_no));
        CREATE TABLE IF NOT EXISTS dwd_sales_daily (
            oper_date TEXT, item_code TEXT, sale_qty REAL, sale_amt REAL,
            PRIMARY KEY (oper_date, item_code));
        CREATE TABLE IF NOT EXISTS dwd_stock_snapshot (
            snap_date TEXT, item_code TEXT, qty REAL, amt REAL,
            PRIMARY KEY (snap_date, item_code));
        CREATE TABLE IF NOT EXISTS dwd_report101 (
            business_date TEXT PRIMARY KEY, sale_amt REAL, profit_amt REAL,
            sale_cnt REAL, refund_amt REAL, stock_amt REAL, receive_amt REAL,
            minus_stock_num INTEGER, minus_profit_num INTEGER,
            zero_stock_num INTEGER);
        CREATE TABLE IF NOT EXISTS ods_raw (
            kind TEXT, day TEXT, key TEXT, raw_json TEXT,
            PRIMARY KEY (kind, day, key));
        ''')
    con.commit()

def load_moves(con, yf, d0, d1, batch):
    rows = yf.list_paginated('/web/api/stock/report/stockinout',
        {'operDateFrom': f'{d0} 00:00:00', 'operDateTo': f'{d1} 23:59:59',
         'branchId': BRANCH})
    n = 0
    for r in rows:
        od = (pick(r, 'approveTime', 'operDate', 'gmtCreate') or '')[:10]
        ot = pick(r, 'approveTime', 'gmtCreate') or ''
        con.execute("""INSERT OR REPLACE INTO dwd_stock_moves
            (yunfan_row_id, branch_id, item_code, sheet_type, sheet_no,
             business_sheet_no, business_sheet_type, oper_date, oper_time, qty,
             cost_price, cost_amt, retail_price, retail_amt,
             balance_start_qty, balance_end_qty, balance_start_amt,
             balance_end_amt, balance_price, inout_flag)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(r.get('id')), pick(r, 'branchId'), pick(r, 'itemCode', 'code'),
             pick(r, 'sheetType'), pick(r, 'sheetNo'),
             r.get('businessSheetNo'), r.get('businessSheetType'), od, ot,
             (fnum(r.get('qty')) or 0) / 10000 if r.get('qty') is not None else None,
             fnum(r.get('costPrice')) / 10000 if r.get('costPrice') is not None else None,
             fnum(r.get('costAmt')) / 10000 if r.get('costAmt') is not None else None,
             fnum(r.get('retailPrice')) / 10000 if r.get('retailPrice') is not None else None,
             fnum(r.get('retailAmt')) / 10000 if r.get('retailAmt') is not None else None,
             fnum(r.get('balanceStartQty')) / 10000 if r.get('balanceStartQty') is not None else None,
             fnum(r.get('balanceEndQty')) / 10000 if r.get('balanceEndQty') is not None else None,
             fnum(r.get('balanceStartAmt')) / 10000 if r.get('balanceStartAmt') is not None else None,
             fnum(r.get('balanceEndAmt')) / 10000 if r.get('balanceEndAmt') is not None else None,
             fnum(r.get('balancePrice')) / 10000 if r.get('balancePrice') is not None else None,
             r.get('inoutFlag')))
        n += 1
    con.commit()
    log(f'流水 {d0}→{d1}：{n} 行')
    return n

def load_sales(con, yf, d0, d1):
    j = yf.post('/web/api/report/builtInReport/retailSalesSummarySummary/query',
        {'page': 1, 'rows': 100000, 'params': {
            'code': 'retailSalesSummarySummary', 'columnList': [],
            'dynamicColumnMap': {}, 'groupBys': ['item'],
            'params': {'dateType': '1', 'gmtSaleStart': f'{d0} 00:00:00',
                       'gmtSaleEnd': f'{d1} 23:59:59', 'saleFlag': '0', 'swapFlag': '0'},
            'queryType': '3', 'reportId': '29'}})
    data = j.get('data', {}) or {}
    rows = data.get('results') or data.get('list') or []
    n = 0
    for r in rows:
        con.execute("""INSERT OR REPLACE INTO dwd_sales_daily
            (oper_date, item_code, sale_qty, sale_amt) VALUES (?,?,?,?)""",
            (d0, pick(r, 'itemCode', 'code'),
             fnum(r.get('saleQty')) / 10000 if r.get('saleQty') is not None else None,
             fnum(r.get('saleAmt')) / 10000 if r.get('saleAmt') is not None else None))
        n += 1
    con.commit()
    log(f'单品销售 {d0}→{d1}：{n} 行')
    return n

def load_stock(con, yf, snap_date):
    rows = yf.list_paginated('/web/api/stock/report/stock',
                             {'tabSwitchType': 1})
    n = 0
    for r in rows:
        con.execute("""INSERT OR REPLACE INTO dwd_stock_snapshot
            (snap_date, item_code, qty, amt) VALUES (?,?,?,?)""",
            (snap_date, pick(r, 'itemCode', 'code'),
             fnum(r.get('qty')) / 10000 if r.get('qty') is not None else None,
             fnum(r.get('stockAmt', r.get('amt'))) / 10000
             if (r.get('stockAmt') is not None or r.get('amt') is not None) else None))
        n += 1
    con.commit()
    log(f'库存快照 {snap_date}：{n} 品')
    return n

def load_101(con, yf, month):
    j = yf.post('/web/api/report/businessAnalysis/get101ListData',
                {'page': 1, 'rows': 100,
                 'params': {'businessMonth': month, 'branchId': BRANCH}})
    data = j.get('data', {}) or {}
    rows = data.get('results') or data.get('list') or []
    n = 0
    for r in rows:
        bd = f"{month}-{str(r.get('businessDate')).zfill(2)}"
        div = lambda v: fnum(v) / 10000 if v is not None else None
        con.execute("""INSERT OR REPLACE INTO dwd_report101
            (business_date, sale_amt, profit_amt, sale_cnt, refund_amt,
             stock_amt, receive_amt, minus_stock_num, minus_profit_num,
             zero_stock_num) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (bd, div(r.get('saleAmt')), div(r.get('profitAmt')),
             div(r.get('saleCnt')), div(r.get('refundAmt')),
             div(r.get('stockAmt')), div(r.get('receiveAmt')),
             r.get('minusStockItemNum'), r.get('minusProfitItemNum'),
             r.get('zorostockItemNum')))
        n += 1
    con.commit()
    log(f'101 {month}：{n} 天')
    return n

def load_docs(con, yf, d0, d1):
    total_h, total_d = 0, 0
    for dt, (base, extra) in DOC_TYPES.items():
        params = {'operDateFrom': f'{d0} 00:00:00', 'operDateTo': f'{d1} 23:59:59'}
        params.update(extra)
        headers = yf.list_paginated(base, params, rows=100)
        for h in headers:
            od = (pick(h, 'approveTime', 'createTime', 'operDate', 'gmtCreate') or '')[:10]
            con.execute("""INSERT OR REPLACE INTO dwd_doc_headers
                (doc_type, doc_no, branch_id, oper_date, status, supplier_code,
                 supplier_name, creator, create_time, approver, approve_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (dt, pick(h, 'sheetNo'), pick(h, 'branchId'), od,
                 pick(h, 'status'), pick(h, 'supplierCode'),
                 pick(h, 'supplierName'), pick(h, 'creator', 'operatorName'),
                 pick(h, 'createTime'), pick(h, 'approver'), pick(h, 'approveTime')))
            total_h += 1
            did = h.get('id')
            if not did:
                continue
            j = yf.post(f'{API}{base}/doLoadEntity', {'id': str(did)})
            if str(j.get('code', '')) == '0':
                ent = (j.get('data') or {}).get('entity') or {}
                for i, ln in enumerate(ent.get('details') or []):
                    con.execute("""INSERT OR REPLACE INTO dwd_doc_details
                        (doc_type, doc_no, line_no, item_code, item_name, qty,
                         price, cost_price, amt, unit_name)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (dt, pick(h, 'sheetNo'), i,
                         pick(ln, 'itemCode', 'code'),
                         pick(ln, 'itemName', 'name'),
                         fnum(ln.get('qty')) / 10000 if ln.get('qty') is not None else None,
                         fnum(ln.get('price')) / 10000 if ln.get('price') is not None else None,
                         fnum(ln.get('costPrice')) / 10000 if ln.get('costPrice') is not None else None,
                         fnum(ln.get('amt')) / 10000 if ln.get('amt') is not None else None,
                         pick(ln, 'unitName')))
                    total_d += 1
            time.sleep(0.02)
        con.commit()
        log(f'单据 {dt} {d0}→{d1}：{len(headers)} 张')
    log(f'单据合计：{total_h} 张 / {total_d} 行')
    return total_h, total_d

def load_items(con, yf):
    items = yf.list_paginated('/web/api/product/item', {})
    cats = yf.list_paginated('/web/api/product/category', {})
    con.execute("""CREATE TABLE IF NOT EXISTS dwd_items
        (item_code TEXT PRIMARY KEY, item_name TEXT, category_code TEXT,
         barcode TEXT, spec TEXT)""")
    for r in items:
        con.execute("""INSERT OR REPLACE INTO dwd_items
            (item_code, item_name, category_code, barcode, spec)
            VALUES (?,?,?,?,?)""",
            (pick(r, 'itemCode', 'code'), pick(r, 'itemName', 'name'),
             pick(r, 'categoryCode'), pick(r, 'barcode'),
             pick(r, 'size', 'spec')))
    con.execute("""CREATE TABLE IF NOT EXISTS dwd_categories
        (category_code TEXT PRIMARY KEY, category_name TEXT, level INTEGER)""")
    for r in cats:
        con.execute("""INSERT OR REPLACE INTO dwd_categories
            (category_code, category_name, level) VALUES (?,?,?)""",
            (pick(r, 'categoryCode', 'code'), pick(r, 'categoryName', 'name'),
             r.get('level')))
    con.commit()
    log(f'商品档案 {len(items)} / 分类 {len(cats)}')
    return len(items), len(cats)

def reconcile(con, day):
    """当日对账：销售 vs 101、流水按类型汇总、单据 vs 流水单号。返回 (PASS/FAIL, 明细行)。"""
    lines, ok = [], True
    sale = con.execute(
        "SELECT COALESCE(SUM(sale_amt),0) FROM dwd_sales_daily WHERE oper_date=?",
        (day,)).fetchone()[0]
    r101 = con.execute(
        "SELECT sale_amt, refund_amt, sale_cnt, profit_amt FROM dwd_report101 WHERE business_date=?",
        (day,)).fetchone()
    if r101 and r101[0] is not None:
        expect = (r101[0] or 0) + (r101[1] or 0)
        diff = round(sale - expect, 2)
        status = 'PASS' if abs(diff) < 0.01 else 'FAIL'
        if status == 'FAIL':
            ok = False
        lines.append(f'- 销售毛额：销售文件 {sale:.2f} vs 101（净额+退货）{expect:.2f}，差 {diff:.2f} [{status}]')
        lines.append(f'- 101 当日：净额 {r101[0]:.2f}，退货 {r101[1] or 0:.2f}，'
                     f'官方毛利 {r101[3] if r101[3] is not None else "—"}，交易笔数 {r101[2]}')
    else:
        ok = False
        lines.append(f'- 101 当日无数据（{day} 行缺失）[FAIL]')
    for row in con.execute(
            "SELECT sheet_type, COUNT(*), COALESCE(SUM(qty),0) FROM dwd_stock_moves"
            " WHERE oper_date=? GROUP BY 1 ORDER BY 2 DESC", (day,)):
        lines.append(f'- 流水 {row[0]}：{row[1]} 行，数量合计 {row[2]:.2f}')
    for row in con.execute(
            "SELECT doc_type, COUNT(*) FROM dwd_doc_headers WHERE oper_date=?"
            " GROUP BY 1 ORDER BY 2 DESC", (day,)):
        sheets = con.execute(
            "SELECT COUNT(DISTINCT sheet_no) FROM dwd_stock_moves WHERE oper_date=?"
            " AND sheet_no IN (SELECT doc_no FROM dwd_doc_headers"
            " WHERE doc_type=? AND oper_date=?)", (day, row[0], day)).fetchone()[0]
        st = 'PASS' if sheets == row[1] else 'CHECK'
        if st == 'CHECK':
            ok = False
        lines.append(f'- 单据 {row[0]}：{row[1]} 张 vs 流水单号 {sheets} 个 [{st}]')
    return ('PASS' if ok else 'FAIL'), lines

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--backfill', action='store_true')
    args = ap.parse_args()
    today = date.today().isoformat()
    day = args.date or (date.today() - timedelta(days=1)).isoformat()
    d0, d1 = ('2026-08-01', today) if args.backfill else (day, day)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yunfan_login import login
    token = login()
    if not token:
        log('同步失败：登录未成功')
        sys.exit(2)
    yf = Yunfan(token)
    os.makedirs(os.path.join(BASE_DIR, 'reports'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    init_db(con)
    log(f'开始同步 {d0} → {d1}（库 {DB_PATH}）')
    n_moves = load_moves(con, yf, d0, d1, 'daily')
    n_sales = load_sales(con, yf, d0, d1)
    n_stock = load_stock(con, yf, d1)
    n_101 = load_101(con, yf, d1[:7])
    n_h, n_d = load_docs(con, yf, d0, d1)
    n_items, n_cats = load_items(con, yf)
    con.close()
    if args.backfill:
        rep = (f'# 镜像首跑全量回填报告（{d0} → {d1}）\n\n'
               f'- 流水 {n_moves} 行，单品销售 {n_sales} 行，库存快照 {n_stock} 品，'
               f'101 {n_101} 天，单据 {n_h} 张 / {n_d} 行，'
               f'商品 {n_items} / 分类 {n_cats}\n'
               f'- 对照锚点：商品 9,278 / 分类 1,273 / 流水 258,118（8 月–11 月 2 日）/'
               f'销售 7,373 / 单据 1,949（1,795+154）/ 快照 5,201\n')
        path = os.path.join(BASE_DIR, 'reports', f'backfill-{d1}.md')
    else:
        con = sqlite3.connect(DB_PATH)
        status, lines = reconcile(con, day)
        con.close()
        rep = (f'# 镜像每日对账日报（{day}）\n\n'
               f'- 拉取：流水 {n_moves} 行，单品销售 {n_sales} 行，库存快照 {n_stock} 品，'
               f'101 {n_101} 天，单据 {n_h} 张 / {n_d} 行，商品 {n_items} / 分类 {n_cats}\n'
               f'- 对账结论：{status}\n\n' + '\n'.join(lines) + '\n')
        path = os.path.join(BASE_DIR, 'reports', f'daily-{day}.md')
    open(path, 'w', encoding='utf-8').write(rep)
    log(f'日报已写 {path}')
    log('同步完成')

if __name__ == '__main__':
    main()
