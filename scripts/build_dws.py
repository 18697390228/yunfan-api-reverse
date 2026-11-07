"""汇总层回填：对已同步的日子从明细层重建汇总（可反复跑）。"""
import sys, sqlite3
sys.path.insert(0, '/home/hatch/workspace/supermarket-mirror')
from sync_local import build_dws

DB = '/home/hatch/workspace/supermarket-core/mirror_full.db'
con = sqlite3.connect(DB)
days = sys.argv[1:] or [r[0] for r in con.execute(
    "SELECT DISTINCT sale_date FROM dwd_sales_daily WHERE length(sale_date)=10")]
for day in days:
    dws = build_dws(con, day)
    print(f'{day}: 日表 {dws[0]} 行，课组 {dws[1]} 行，单品 {dws[2]} 行，库存 {dws[3]} 行')
# 校验：汇总合计 = 明细合计；各课组合计 = 全店合计
for day in days:
    d = con.execute("SELECT sale_amt, net_amt, return_amt FROM dws_sales_daily WHERE sale_date=?", (day,)).fetchone()
    m = con.execute("SELECT COALESCE(SUM(sale_amt),0), COALESCE(SUM(net_amt),0) FROM dwd_sales_daily WHERE sale_date=?", (day,)).fetchone()
    c = con.execute("SELECT COALESCE(SUM(net_amt),0) FROM dws_sales_daily_cls WHERE sale_date=?", (day,)).fetchone()[0]
    i = con.execute("SELECT COUNT(*) FROM dws_sales_daily_item WHERE sale_date=?", (day,)).fetchone()[0]
    inv = con.execute("SELECT COUNT(*), COALESCE(SUM(cost_amt),0) FROM dws_inventory_daily WHERE snapshot_date=?", (day,)).fetchone()
    print(f'校验 {day}: 汇总毛额 {d[0]:.2f} = 明细 {m[0]:.2f} ? {abs(d[0]-m[0])<0.01}；'
          f'课组净额合计 {c:.2f} = 全店净额 {d[1]:.2f} ? {abs(c-d[1])<0.01}；'
          f'净额 {d[1]:.2f} + 退货 {d[2]:.2f} = 毛额 ? {abs(d[1]+d[2]-d[0])<0.01}；单品 {i} 行；库存 {inv[0]} 品')
    unk = con.execute("SELECT net_amt FROM dws_sales_daily_cls WHERE sale_date=? AND cls_code='未知'", (day,)).fetchone()
    print(f'  未归类桶金额: {unk[0] if unk else 0:.2f}')
con.close()
