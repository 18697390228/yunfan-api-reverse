#!/usr/bin/env python3
"""镜像系统 ETL + 覆盖检查 v2（2026-11-02 全量拉取）。
- 新库 mirror_full.db（不动 supermarket.db 的 10 月证明数据）。
- ODS 原值（×10000）→ DWD 真实单位 → 覆盖检查写入 recon_checks。
- 关键口径纠正：流水零售码是 OT（不是 LS）；盘点流水码是 PK/PY（不是 PH/PQ）。
- 销售文件为分月按品汇总（groupBys=["item"]），sale_date 存月份（沿用 v1 约定）。
"""
import json, os, sqlite3, sys
from collections import Counter, defaultdict

BASE = os.path.expanduser('~/workspace/supermarket-core')
PULL = os.path.join(BASE, 'pull_20261102')
DB = os.path.join(BASE, 'mirror_full.db')
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
cur = con.cursor()
cur.executescript(open(os.path.join(BASE, 'schema.sql'), encoding='utf-8').read())

def fnum(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None

def pick(row, *names):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return None

def load_jsonl(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

BATCH = 'pull_20261102'
print('== ODS 装载 ==', flush=True)
# ---- 商品档案 ----
n = 0
for r in load_jsonl(os.path.join(PULL, 'items.jsonl')):
    cur.execute("""INSERT OR REPLACE INTO ods_items
        (item_code, item_name, barcode, size, unit_name, cls_code,
         retail_price_raw, purchase_price_raw, status, import_batch)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (pick(r, 'code', 'itemCode'), pick(r, 'itemName', 'name'),
         pick(r, 'barcode'), pick(r, 'itemSize', 'size'),
         pick(r, 'unitName', 'mainUnitName'),
         pick(r, 'itemClsCode', 'clsCode'),
         fnum(pick(r, 'retailPrice')), fnum(pick(r, 'purchasePrice', 'lastPurchasePrice')),
         pick(r, 'status'), BATCH))
    n += 1
print(f'ods_items: {n}', flush=True)
# ---- 分类 ----
n = 0
for r in load_jsonl(os.path.join(PULL, 'categories.jsonl')):
    cur.execute("""INSERT OR REPLACE INTO categories (cls_code, cls_name, level, parent_code)
        VALUES (?,?,?,?)""",
        (pick(r, 'clsCode', 'cls_code'), pick(r, 'clsName', 'cls_name'),
         pick(r, 'level'), pick(r, 'parentCode', 'parent_code')))
    n += 1
print(f'categories: {n}', flush=True)
# ---- 出入库流水（4 个月） ----
n = 0
for ym in ('2026-08', '2026-09', '2026-10', '2026-11'):
    for r in load_jsonl(os.path.join(PULL, f'stockinout_{ym}.jsonl')):
        at = pick(r, 'approveTime') or ''
        cur.execute("""INSERT OR REPLACE INTO ods_stock_moves
            (yunfan_row_id, branch_id, item_code, item_name, sheet_type, sheet_no,
             approve_time, qty_raw, cost_price_raw, cost_amt_raw, retail_price_raw,
             retail_amt_raw, balance_start_qty_raw, balance_end_qty_raw,
             balance_start_amt_raw, balance_end_amt_raw, balance_price_raw,
             inout_flag, unit_name, store_name, import_batch)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(r.get('id')), pick(r, 'branchId'), pick(r, 'itemCode'),
             pick(r, 'itemName'), pick(r, 'sheetType'), pick(r, 'sheetNo'), at,
             fnum(r.get('qty')), fnum(r.get('costPrice')), fnum(r.get('costAmt')),
             fnum(r.get('retailPrice')), fnum(r.get('retailAmt')),
             fnum(r.get('balanceStartQty')), fnum(r.get('balanceEndQty')),
             fnum(r.get('balanceStartAmt')), fnum(r.get('balanceEndAmt')),
             fnum(r.get('balancePrice')), r.get('inoutFlag'),
             pick(r, 'unitName'), pick(r, 'storeName'), BATCH))
        n += 1
    print(f'ods_stock_moves 累计: {n}', flush=True)
# ---- 单品销售（分月） ----
n = 0
for ym in ('2026-08', '2026-09', '2026-10', '2026-11'):
    for r in load_jsonl(os.path.join(PULL, f'sales_{ym}.jsonl')):
        cur.execute("""INSERT OR REPLACE INTO ods_sales_daily
            (branch_id, item_code, sale_date, sale_qty_raw, sale_amt_raw, import_batch)
            VALUES (?,?,?,?,?,?)""",
            ('80996731', pick(r, 'item_code'), ym,
             fnum(r.get('sale_qty')), fnum(r.get('sale_amt')), BATCH))
        n += 1
print(f'ods_sales_daily: {n}', flush=True)
# ---- 库存快照（2026-11-02） ----
n = 0
for r in load_jsonl(os.path.join(PULL, 'stock_snapshot.jsonl')):
    cur.execute("""INSERT OR REPLACE INTO ods_stock_snapshot
        (branch_id, item_code, snapshot_date, qty_raw, cost_amt_raw,
         retail_price_raw, unit_name, import_batch)
        VALUES (?,?,?,?,?,?,?,?)""",
        (pick(r, 'branchId'), pick(r, 'itemCode'), '2026-11-02',
         fnum(r.get('qty')), fnum(r.get('costAmt')), fnum(r.get('retailPrice')),
         pick(r, 'unitName'), BATCH))
    n += 1
print(f'ods_stock_snapshot: {n}', flush=True)
# ---- 单据头 + 明细 ----
DOC_TYPES = ['PI', 'PH', 'PD', 'TA', 'TH', 'TG', 'CJ']
nh, nd, nd_fail = 0, 0, 0
for dt in DOC_TYPES:
    for r in load_json(os.path.join(PULL, f'doc_headers_{dt}.json')):
        od = pick(r, 'approveTime', 'createTime', 'operDate', 'gmtCreate') or ''
        cur.execute("""INSERT OR REPLACE INTO ods_doc_headers
            (doc_type, doc_no, branch_id, oper_date, status, supplier_code,
             supplier_name, creator, create_time, approver, approve_time,
             yunfan_id, raw_json, import_batch)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (dt, pick(r, 'sheetNo'), pick(r, 'branchId'), od[:10],
             pick(r, 'status'), pick(r, 'supplierCode'), pick(r, 'supplierName'),
             pick(r, 'creator', 'operatorName'), pick(r, 'createTime'),
             pick(r, 'approver'), pick(r, 'approveTime'),
             str(r.get('id')), json.dumps(r, ensure_ascii=False), BATCH))
        nh += 1
    for d in load_jsonl(os.path.join(PULL, f'doc_details_{dt}.jsonl')):
        ent = d.get('entity') or {}
        details = ent.get('details') or []
        if not details:
            nd_fail += 1
            continue
        for i, ln in enumerate(details):
            cur.execute("""INSERT OR REPLACE INTO ods_doc_details
                (doc_type, doc_no, line_no, item_code, item_name, qty_raw,
                 price_raw, cost_price_raw, amt_raw, unit_name, raw_json, import_batch)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (dt, d.get('sheetNo'), i,
                 pick(ln, 'itemCode', 'code'), pick(ln, 'itemName', 'name'),
                 fnum(ln.get('qty')), fnum(ln.get('price')),
                 fnum(ln.get('costPrice')), fnum(ln.get('amt')),
                 pick(ln, 'unitName'), json.dumps(ln, ensure_ascii=False), BATCH))
            nd += 1
print(f'ods_doc_headers: {nh}, ods_doc_details: {nd}, 无明细entity: {nd_fail}', flush=True)
con.commit()
print('== DWD 转换（÷10000） ==', flush=True)
cur.execute("""INSERT INTO dwd_stock_moves
    (yunfan_row_id, branch_id, item_code, sheet_type, sheet_no, oper_date, oper_time,
     qty, cost_price, cost_amt, retail_price, retail_amt,
     balance_start_qty, balance_end_qty, balance_start_amt, balance_end_amt,
     balance_price, inout_flag, neg_flag)
    SELECT yunfan_row_id, branch_id, item_code, sheet_type, sheet_no,
     substr(approve_time,1,10), approve_time,
     qty_raw/10000, cost_price_raw/10000, cost_amt_raw/10000,
     retail_price_raw/10000, retail_amt_raw/10000,
     balance_start_qty_raw/10000, balance_end_qty_raw/10000,
     balance_start_amt_raw/10000, balance_end_amt_raw/10000,
     balance_price_raw/10000, inout_flag,
     CASE WHEN balance_end_qty_raw < 0 THEN 1 ELSE 0 END
    FROM ods_stock_moves""")
cur.execute("""INSERT INTO dwd_sales_daily
    (branch_id, item_code, sale_date, sale_qty, sale_amt)
    SELECT branch_id, item_code, sale_date, sale_qty_raw/10000, sale_amt_raw/10000
    FROM ods_sales_daily""")
cur.execute("""INSERT INTO dwd_stock_snapshot
    (branch_id, item_code, snapshot_date, qty, cost_amt, retail_price, unit_cost)
    SELECT branch_id, item_code, snapshot_date, qty_raw/10000, cost_amt_raw/10000,
     retail_price_raw/10000,
     CASE WHEN qty_raw <> 0 THEN cost_amt_raw/qty_raw ELSE NULL END
    FROM ods_stock_snapshot""")
cur.execute("""INSERT INTO dwd_doc_headers
    (doc_type, doc_no, branch_id, oper_date, status, supplier_code, supplier_name,
     creator, create_time, approver, approve_time)
    SELECT doc_type, doc_no, branch_id, oper_date, status, supplier_code, supplier_name,
     creator, create_time, approver, approve_time FROM ods_doc_headers""")
cur.execute("""INSERT INTO dwd_doc_details
    (doc_type, doc_no, line_no, item_code, item_name, qty, price, cost_price, amt, unit_name)
    SELECT doc_type, doc_no, line_no, item_code, item_name, qty_raw/10000,
     price_raw/10000, cost_price_raw/10000, amt_raw/10000, unit_name
    FROM ods_doc_details""")
cur.execute("""INSERT INTO dwd_items
    (item_code, item_name, barcode, size, unit_name, cls_code, retail_price, purchase_price, status)
    SELECT item_code, item_name, barcode, size, unit_name, cls_code,
     retail_price_raw/10000, purchase_price_raw/10000, status FROM ods_items""")
con.commit()
print('== 覆盖检查 v2 ==', flush=True)
checks = []
def check(period, metric, granularity, yunfan, ours, note, tol=0.01):
    diff = (ours - yunfan) if (yunfan is not None and ours is not None) else None
    status = 'pending' if diff is None else ('match' if abs(diff) <= tol else 'diff')
    checks.append((period, metric, granularity, yunfan, ours, diff, status, note))
    flag = '✓' if status == 'match' else ('?' if status == 'pending' else '✗')
    print(f'{flag} [{period}] {metric}（{granularity}）: 云帆 {yunfan} vs 新系统 {ours} 差异 {diff} | {note}', flush=True)

# ---- 101 官方对照（分月汇总） ----
def sum101(ym, field):
    tot = 0.0
    for r in load_jsonl(os.path.join(PULL, f'report101_{ym}.jsonl')):
        v = r.get(field)
        if v is not None:
            tot += float(v) / 10000
    return round(tot, 2)
for ym in ('2026-08', '2026-09', '2026-10', '2026-11'):
    rows101 = list(load_jsonl(os.path.join(PULL, f'report101_{ym}.jsonl')))
    stocks = [round(float(r['stockAmt']) / 10000, 2) for r in rows101
              if r.get('stockAmt') is not None]
    print(f'101 {ym}: 销售额 {sum101(ym,"saleAmt")} 毛利 {sum101(ym,"profitAmt")} '
          f'退货 {sum101(ym,"refundAmt")} 库存金额(末日有值) '
          f'{stocks[-1] if stocks else None} '
          f'交易笔数 {sum101(ym,"salePayCnt"):.0f}', flush=True)
# ---- C1: 销售文件 vs 101（10月、9月）----
# 口径：销售文件 sale_amt = 毛额；101 saleAmt = 净额；毛额 = 净额 + 退货。
for ym, known in (('2026-10', 844243.03), ('2026-09', 789728.24)):
    ours = round(cur.execute(
        "SELECT COALESCE(SUM(sale_amt),0) FROM dwd_sales_daily WHERE sale_date=?",
        (ym,)).fetchone()[0], 2)
    off_net = sum101(ym, 'saleAmt')
    off_ret = sum101(ym, 'refundAmt')
    check(ym, '销售文件毛额', '全店月', round(off_net + off_ret, 2), ours,
          f'101 净额 {off_net} + 退货 {off_ret} = 毛额；另有已知毛额 {known}')
# ---- C2: 10月官方三数回归 ----
off_ref = sum101('2026-10', 'refundAmt')
check('2026-10', '101退货合计', '全店月', 7482.97, off_ref, '101 refundAmt 合计 vs 已验证官方退货')
check('2026-10', '101毛利合计', '全店月', 93715.39, sum101('2026-10', 'profitAmt'),
      '101 profitAmt 合计 vs 已验证官方毛利')
check('2026-10', '101交易笔数', '全店月', 36302, round(sum101('2026-10', 'salePayCnt')),
      '101 salePayCnt 合计 vs 已验证客流', tol=0)
# ---- C3: 流水 OT 零售额 vs 销售文件（10月） ----
ot_amt = round(abs(cur.execute(
    "SELECT COALESCE(SUM(retail_amt),0) FROM dwd_stock_moves"
    " WHERE sheet_type='OT' AND oper_date LIKE '2026-10%'").fetchone()[0]), 2)
sf_amt = round(cur.execute(
    "SELECT COALESCE(SUM(sale_amt),0) FROM dwd_sales_daily WHERE sale_date='2026-10'").fetchone()[0], 2)
check('2026-10', '流水OT零售额 vs 销售文件', '全店月', sf_amt, ot_amt,
      'OT 流水 retail_amt 绝对值合计 vs 销售文件合计（差额为退货/找零/口径项，须拆）', tol=1000)
# ---- C4: 账实核对（11-02 快照 vs 账面期末） ----
rows = cur.execute("""SELECT s.item_code, s.qty, m.balance_end_qty
    FROM dwd_stock_snapshot s
    JOIN dwd_stock_moves m ON m.yunfan_row_id = (
        SELECT yunfan_row_id FROM dwd_stock_moves
        WHERE item_code = s.item_code ORDER BY oper_time DESC LIMIT 1)
    WHERE s.snapshot_date = '2026-11-02'""").fetchall()
mism = [(c, sq, lq) for c, sq, lq in rows if abs((sq or 0) - (lq or 0)) > 0.001]
print(f'账实核对 11-02: 共 {len(rows)} 品有流水，不一致 {len(mism)} 品', flush=True)
for c, sq, lq in mism[:15]:
    print(f'  {c}: 快照 {sq} vs 账面期末 {lq}', flush=True)
check('2026-11-02', '账实不一致品数', '全店', 0, len(mism),
      '快照量 vs 最后一笔流水期末量', tol=0)
# ---- C5: 库存平衡方程重建（全量，期初+Σ流水=期末） ----
rows = cur.execute("""SELECT item_code,
     (SELECT balance_start_qty FROM dwd_stock_moves m2
      WHERE m2.item_code = m.item_code ORDER BY oper_time ASC LIMIT 1),
     (SELECT balance_end_qty FROM dwd_stock_moves m3
      WHERE m3.item_code = m.item_code ORDER BY oper_time DESC LIMIT 1),
     SUM(qty), COUNT(*)
    FROM dwd_stock_moves m GROUP BY item_code""").fetchall()
bad = []
for code, first_start, last_end, tot, cnt in rows:
    if first_start is None or last_end is None:
        continue
    if abs((first_start + tot) - last_end) > 0.001:
        bad.append((code, first_start, tot, last_end))
print(f'平衡方程重建: 共 {len(rows)} 品，重建不符 {len(bad)} 品', flush=True)
for code, fs, tot, le in bad[:15]:
    print(f'  {code}: 期初 {fs} + Σ流水 {round(tot,3)} = {round(fs+tot,3)} vs 账面期末 {le}', flush=True)
check('2026-08~11', '平衡方程重建不符品数', '全店', 0, len(bad),
      '期初（首笔期初量）+Σ全部流水 = 账面期末（末笔期末量）；不符=流水缺失或系统改写', tol=0)
# ---- C6: 单据勾稽（PI：单据头 vs 流水单号） ----
for ym in ('2026-09', '2026-10'):
    docs = cur.execute(
        "SELECT COUNT(*) FROM dwd_doc_headers WHERE doc_type='PI' AND oper_date LIKE ?",
        (ym + '%',)).fetchone()[0]
    sheets = cur.execute(
        "SELECT COUNT(DISTINCT sheet_no) FROM dwd_stock_moves"
        " WHERE sheet_type='PI' AND oper_date LIKE ?", (ym + '%',)).fetchone()[0]
    lines = cur.execute(
        "SELECT COUNT(*) FROM dwd_doc_details d JOIN dwd_doc_headers h"
        " ON d.doc_type=h.doc_type AND d.doc_no=h.doc_no"
        " WHERE d.doc_type='PI' AND h.oper_date LIKE ?", (ym + '%',)).fetchone()[0]
    mrows = cur.execute(
        "SELECT COUNT(*) FROM dwd_stock_moves WHERE sheet_type='PI' AND oper_date LIKE ?",
        (ym + '%',)).fetchone()[0]
    print(f'PI勾稽 {ym}: 单据头 {docs} 张 vs 流水单号 {sheets} 个；明细行 {lines} vs 流水行 {mrows}', flush=True)
# ---- C7: 启用日与上线前 ----
first_ot = cur.execute(
    "SELECT oper_time, sheet_no FROM dwd_stock_moves"
    " WHERE sheet_type='OT' ORDER BY oper_time ASC LIMIT 1").fetchone()
print(f'首笔零售 OT: {first_ot}', flush=True)
aug = cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT item_code) FROM dwd_stock_moves"
    " WHERE oper_date LIKE '2026-08%'").fetchone()
