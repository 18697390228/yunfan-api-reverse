# Module Interface Checklist

For each module capture: list query (pagination params), create, save, submit, approve, delete, detail query. For documents, verify the six universal actions and record the `base` path + doc type code.

## Products
- [ ] List query (pagination, filter by barcode/name/category)
- [ ] `POST /web/api/product/common/getItemByBarcodeOrCode` `{"keyword": "..."}`
- [ ] `POST /web/api/product/common/getItemInfoByIds` (batch)
- [ ] Create / save / delete product
- [ ] **Batch category change** (priority — needed for bulk reclassification)
- [ ] Image upload (if any)

## Categories
- [ ] Full category tree (code, level, is-leaf flag)
- [ ] Create (confirm code rule per level)
- [ ] Update / delete

## Suppliers
- [ ] List / create / update / delete
- [ ] Supplier-product linkage (if any)

## Purchase
- [ ] Purchase order: base + full chain (new → save → submit → approve)
- [ ] Purchase inbound: same
- [ ] Purchase return: same

## Sales
- [ ] Wholesale sales order: base + full chain
- [ ] Retail receipt query (by date / cashier / receipt no)
- [ ] Retail return flow

## Inventory
- [ ] Stock query (by product / warehouse; check qty + amount fields)
- [ ] Stocktake: create → enter counts → variance handling → approve
- [ ] Transfer (warehouse-to-warehouse)
- [ ] Write-off / write-on
- [ ] Stock movement log query

## Pricing
- [ ] Retail price change: base `/web/api/shop/retailPrice/`, type `TA` (partially verified)
- [ ] Purchase price change (type `TH`)
- [ ] Promotion (type `SP`): create, effective dates, product scope
- [ ] Member price setting

## Members
- [ ] List / create / tiers
- [ ] Points / stored value (if any)

## Master data
- [ ] Warehouse / store list
- [ ] Units of measure
- [ ] Cashiers / operators
- [ ] Payment methods

## Reports
- [x] Sales summary (by product / category / date — priority, used for sales stats)
  - 客流口径（2026-10-15 用户立）：默认取交易笔数（订单数）。云帆 POS 报表没有进店人数字段，门店也没有客流计数器设备；客单价=销售额/交易笔数。
  - 内置报表通用端点（2026-11-01 实测，M3 禹州店）：`POST /web/api/report/builtInReport/{code}/query`，body `{"page","rows","params":{"code","columnList":[],"dynamicColumnMap":{},"groupBys":[],"params":{...},"queryType":"3","reportId":"29"}}`；金额/数量/订单数字段均 ×10000 存储，读取时 ÷10000。
  - 已验 code（groupBys 示例）：retailSalesSummary（单品销售）、retailSalesSummarySummary（按机构+日期）、retailProfitSummary（毛利字段全空，不可用）、purchaseSummary（实为销售视图，非采购数）、retailProfitAnalysis（零售毛利分析，含毛额/净额/退货/客单/会员）、retailAndWholesaleProfitAnalysis（零批毛利分析，与零售毛利数一致）、wholesaleProfitQuery（批发毛利，10 月全零）、itemABCAnalysis（商品ABC，3284 条）、itemSaleRate（动销率机构汇总，不直接返回动销率字段）、itemTurnoverReport（周转率，与商品ABC同一数据源，无周转率字段）、businessComparisonAnalysis（102 业绩对比）、clsABCAnalysis（类别ABC，分组不返回分类行，仅机构合计）、salestockMonthReportNew / salestockMonthReport / salestockDayReport / salestockDayReportDx / salestockMonthReportDx（进销存各口径，均只返回销售字段，无期初/入库/结存字段）。
  - 成本/毛利字段：builtInReport 的 cost_amt、profit_amt、current_profit_rate、member_profit_rate 全部为 None；系统结转毛利只能走网页端零售毛利分析或 101 日报（见下），接口为空不等于系统无毛利。
- [x] 101 经营总览日报（2026-11-01 实测）：`POST /web/api/report/businessAnalysis/get101ListData`，body `{"page","rows","params":{"businessMonth":"2026-10","branchId":"80996731"}}`；返回 31 天逐日行，saleAmt/profitAmt/salePayCnt 等 ×10000，占比字段 ×100（如 norSaleAmtRatio 9741 = 97.41%）；31 天 saleAmt 合计 = 净额 836,760.06、profitAmt 合计 = 毛利 93,715.39，与网页端零售毛利分析分毫不差；交易笔数取 salePayCnt 字段（接口里另有个 saleCnt 字段是另一口径，绝不能当交易笔数用）；末日异常计数（负库存/负毛利/库0/畅缺/高库存/滞销/进货未销/暂停淘汰）与各异常报表条数完全一致；注意 101 存在数据缺失日（10-12 负库存计数为 0、10-26/28/30 库存金额为 0），引用时须剔除。
- [x] 异常报表通用动作（2026-11-01 实测）：`POST /web/api/report/{base}/getListData`，body `{"page","rows","params":{"branchId":"80996731",...}}`；201 zerostockItem（库0）、202 bastsellOutstockItem（畅缺）、203 unsalableItem（滞销，按建档时间）、204 purchaseNoSalesItem（进货未销）、205 highInventoryItem（高库存）、206 pauseEliminateItem（暂停淘汰库非0）、207 minusItemStock（负库存）、208 minusProfitItem（负毛利，含 saleCostAmt/saleProfit/saleProfitRate ×100）；201/207/208 为实时快照非历史数据；`/query` 后缀端点全部 404，不要用。
- [x] 其他报表端点（2026-11-01 实测）：新品销售 `POST /web/api/product/newItemSalesReport/getListData`（gmtCreateStart/End）；销售目标分析 `POST /web/api/report/salesTargetAnalyse/getListData`（startTime/endTime/type，type=2 为月）；进销存出入库明细 `POST /web/api/stock/report/stockinout/getListData`（operDateFrom/To + branchId，含 balanceStart/EndQty/Amt、adjustAmt；明细行为交易级，直接加总会重复计算，须按商品取末条余额）；商品价格带 `POST /web/api/report/priceRange/queryForReport`（需先配置价格带区间，否则报错）；库存 `POST /web/api/stock/report/stock/getListData`（params {"tabSwitchType":1} 即可，不需要 branchId；totalRecord 字段不可信为 0，须分页拉到空为止）。
- [ ] Stock summary
- [ ] Purchase-sale-inventory report（builtInReport 的 salestock 各 code 均只返回销售字段，真正的进销存须走 stockinout 明细或网页端）

## Doc output format (per interface)

```markdown
### {Interface name}
- URL:
- Method:
- UI trigger path:
- Request headers: (auth-related only)
- Request body example:
- Field notes: (meaning, required?, value range)
- Response example:
- Notes: (e.g. amount ×10000, numeric-ID-only)
- Status: ✅ verified / 🔍 inferred
```
