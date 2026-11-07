#!/usr/bin/env python3
"""第二轮单据入库 + 勾稽（RO/LC/QC/OR/OC/PQ → mirror_full.db）。"""
import json, os, sqlite3

BASE = os.path.expanduser('~/workspace/supermarket-core')
PULL = os.path.join(BASE, 'pull_20261102')
con = sqlite3.connect(os.path.join(BASE, 'mirror_full.db'))
cur = con.cursor()

def fnum(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None

def pick(row, *names):
    for n in names:
        if n in row and row[n] is not None:
            return row[n]
    return None

BATCH = 'pull_20261102_r2'
for dt in ('RO', 'LC', 'QC', 'OR', 'OC', 'PQ'):
    with open(os.path.join(PULL, f'doc_headers_{dt}.json'), encoding='utf-8') as f:
        headers = json.load(f)
    nh = 0
    for r in headers:
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
    nd = 0
    with open(os.path.join(PULL, f'doc_details_{dt}.jsonl'), encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            ent = d.get('entity') or {}
            for i, ln in enumerate(ent.get('details') or []):
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
    print(f'{dt}: 入库单据头 {nh} 张，明细 {nd} 行', flush=True)
con.commit()
# DWD
cur.execute("""INSERT OR REPLACE INTO dwd_doc_headers
    (doc_type, doc_no, branch_id, oper_date, status, supplier_code, supplier_name,
     creator, create_time, approver, approve_time)
    SELECT doc_type, doc_no, branch_id, oper_date, status, supplier_code, supplier_name,
     creator, create_time, approver, approve_time FROM ods_doc_headers
    WHERE import_batch=?""", (BATCH,))
cur.execute("""INSERT OR REPLACE INTO dwd_doc_details
    (doc_type, doc_no, line_no, item_code, item_name, qty, price, cost_price, amt, unit_name)
    SELECT doc_type, doc_no, line_no, item_code, item_name, qty_raw/10000,
     price_raw/10000, cost_price_raw/10000, amt_raw/10000, unit_name
    FROM ods_doc_details WHERE import_batch=?""", (BATCH,))
con.commit()
print('== 勾稽（按单号 join，不依赖类型码） ==', flush=True)
for dt in ('RO', 'LC', 'QC', 'OR', 'OC', 'PQ'):
    docs = cur.execute(
        "SELECT COUNT(*) FROM dwd_doc_headers WHERE doc_type=?", (dt,)).fetchone()[0]
    docnos = [r[0] for r in cur.execute(
        "SELECT doc_no FROM dwd_doc_headers WHERE doc_type=?", (dt,))]
    ph = ','.join('?' * len(docnos)) if docnos else "''"
    sheets = cur.execute(
        f"SELECT COUNT(DISTINCT sheet_no) FROM dwd_stock_moves WHERE sheet_no IN ({ph})",
        docnos).fetchone()[0] if docnos else 0
    lines = cur.execute(
        "SELECT COUNT(*) FROM dwd_doc_details WHERE doc_type=?", (dt,)).fetchone()[0]
    mrows = cur.execute(
        f"SELECT COUNT(*) FROM dwd_stock_moves WHERE sheet_no IN ({ph})",
        docnos).fetchone()[0] if docnos else 0
    flag = '✓' if (docs == sheets and lines == mrows) else '⚠'
    print(f'{flag} {dt}: 单据头 {docs} 张 vs 流水单号 {sheets} 个；明细行 {lines} vs 流水行 {mrows}', flush=True)
    if docs != sheets or lines != mrows:
        # 差异明细：单据有但流水无的单号、流水有但单据无的单号（仅本类型单据的单号集合内）
        only_doc = cur.execute(
            f"SELECT doc_no FROM dwd_doc_headers WHERE doc_type=? AND doc_no NOT IN"
            f" (SELECT DISTINCT sheet_no FROM dwd_stock_moves)", (dt,)).fetchall()
        print(f'   单据有、流水无的单号（前10）: {[r[0] for r in only_doc[:10]]} 共 {len(only_doc)}', flush=True)
con.commit()
con.close()
print('入库 + 勾稽完成', flush=True)
