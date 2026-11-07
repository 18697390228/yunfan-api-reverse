#!/usr/bin/env python3
"""禹州鲜佳数据镜像 · 本机每日同步（跑在助手电脑上）。
用法（用 ~/workspace/kemai/venv/bin/python 运行）：
  python3 sync_local.py                 # 补跑：从上次成功日 +1 天 → 昨天，逐天跑
  python3 sync_local.py --date 2026-11-03
  python3 sync_local.py --reconcile-only 2026-11-03   # 不登录，只对账写日报
凭证：~/workspace/supermarket-mirror/.env（0600，只给同步程序读），内容：
  YF_SHOP=213261
  YF_USERCODE=1006
  YF_PWD=（密码）
token：登录后只放内存，当次用完即丢，不写盘、不打日志。
库：~/workspace/supermarket-core/mirror_full.db（与本地全量库同一套表结构 v2.1，ods + dwd 双写）。
断点：sync_state 表记 last_ok_date；某天拉取入库成功即更新（对账 PASS/FAIL 不影响断点，只影响日报结论）。
退出码：0=成功；2=登录/token 失效；3=限流；4=.env 缺失或权限不对。
"""
import argparse, json, os, sqlite3, sys, time, urllib.parse
from datetime import date, timedelta
import requests

MIRROR_HOME = os.path.expanduser('~/workspace/supermarket-mirror')
DB_PATH = os.path.expanduser('~/workspace/supermarket-core/mirror_full.db')
ENV_PATH = os.path.join(MIRROR_HOME, '.env')
REPORT_DIR = os.path.join(MIRROR_HOME, 'reports')
API = 'https://yunfan-api.kemai.com.cn'
SHOP = '213261'
BRANCH = '80996731'
AUTH_FAIL = {'140001', '140002', '301537', '301543', '301544'}
SEED_LAST_OK = '2026-11-01'

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

