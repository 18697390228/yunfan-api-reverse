# Yunfan M5 API 字段参考

## 销售汇总查询

`POST /web/api/report/builtInReport/retailSalesSummarySummary/query`

```json
{
  "page": 1, "rows": 100,
  "params": {
    "code": "retailSalesSummarySummary",
    "columnList": ["index","branch_code","branch_name","date","sale_amt","order_count","atv"],
    "dynamicColumnMap": {},
    "groupBys": ["branch","date"],
    "params": {
      "dateType": "1",
      "gmtSaleStart": "2026-10-14 00:00:00",
      "gmtSaleEnd": "2026-10-14 23:59:59",
      "saleFlag": "0", "swapFlag": "0"
    },
    "queryType": "3",
    "reportId": "29"
  }
}
```

返回 `data.results[]`，关键字段（均为 ×10000）：
- `sale_amt`：销售额（字符串）
- `order_count`：订单数（字符串，需 ÷10000）
- `atv`：客单价
- `date`：日期
- `branch_name`：机构名称

## 库存查询

`POST /web/api/stock/report/stock/getListData`

```json
{
  "page": 1, "rows": 100,
  "params": {
    "branchIdList": ["45050580"],
    "itemIdList": ["2108469878038884416"],
    "tabSwitchType": 1
  }
}
```

返回 `data.results[]`：
- `storeName` / `storeCode`：仓库
- `qty`：库存数量（×10000，可为负）
- `availableQty`：可用库存
- `retailPrice`：售价（×10000）
- `price`：进价（×10000）
- `lastReceivePrice` / `lastReceiveQty`：最后收货价/量
- `unitName`：单位

## TG 进售价调整单明细关键字段

从 TA 明细模板改（103 字段），核心：
- `itemId`、`itemCode`、`itemName`、`itemSubno`（条码）
- `purchasePriceNew` / `purchasePriceOld`（字符串，×10000）
- `retailPriceNew` / `retailPriceOld`（字符串，×10000）
- `itemClsId`、`supplierId`、`unitName`

表头：
- `branchId`: "45050580"、`branchName`: "002"（doNewEntity 预填）
- `effectDate`: 生效日期 "2026-10-14"

## PI 入库单明细关键字段（字符串）

`amt`、`price`、`purchasePrice`、`basicPrice`、`qty`、`purchaseQty`、`basicQty`

表头带 `supplierId`、`branchId`。

## CJ 采购计划关键字段

- `amt`：金额
- `qty`（字符串）、`purchasePackageQty`、`purchaseUnitQty`、`unitQty`、`basicQty`
- `otherItemId` = 包装ID

## 测试商品（腾兴广场 M5）

- 编码：`1110001` / 品名：`测试红富士苹果` / 条码：`6900000000014`
- 商品ID：`2108469878038884416` / 包装ID：`2108469878097604623`
- 供应商ID：`2108464753254715441`（编码0100，测试供应商A）
- 机构：`45050580` / `002`
- 默认进货仓：`2108835481659256851` / `97`

## 商品建档（2026-10-14 实测打通）

`POST /web/api/product/item/doNewEntity` 取 157 字段模板 → 填字段 → `POST /web/api/product/item/doSaveEntity`（直接发 entity 本体）

必填字段：
- `barcode`、`code`（编码，可用条码）、`name`（品名）
- `purchasePrice`、`retailPrice`（**字符串**，元×10000，如 "100000"=10元）
- `itemClsId`（类别ID）、`supplierId`（供应商ID）+ `supplierCode` + `supplierName`
- `unitId`（如 56=千克）+ `unitName` + `purchaseUnitId`

**UI 建档技巧**（用户 2026-10-14 告知）：在界面输入条码时，系统会自动从公共条码库带出品名、规格等信息；API 建档需手动填写。

实测：9 个条码商品建档成功（品名暂用"待命名_条码"，类别/供应商用临时值，需在系统里批量改为 3113/0101）。

## 商品建档完整流程（2026-10-14 跑通）

1. **条码反查品名规格**（GET）：
   `GET /web/api/product/item/barcode/search?barcode={条码}`
   返回 `name`（品名）、`spec`（规格如"260g"）

2. **取新建模板**：
   `POST /web/api/product/item/doNewEntity`（157 字段）

3. **填必填字段**：
   - `barcode`、`code`（用条码）、`name`、`size`（规格）
   - `purchasePrice`、`retailPrice`（**字符串**，元×10000）
   - `itemClsId`（类别ID，如 3113扑克=`2109203200083906585`）
   - `supplierId` + `supplierCode` + `supplierName`（如 0101测试供应商B=`2108464961023758416`）
   - `unitId` + `unitName` + `purchaseUnitId`（盒=29、袋=17、个=1、包=6、箱=72、瓶=54、千克=56）
   - 单位列表：`POST /web/api/product/unit/getListData`
   - 类别ID获取：类别选择界面的 `getListData` 请求 Response 中 `code`=类别编码的 `id`
   - 供应商ID获取：供应商列表请求 Response 中 `code`=供应商编码的 `id`

4. **保存**：
   `POST /web/api/product/item/doSaveEntity`（直接发 entity 本体）
   - 成功返回 code 0（但商品为草稿状态，需在 UI 审核后才可见）
   - 条码重复报"国际条码已存在"

**注意**：API 建档后商品为草稿状态，`getListData` 查不到，需在 UI 审核。删除草稿需在 UI 操作。

## 规格提取规则（2026-10-14）
- 条码反查返回的 `spec` 字段不可靠（如"黄油黑芝麻酥"误带"260g"、"null"字符串）
- **优先从品名用正则提取**：`(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|mm|cm|m|套|个|包|盒|袋|瓶|箱))`
- 品名无规格则留空，不用反查的 spec
- 规格字段名是 `size`（不是 `spec`）
