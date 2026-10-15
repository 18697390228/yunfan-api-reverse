---
name: "yunfan-api-reverse"
description: "Reverse-engineer Kemai Yunfan (科脉云帆) M3/M5 retail system backend APIs via browser capture + replay verification. Covers document CRUD pattern, product archive creation (商品建档), price/purchase/stock documents. Use when asked to document Yunfan interfaces, debug a Yunfan API call, create product archives via API, or extend Yunfan API coverage to new modules."
metadata: { "includeInPrompt": true }
---

# Yunfan API Reverse Engineering

## Purpose

Systematically capture, verify, and document backend APIs of the Kemai Yunfan M3 retail system (科脉云帆), which has **no official public API documentation**. All interfaces must be reverse-engineered from frontend behavior.

## Base Conventions (verified)

| Item | Value |
|---|---|
| API Host | `https://yunfan-api.kemai.com.cn` |
| Frontend Host | `https://yunfan.kemai.com.cn` |
| Method | All `POST` + `Content-Type: application/json` |
| Response envelope | `{code, msg, data}`, `code: 0` = success |
| Amount storage | **×10000** (¥9.80 → `98000`) |
| Auth headers (every request) | `token`, `loginName`, `shopAdminId`, `merchantName` (URL-encoded) |
| Token dead codes | `140001`/`140002`/`301537` (re-login), `301544` = session conflict |

**Single-session**: a new login kicks the old token. Never login repeatedly; coordinate with anyone else using the account. See `references/login.md` for the slider-CAPTCHA login flow.

## Core Workflow

1. **Write data first, then capture.** On a blank ledger: create categories → suppliers → products → purchase order → price change → stocktake → write-off, capturing XHR for each step in DevTools Network panel.
2. **Replay-verify every interface** with curl/script outside the browser before documenting. Mark unverified ones explicitly.
3. **Document per interface**: URL, trigger path in UI, request/response JSON examples, field meanings, pitfalls.

## Universal Document Pattern (verified)

Every business document follows:

```
{base}doNewEntity      new (fetch empty template)
{base}doSaveEntity      save (entity JSON sent directly, NOT wrapped in {entity:...})
{base}doSubmit          submit, body {"ids": "<numeric ID as string>"}
{base}doApprove         approve
{base}doDeleteEntity    delete
{base}doLoadEntity      load by numeric ID — body {"id": ...} (singular!)
```

Known example: retail price change base = `/web/api/shop/retailPrice/`, doc type `TA`.
Known product lookup: `POST /web/api/product/common/getItemByBarcodeOrCode` body `{"keyword": "<barcode>"}`.

## Product Archive Creation (商品建档, verified 2026-10-14)

Same doNewEntity → doSaveEntity pattern, but the entity is a 150+ field product object (not a document with details array).

**Barcode pre-fill**: `GET /web/api/product/item/barcode/search?barcode={条码}` returns name/candidate spec from the barcode library.

**Key fields** (from doNewEntity template):

| Field | Meaning | Notes |
|---|---|---|
| `barcode` | International barcode | |
| `name` | Product name | |
| `size` | **Spec** (规格) | ⚠️ field is `size`, NOT `spec` |
| `itemClsId` / `itemClsCode` | Category internal ID + code | Must resolve code → ID first |
| `supplierId` | Supplier internal ID | Must resolve code → ID first |
| `unitId` / `unitName` | Unit ID + name | Via `POST /web/api/product/unit/getListData` (盒=29, 袋=17, 个=1, 包=6, 箱=72, 瓶=54) |
| `purchasePrice` / `retailPrice` | Cost / retail | ×10000 |
| `itemPackDtoList` | Packaging info | Usually `[]` for simple products |

**Spec rule (user-mandated)**: parse spec from the **product name**, never trust the barcode library's spec (it is often wrong or returns string `"null"`). If the name has no clear spec, leave `size` empty.

**Verify-after-save (mandatory)**: a successful `doSaveEntity` response does NOT prove correct persistence. Always re-query/reload the entity and verify the stored fields match what was sent.

See `references/product-archive.md` for the full field walkthrough and worked example.

## Debugging Playbook

When a call fails, follow `references/debugging.md`:
- **Field-name guessing doesn't work** → copy the real `doSaveEntity` body from DevTools after doing it manually in UI; or `doLoadEntity` a real document by numeric ID to see the exact structure.
- **500 "system busy" after validation passes** → field names are right, a missing field causes backend NPE. Compare against the real request body field-by-field.
- **`doLoadEntity` needs numeric ID** → capture the **list query API** first; list responses contain both doc number and numeric ID. Never guess IDs.

## Module Checklist

See `references/modules.md` for the full per-module interface checklist (products, categories, suppliers, purchase, sales, inventory, pricing, members, master data, reports).

## Operating Rules

1. Do NOT visit `royal-pre.cs.kemai.com.cn/login` (triggers re-login + slider). Use `yunfan.kemai.com.cn` business pages directly.
2. Slider CAPTCHA: max 3 attempts, then hand to human. Never brute-force.
3. Never fabricate field meanings — mark uncertain fields "pending verification".
4. Amounts: always note the ×10000 conversion in documentation.
5. `doSaveEntity` sends the entity JSON directly; wrapping it in `{entity: ...}` fails.
6. `doSubmit`/`doApprove` take `ids` (plural, string); `doLoadEntity` takes `id` (singular). Don't mix them up.
