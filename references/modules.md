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
- [ ] Sales summary (by product / category / date — priority, used for sales stats)
  - 客流口径（2026-10-15 用户立）：默认取交易笔数（订单数）。云帆 POS 报表没有进店人数字段，门店也没有客流计数器设备；客单价=销售额/交易笔数。
- [ ] Stock summary
- [ ] Purchase-sale-inventory report

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
