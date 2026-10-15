# Product Archive Creation (商品档案建立)

Verified 2026-10-14 on M5 ledger (腾兴广场, merchant 216293). Follows the universal doNewEntity → doSaveEntity pattern; the entity is a flat 150+ field product object.

## Step 1: Barcode pre-fill (optional but recommended)

```
GET /web/api/product/item/barcode/search?barcode={条码}
```

Returns candidate `name` and `spec` from the barcode library.

⚠️ **Do NOT trust the library spec.** It is frequently wrong or returns the string `"null"`. It is only a hint; the final spec comes from parsing the product name (see Spec rule below).

## Step 2: Resolve reference IDs

These fields require **internal numeric IDs**, not display codes. Resolve each before building the entity:

| Reference | How to resolve |
|---|---|
| Category (`itemClsId`) | Category tree query → match `itemClsCode` → take `id` |
| Supplier (`supplierId`) | Supplier list query → match code → take `id` |
| Unit (`unitId`) | `POST /web/api/product/unit/getListData` → match name → take `id`. Known: 盒=29, 袋=17, 个=1, 包=6, 箱=72, 瓶=54 |

Worked example (2026-10-14): category `[3113]扑克` → `2109203200083906585`; supplier `[0101]测试供应商B` → `2108464961023758416`.

## Step 3: Build entity from doNewEntity template

Call the product module's `doNewEntity` to get the template (157 fields), then fill:

**Required core fields:**

```json
{
  "barcode": "6978137070330",
  "name": "黄油黑芝麻酥",
  "size": "",
  "itemClsId": "2109203200083906585",
  "itemClsCode": "3113",
  "supplierId": "2108464961023758416",
  "unitId": 29,
  "unitName": "盒",
  "purchasePrice": 100000,
  "retailPrice": 140000
}
```

**Amounts ×10000**: 进价 10 元 → `100000`, 售价 14 元 → `140000`.

**Fields to leave alone**: `id` (empty on create), `itemPackDtoList` (`[]` for simple products), audit fields (`creatorId`, `gmtCreate`, …), computed fields (`grossProfitRate`, …).

## Step 4: Save

```
POST {product-base}/doSaveEntity
Content-Type: application/json
<body = entity JSON directly>
```

## Step 5: Verify-after-save (MANDATORY)

A `code: 0` response does **not** prove correct persistence. Immediately re-query the product via `getItemByBarcodeOrCode` and confirm every sent field landed correctly — especially `size`, prices, category, and supplier.

## Spec rule (user-mandated, 2026-10-14)

- The spec field is **`size`**, not `spec`.
- Parse the spec from the **product name** (e.g. "熊猫诗黄油型曲奇260g" → `"260g"`).
- Never use the barcode library's spec as final.
- If the name has no clear spec, leave `size` **empty** — do not invent one.

Counter-examples from 2026-10-14 (all wrong, later corrected):
- `6978137070330` saved `size: "260g"` from library, but name "黄油黑芝麻酥" has no spec → should be empty.
- `6978137070293` saved `size: "null"` (string) from library → should be empty.
- `6977955380034` saved `size: "1688"` from library → unreliable, re-parse from name.

## Deleting a bad archive

If an archive was created with wrong data, delete via the product module's `doDeleteEntity` with the numeric ID, then re-create. Do not "fix" by overwriting blindly — verify after each step.