print(f'8月流水: {aug[0]} 行，{aug[1]} 品（上线前测试数据）', flush=True)
# ---- C8: 快照统计 ----
snap = cur.execute(
    "SELECT COUNT(*), SUM(CASE WHEN qty<0 THEN 1 ELSE 0 END),"
    " SUM(CASE WHEN qty=0 THEN 1 ELSE 0 END), SUM(cost_amt)"
    " FROM dwd_stock_snapshot WHERE snapshot_date='2026-11-02'").fetchone()
print(f'快照 11-02: 共 {snap[0]} 品，负 {snap[1]} 品，零 {snap[2]} 品，库存金额 {snap[3]:,.2f} 元', flush=True)
cur.executemany("""INSERT INTO recon_checks
    (check_date, period, metric, granularity, yunfan_value, our_value, diff, status, note)
    VALUES (date('now'),?,?,?,?,?,?,?,?)""", checks)
con.commit()
print(f'\n对账结果已写入 recon_checks，共 {len(checks)} 项', flush=True)
# ---- 报告数据落盘（供第二份报告用） ----
report = {
    'snapshot_1102': {'total': snap[0], 'neg': snap[1], 'zero': snap[2],
                      'cost_amt': round(snap[3], 2) if snap[3] else 0},
    'first_ot': list(first_ot) if first_ot else None,
    'aug_moves': aug,
    'recon_mismatch': len(mism),
    'balance_mismatch': len(bad),
    'balance_bad_sample': [[c, fs, round(t, 3), le] for c, fs, t, le in bad[:20]],
    'recon_sample': [[c, sq, lq] for c, sq, lq in mism[:20]],
    'checks': checks,
}
with open(os.path.join(BASE, '第二份对账_数据_20261102.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print('报告数据已落盘：第二份对账_数据_20261102.json', flush=True)
con.close()