def load_env():
    if not os.path.exists(ENV_PATH):
        log(f'.env 缺失：{ENV_PATH}')
        sys.exit(4)
    mode = os.stat(ENV_PATH).st_mode & 0o777
    if mode & 0o077:
        log(f'.env 权限不对（{oct(mode)}，须 0600），拒绝使用')
        sys.exit(4)
    for line in open(ENV_PATH, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
    if not os.environ.get('YF_PWD'):
        log('.env 里没有 YF_PWD')
        sys.exit(4)

class Yunfan:
    def __init__(self, token):
        mode = os.environ.get('YF_LOGIN_MODE', '4')
        login_name = os.environ.get('YF_ACCOUNT') if mode == '1' else os.environ.get('YF_USERCODE', '1006')
        self.h = {'token': token, 'loginName': login_name,
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
    con.execute("""CREATE TABLE IF NOT EXISTS dwd_report101 (
        business_date TEXT PRIMARY KEY, sale_amt REAL, profit_amt REAL,
        sale_cnt REAL, refund_amt REAL, stock_amt REAL, receive_amt REAL,
        minus_stock_num INTEGER, minus_profit_num INTEGER,
        zero_stock_num INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY, value TEXT)""")
    con.commit()

def sync_day(con, yf, day):
    """同步一整天：拉数 → ods+dwd 入库。返回 (counts, reconcile_lines, status)。"""
    batch = f'daily-{day}'
    d0 = d1 = day
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    # 流水
    rows = yf.list_paginated('/web/api/stock/report/stockinout',
        {'operDateFrom': f'{d0} 00:00:00', 'operDateTo': f'{d1} 23:59:59',
         'branchId': BRANCH})
    n_moves = 0
    for r in rows:
        od = (pick(r, 'approveTime', 'operDate', 'gmtCreate') or '')[:10]
        con.execute("""INSERT OR REPLACE INTO ods_stock_moves
            (yunfan_row_id, branch_id, item_code, item_name, sheet_type, sheet_no,
             business_sheet_no, business_sheet_type, approve_time, qty_raw,
             cost_price_raw, cost_amt_raw, retail_price_raw, retail_amt_raw,
             balance_start_qty_raw, balance_end_qty_raw, balance_start_amt_raw,
             balance_end_amt_raw, balance_price_raw, inout_flag, unit_name,
             store_name, import_batch, import_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(r.get('id')), pick(r, 'branchId'), pick(r, 'itemCode'),
             pick(r, 'itemName'), pick(r, 'sheetType'), pick(r, 'sheetNo'),
             r.get('businessSheetNo'), r.get('businessSheetType'),
             pick(r, 'approveTime'), fnum(r.get('qty')), fnum(r.get('costPrice')),
             fnum(r.get('costAmt')), fnum(r.get('retailPrice')),
             fnum(r.get('retailAmt')), fnum(r.get('balanceStartQty')),
             fnum(r.get('balanceEndQty')), fnum(r.get('balanceStartAmt')),
             fnum(r.get('balanceEndAmt')), fnum(r.get('balancePrice')),
             r.get('inoutFlag'), pick(r, 'unitName'), pick(r, 'storeName'),
             batch, now))
        con.execute("""INSERT OR REPLACE INTO dwd_stock_moves
            (yunfan_row_id, branch_id, item_code, sheet_type, sheet_no,
             business_sheet_no, business_sheet_type, oper_date, oper_time, qty,
             cost_price, cost_amt, retail_price, retail_amt,
             balance_start_qty, balance_end_qty, balance_start_amt,
             balance_end_amt, balance_price, inout_flag)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(r.get('id')), pick(r, 'branchId'), pick(r, 'itemCode'),
             pick(r, 'sheetType'), pick(r, 'sheetNo'),
             r.get('businessSheetNo'), r.get('businessSheetType'), od,
             pick(r, 'approveTime'),
             fnum(r.get('qty')) / 10000 if r.get('qty') is not None else None,
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
        n_moves += 1
    con.commit()
    log(f'[{day}] 流水 {n_moves} 行')
    # 单品销售（snake_case 字段）
    j = yf.post(f'{API}/web/api/report/builtInReport/retailSalesSummarySummary/query',
        {'page': 1, 'rows': 100000, 'params': {
            'code': 'retailSalesSummarySummary', 'columnList': [],
            'dynamicColumnMap': {}, 'groupBys': ['item'],
            'params': {'dateType': '1', 'gmtSaleStart': f'{d0} 00:00:00',
                       'gmtSaleEnd': f'{d1} 23:59:59', 'saleFlag': '0', 'swapFlag': '0'},
            'queryType': '3', 'reportId': '29'}})
    data = j.get('data', {}) or {}
    srows = data.get('results') or data.get('list') or []
    n_sales = 0
    for r in srows:
        ic = pick(r, 'item_code', 'itemCode', 'code')
        sq = fnum(pick(r, 'sale_qty', 'saleQty'))
        sa = fnum(pick(r, 'sale_amt', 'saleAmt'))
        con.execute("""INSERT OR REPLACE INTO ods_sales_daily
            (branch_id, item_code, sale_date, sale_qty_raw, sale_amt_raw,
             import_batch) VALUES (?,?,?,?,?,?)""",
            (BRANCH, ic, day, sq, sa, batch))
        con.execute("""INSERT OR REPLACE INTO dwd_sales_daily
            (branch_id, item_code, sale_date, sale_qty, return_qty, net_qty,
             sale_amt, return_amt, net_amt, order_count, vip_amt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (BRANCH, ic, day,
             sq / 10000 if sq is not None else None,
             fnum(pick(r, 'return_qty', 'returnQty')) / 10000
                 if pick(r, 'return_qty', 'returnQty') is not None else 0,
             (sq - (fnum(pick(r, 'return_qty', 'returnQty')) or 0)) / 10000
                 if sq is not None else None,
             sa / 10000 if sa is not None else None,
             fnum(pick(r, 'return_amt', 'returnAmt')) / 10000
                 if pick(r, 'return_amt', 'returnAmt') is not None else 0,
             (sa - (fnum(pick(r, 'return_amt', 'returnAmt')) or 0)) / 10000
                 if sa is not None else None,
             fnum(pick(r, 'order_count', 'orderCount')) / 10000
                 if pick(r, 'order_count', 'orderCount') is not None else None,
             fnum(pick(r, 'vip_sales_subtotal_amt', 'vipAmt')) / 10000
                 if pick(r, 'vip_sales_subtotal_amt', 'vipAmt') is not None else None))
        n_sales += 1
    con.commit()
    log(f'[{day}] 单品销售 {n_sales} 行')
    # 库存快照（以当日为快照日）
    srows = yf.list_paginated('/web/api/stock/report/stock', {'tabSwitchType': 1})
    n_stock = 0
    for r in srows:
        ic = pick(r, 'itemCode', 'code')
        q = fnum(r.get('qty'))
        ca = fnum(r.get('costAmt'))
        con.execute("""INSERT OR REPLACE INTO ods_stock_snapshot
            (branch_id, item_code, snapshot_date, qty_raw, cost_amt_raw,
             retail_price_raw, unit_name, import_batch)
            VALUES (?,?,?,?,?,?,?,?)""",
            (BRANCH, ic, day, q, ca, fnum(r.get('retailPrice')),
             pick(r, 'unitName'), batch))
        con.execute("""INSERT OR REPLACE INTO dwd_stock_snapshot
            (branch_id, item_code, snapshot_date, qty, cost_amt, unit_cost,
             retail_price) VALUES (?,?,?,?,?,?,?)""",
            (BRANCH, ic, day,
             q / 10000 if q is not None else None,
             ca / 10000 if ca is not None else None,
             (ca / q) if (q and ca) else None,
             fnum(r.get('retailPrice')) / 10000 if r.get('retailPrice') is not None else None))
        n_stock += 1
    con.commit()
    log(f'[{day}] 库存快照 {n_stock} 品')
    # 101（当月）
    month = day[:7]
    j = yf.post(f'{API}/web/api/report/businessAnalysis/get101ListData',
                {'page': 1, 'rows': 100,
                 'params': {'businessMonth': month, 'branchId': BRANCH}})
    data = j.get('data', {}) or {}
    irows = data.get('results') or data.get('list') or []
    n_101 = 0
    div = lambda v: fnum(v) / 10000 if v is not None else None
    for r in irows:
        bd = f"{month}-{str(r.get('businessDate')).zfill(2)}"
        con.execute("""INSERT OR REPLACE INTO dwd_report101
            (business_date, sale_amt, profit_amt, sale_cnt, refund_amt,
             stock_amt, receive_amt, minus_stock_num, minus_profit_num,
             zero_stock_num) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (bd, div(r.get('saleAmt')), div(r.get('profitAmt')),
             div(r.get('salePayCnt')), div(r.get('refundAmt')),
             div(r.get('stockAmt')), div(r.get('receiveAmt')),
             r.get('minusStockItemNum'), r.get('minusProfitItemNum'),
             r.get('zorostockItemNum')))
        n_101 += 1
    con.commit()
    log(f'[{day}] 101 {month}：{n_101} 天')
    # 单据
    n_h, n_d = 0, 0
    for dt, (base, extra) in DOC_TYPES.items():
        params = {'operDateFrom': f'{d0} 00:00:00', 'operDateTo': f'{d1} 23:59:59'}
        params.update(extra)
        headers = yf.list_paginated(base, params, rows=100)
        for h in headers:
            od = (pick(h, 'approveTime', 'createTime', 'operDate', 'gmtCreate') or '')[:10]
            con.execute("""INSERT OR REPLACE INTO ods_doc_headers
                (doc_type, doc_no, branch_id, oper_date, status, supplier_code,
                 supplier_name, creator, create_time, approver, approve_time,
                 yunfan_id, raw_json, import_batch)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (dt, pick(h, 'sheetNo'), pick(h, 'branchId'), od,
                 pick(h, 'status'), pick(h, 'supplierCode'),
                 pick(h, 'supplierName'), pick(h, 'creator', 'operatorName'),
                 pick(h, 'createTime'), pick(h, 'approver'), pick(h, 'approveTime'),
                 str(h.get('id')), json.dumps(h, ensure_ascii=False), batch))
            con.execute("""INSERT OR REPLACE INTO dwd_doc_headers
                (doc_type, doc_no, branch_id, oper_date, status, supplier_code,
                 supplier_name, creator, create_time, approver, approve_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (dt, pick(h, 'sheetNo'), pick(h, 'branchId'), od,
                 pick(h, 'status'), pick(h, 'supplierCode'),
                 pick(h, 'supplierName'), pick(h, 'creator', 'operatorName'),
                 pick(h, 'createTime'), pick(h, 'approver'), pick(h, 'approveTime')))
            n_h += 1
            did = h.get('id')
            if not did:
                continue
            jj = yf.post(f'{API}{base}/doLoadEntity', {'id': str(did)})
            if str(jj.get('code', '')) == '0':
                ent = (jj.get('data') or {}).get('entity') or {}
                for i, ln in enumerate(ent.get('details') or []):
                    con.execute("""INSERT OR REPLACE INTO ods_doc_details
                        (doc_type, doc_no, line_no, item_code, item_name,
                         qty_raw, price_raw, cost_price_raw, amt_raw, unit_name,
                         raw_json, import_batch)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (dt, pick(h, 'sheetNo'), i,
                         pick(ln, 'itemCode', 'code'),
                         pick(ln, 'itemName', 'name'),
                         fnum(ln.get('qty')), fnum(ln.get('price')),
                         fnum(ln.get('costPrice')), fnum(ln.get('amt')),
                         pick(ln, 'unitName'),
                         json.dumps(ln, ensure_ascii=False), batch))
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
                    n_d += 1
            time.sleep(0.02)
        con.commit()
        log(f'[{day}] 单据 {dt}：{len(headers)} 张')
    # 商品档案 + 分类（每日全量，量小）
    items = yf.list_paginated('/web/api/product/item', {})
    for r in items:
        con.execute("""INSERT OR REPLACE INTO ods_items
            (item_code, item_name, barcode, size, unit_name, cls_code,
             retail_price_raw, purchase_price_raw, status, import_batch)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (pick(r, 'code', 'itemCode'), pick(r, 'name', 'itemName'),
             pick(r, 'barcode'), pick(r, 'size'), pick(r, 'unitName'),
             pick(r, 'itemClsCode', 'clsCode'), fnum(r.get('retailPrice')),
             fnum(r.get('purchasePrice')), pick(r, 'status'), batch))
        con.execute("""INSERT OR REPLACE INTO dwd_items
            (item_code, item_name, barcode, size, unit_name, cls_code,
             retail_price, purchase_price, status)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (pick(r, 'code', 'itemCode'), pick(r, 'name', 'itemName'),
             pick(r, 'barcode'), pick(r, 'size'), pick(r, 'unitName'),
             pick(r, 'itemClsCode', 'clsCode'),
             fnum(r.get('retailPrice')) / 10000 if r.get('retailPrice') is not None else None,
             fnum(r.get('purchasePrice')) / 10000 if r.get('purchasePrice') is not None else None,
             pick(r, 'status')))
    cats = yf.list_paginated('/web/api/product/category', {})
    for r in cats:
        con.execute("""INSERT OR REPLACE INTO categories
            (cls_code, cls_name, level, parent_code) VALUES (?,?,?,?)""",
            (pick(r, 'code', 'clsCode', 'categoryCode'),
             pick(r, 'name', 'clsName', 'categoryName'), r.get('level'),
             pick(r, 'parentCode', 'parent_code')))
    con.commit()
    log(f'[{day}] 商品 {len(items)} / 分类 {len(cats)}')
    counts = {'moves': n_moves, 'sales': n_sales, 'stock': n_stock,
              'd101': n_101, 'docs': n_h, 'doc_lines': n_d,
              'items': len(items), 'cats': len(cats)}
    try:
        dws = build_dws(con, day)
        counts['dws'] = dws
        log(f'[{day}] 汇总：日表 1 行，课组 {dws[1]} 行，单品 {dws[2]} 行，库存 {dws[3]} 行')
    except Exception as e:
        counts['dws'] = None
        log(f'[{day}] 汇总失败（不影响明细与对账）：{e}')
    status, lines = reconcile(con, day)
    con.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES ('last_ok_date', ?)",
                (day,))
    con.commit()
    return counts, lines, status

def build_dws(con, day):
    """汇总层：从明细层为指定日期建汇总（可反复跑，同一天先清后写）。
    口径：
    - 只处理日粒度销售行（sale_date 为完整日期）；月粒度行（YYYY-MM）不进汇总。
    - 净额、退货取明细层实值；明细层缺退货字段的日子（老同步拉的），
      按行回退为净额＝毛额、退货＝0，保证汇总不断档。
    - 核算层并入规则（2026-11-03 用户定）：排骨（240049）一律计入白条（240017），
      不单独列示、不单独算销售；原始明细层不动，只在汇总时并入。
    - 课组 = 商品档案类别沿分类树上溯到二级（level=2）；无法归类的进“未知”桶，
      保证各课组合计仍等于全店合计。
    返回 (日表行数, 课组行数, 单品行数, 库存行数)。"""
    ITEM_MERGE = {'240049': '240017'}
    cats = {}
    for code, lv, parent in con.execute(
            "SELECT cls_code, level, parent_code FROM categories"):
        cats[code] = (lv, parent)
        cats[str(code)] = (lv, parent)

    def level2(code):
        seen = set()
        while code is not None and code not in seen:
            seen.add(code)
            lv, parent = cats.get(code, (None, None))
            if str(lv) == '2':
                return code
            if lv is None or not parent:
                return None
            code = parent
        return None

    item_cls = {}
    for ic, cc in con.execute("SELECT item_code, cls_code FROM dwd_items"):
        item_cls[ic] = cc
        item_cls[str(ic)] = cc
    rows = con.execute(
        "SELECT item_code, COALESCE(SUM(sale_qty),0), COALESCE(SUM(sale_amt),0),"
        " COALESCE(SUM(COALESCE(return_qty,0)),0), COALESCE(SUM(COALESCE(return_amt,0)),0),"
        " COALESCE(SUM(COALESCE(net_qty,sale_qty)),0), COALESCE(SUM(COALESCE(net_amt,sale_amt)),0)"
        " FROM dwd_sales_daily WHERE sale_date=? GROUP BY item_code",
        (day,)).fetchall()
    merged = {}
    for ic, sq, sa, rq, ra, nq, na in rows:
        mic = ITEM_MERGE.get(ic, ic)
        a = merged.get(mic)
        if a is None:
            merged[mic] = [sq, sa, rq, ra, nq, na]
        else:
            for j, v in enumerate((sq, sa, rq, ra, nq, na)):
                a[j] += v
    rows = [(ic,) + tuple(v) for ic, v in merged.items()]
    con.execute("DELETE FROM dws_sales_daily WHERE sale_date=?", (day,))
    con.execute("DELETE FROM dws_sales_daily_cls WHERE sale_date=?", (day,))
    con.execute("DELETE FROM dws_sales_daily_item WHERE sale_date=?", (day,))
    tot_sa = tot_ra = tot_na = tot_nq = 0.0
    cls_agg = {}
    for ic, sq, sa, rq, ra, nq, na in rows:
        con.execute("INSERT INTO dws_sales_daily_item VALUES (?,?,?,?)",
                    (day, ic, na, nq))
        tot_sa += sa; tot_ra += ra; tot_na += na; tot_nq += nq
        lc = level2(item_cls.get(ic)) or '未知'
        a, q = cls_agg.get(lc, (0.0, 0.0))
        cls_agg[lc] = (a + na, q + nq)
    for lc, (a, q) in cls_agg.items():
        con.execute("INSERT INTO dws_sales_daily_cls VALUES (?,?,?,?)",
                    (day, lc, a, q))
    con.execute("INSERT INTO dws_sales_daily VALUES (?,?,?,?,?,?)",
                (day, tot_na, tot_nq, None, tot_sa, tot_ra))
    con.execute("DELETE FROM dws_inventory_daily WHERE snapshot_date=?", (day,))
    n_inv = 0
    inv = {}
    for ic, q, ca in con.execute(
            "SELECT item_code, qty, cost_amt FROM dwd_stock_snapshot"
            " WHERE snapshot_date=?", (day,)).fetchall():
        mic = ITEM_MERGE.get(ic, ic)
        a = inv.get(mic)
        if a is None:
            inv[mic] = [q or 0, ca or 0]
        else:
            a[0] += q or 0; a[1] += ca or 0
    for ic, (q, ca) in inv.items():
        con.execute("INSERT INTO dws_inventory_daily VALUES (?,?,?,?)",
                    (day, ic, q, ca))
        n_inv += 1
    con.commit()
    return (1, len(cls_agg), len(rows), n_inv)

def reconcile(con, day):
    lines, ok = [], True
    sale = con.execute(
        "SELECT COALESCE(SUM(sale_amt),0) FROM dwd_sales_daily WHERE sale_date=?",
        (day,)).fetchone()[0]
    r101 = con.execute(
        "SELECT sale_amt, refund_amt, sale_cnt, profit_amt FROM dwd_report101"
        " WHERE business_date=?", (day,)).fetchone()
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
            "SELECT sheet_type, COUNT(*) FROM dwd_stock_moves"
            " WHERE oper_date=? GROUP BY 1 ORDER BY 2 DESC", (day,)):
        lines.append(f'- 流水 {row[0]}：{row[1]} 行')
    # 单据对账分三类：过账单（单号即流水单号）按单号比；盘点单（PH/PQ）按挂接键比；
    # 调价/计划/录入单（TA/TH/TG/CJ/PD）不产生库存移动，只列数不比。
    MOVE_DOCS = ('PI', 'RO', 'LC', 'QC', 'OR', 'OC')
    LINK_DOCS = ('PH', 'PQ')
    for row in con.execute(
            "SELECT doc_type, COUNT(*) FROM dwd_doc_headers WHERE oper_date=?"
            " GROUP BY 1 ORDER BY 2 DESC", (day,)):
        dt, cnt = row[0], row[1]
        if dt in MOVE_DOCS:
            sheets = con.execute(
                "SELECT COUNT(DISTINCT sheet_no) FROM dwd_stock_moves WHERE oper_date=?"
                " AND sheet_no IN (SELECT doc_no FROM dwd_doc_headers"
                " WHERE doc_type=? AND oper_date=?)", (day, dt, day)).fetchone()[0]
            st = 'PASS' if sheets == cnt else 'CHECK（可能次日过账）'
            if sheets != cnt:
                ok = False
            lines.append(f'- 单据 {dt}：{cnt} 张 vs 当日流水单号 {sheets} 个 [{st}]')
        elif dt in LINK_DOCS:
            linked = con.execute(
                "SELECT COUNT(*) FROM dwd_doc_headers h WHERE h.doc_type=? AND h.oper_date=?"
                " AND EXISTS (SELECT 1 FROM dwd_stock_moves m"
                " WHERE m.business_sheet_no = h.doc_no)", (dt, day)).fetchone()[0]
            st = 'PASS' if linked == cnt else 'CHECK'
            if linked != cnt:
                ok = False
            lines.append(f'- 单据 {dt}：{cnt} 张，其中有流水挂接 {linked} 张 [{st}]')
        else:
            lines.append(f'- 单据 {dt}：{cnt} 张（不产生库存移动，只列数）')
    return ('PASS' if ok else 'FAIL'), lines

def write_report(day, counts, lines, status, pulled=True):
    os.makedirs(REPORT_DIR, exist_ok=True)
    if pulled:
        head = (f'- 拉取：流水 {counts["moves"]} 行，单品销售 {counts["sales"]} 行，'
                f'库存快照 {counts["stock"]} 品，101 {counts["d101"]} 天，'
                f'单据 {counts["docs"]} 张 / {counts["doc_lines"]} 行，'
                f'商品 {counts["items"]} / 分类 {counts["cats"]}\n')
    else:
        head = ('- 仅对账，未拉取（历史销售按月存，11-01 之前的日对账销售项为空属正常，'
                '以后的每日同步按天写）\n')
    rep = (f'# 镜像每日对账日报（{day}）\n\n' + head +
           f'- 对账结论：{status}\n\n' + '\n'.join(lines) + '\n')
    path = os.path.join(REPORT_DIR, f'daily-{day}.md')
    open(path, 'w', encoding='utf-8').write(rep)
    log(f'日报已写 {path}')
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--reconcile-only')
    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    init_db(con)
    if args.reconcile_only:
        day = args.reconcile_only
        status, lines = reconcile(con, day)
        counts = {'moves': 0, 'sales': 0, 'stock': 0, 'd101': 0,
                  'docs': 0, 'doc_lines': 0, 'items': 0, 'cats': 0}
        write_report(day, counts, lines, status, pulled=False)
        print(f'RECONCILE {day}: {status}')
        con.close()
        return
    load_env()
    sys.path.insert(0, MIRROR_HOME)
    from yunfan_login import login
    token = login()
    if not token:
        log('同步失败：登录未成功')
        con.close()
        sys.exit(2)
    yf = Yunfan(token)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if args.date:
        days = [args.date]
    else:
        last = con.execute(
            "SELECT value FROM sync_state WHERE key='last_ok_date'").fetchone()
        start = last[0] if last else SEED_LAST_OK
        d = date.fromisoformat(start) + timedelta(days=1)
        days = []
        while d.isoformat() <= yesterday:
            days.append(d.isoformat())
            d += timedelta(days=1)
        if not days:
            log(f'无待同步日（上次成功 {start}，昨天 {yesterday}）')
            con.close()
            return
    log(f'待同步：{days}')
    for day in days:
        counts, lines, status = sync_day(con, yf, day)
        write_report(day, counts, lines, status)
        log(f'[{day}] 对账结论：{status}')
    con.close()
    log('同步完成')

if __name__ == '__main__':
    main()
