#!/usr/bin/env python3
"""PQ 链接核查 + stock_moves 补 businessSheetNo/businessSheetType（schema v2.1）。
- 核查：每张 PQ 单是否有 PY 流水行经 businessSheetNo 挂接；PY-PQ 行的品是否为 PQ 明细的子集（抽查）。
- 补列：mirror_full.db 的 ods/dwd_stock_moves 加 business_sheet_no/business_sheet_type，并从原始流水回填。
"""
import json, os, sqlite3
from collections import defaultdict

BASE = os.path.expanduser('~/workspace/supermarket-core')
PULL = os.path.join(BASE, 'pull_20261102')
con = sqlite3.connect(os.path.join(BASE, 'mirror_full.db'))
cur = con.cursor()
for tbl in ('ods_stock_moves', 'dwd_stock_moves'):
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info({tbl})')]
    for col in ('business_sheet_no', 'business_sheet_type'):
        if col not in cols:
            cur.execute(f'ALTER TABLE {tbl} ADD COLUMN {col} TEXT')
            print(f'{tbl} 加列 {col}', flush=True)
con.commit()
# 回填：按 yunfan_row_id 从原始流水取 businessSheetNo/Type
n = 0
for ym in ('2026-08', '2026-09', '2026-10', '2026-11'):
    with open(os.path.join(PULL, f'stockinout_{ym}.jsonl'), encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            cur.execute("""UPDATE ods_stock_moves SET business_sheet_no=?, business_sheet_type=?
                WHERE yunfan_row_id=?""",
                (r.get('businessSheetNo'), r.get('businessSheetType'), str(r.get('id'))))
            cur.execute("""UPDATE dwd_stock_moves SET business_sheet_no=?, business_sheet_type=?
                WHERE yunfan_row_id=?""",
                (r.get('businessSheetNo'), r.get('businessSheetType'), str(r.get('id'))))
            n += 1
    print(f'回填 {ym} 累计 {n} 行', flush=True)
con.commit()
# 核查：PQ 单 ↔ PY 行（businessSheetNo）
pq_docs = [r[0] for r in cur.execute(
    "SELECT doc_no FROM dwd_doc_headers WHERE doc_type='PQ'")]
print(f'PQ 单共 {len(pq_docs)} 张', flush=True)
linked, unlinked = [], []
for doc in pq_docs:
    cnt = cur.execute(
        "SELECT COUNT(*) FROM dwd_stock_moves WHERE business_sheet_no=?", (doc,)).fetchone()[0]
    (linked if cnt > 0 else unlinked).append((doc, cnt))
print(f'有 PY 行挂接的 PQ 单：{len(linked)} 张；无挂接：{len(unlinked)} 张', flush=True)
for doc, cnt in linked:
    print(f'  {doc}: PY 行 {cnt}', flush=True)
for doc, cnt in unlinked:
    print(f'  无挂接 {doc}', flush=True)
# 抽查一张：PY 行的品是否在 PQ 明细内
if linked:
    doc = linked[0][0]
    py_items = set(r[0] for r in cur.execute(
        "SELECT item_code FROM dwd_stock_moves WHERE business_sheet_no=?", (doc,)))
    pq_items = set(r[0] for r in cur.execute(
        "SELECT item_code FROM dwd_doc_details WHERE doc_type='PQ' AND doc_no=?", (doc,)))
    print(f'抽查 {doc}: PY 行品数 {len(py_items)}，PQ 明细品数 {len(pq_items)}，'
          f'PY 品在明细内 {len(py_items & pq_items)}，PY 有明细无 {len(py_items - pq_items)}', flush=True)
# PY 行按业务类型汇总（全量）
for row in cur.execute(
        "SELECT business_sheet_type, COUNT(*) FROM dwd_stock_moves"
        " WHERE sheet_type='PY' GROUP BY business_sheet_type"):
    print(f'PY 行业务类型 {row[0]}: {row[1]} 行', flush=True)
con.commit()
con.close()
print('完成', flush=True)
