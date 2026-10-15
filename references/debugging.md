# Debugging Playbook

## Case 1: "Field name for product ID in detail lines unknown"

**Don't guess.** Use one of these, in order:

1. **Copy the real request.** Do the action manually in UI (create doc → add one line → save), open DevTools Network, copy the `doSaveEntity` request body verbatim. This is the ground truth.
2. **Read `getItemByBarcodeOrCode` response.** The product object's ID field name is what the detail line expects. Copy it directly.
3. **`doLoadEntity` reverse-check.** Get a real document's numeric ID (see Case 3), call `doLoadEntity`, inspect the returned detail structure.

## Case 2: 500 "system busy" after validation passes

Symptom: field names accepted (no more "field required" errors), but backend returns 500.

Meaning: **field names are correct, but a missing field causes backend NPE** during detail assembly (e.g. original price needed for margin calc).

Fix: diff your body against the real `doSaveEntity` body from DevTools, field by field. The missing one is the crash point. Common suspects: `oldRetailPrice`, `purchasePrice`, original cost fields.

Also check: value types. A numeric ID sent as string (or vice versa) can crash after passing name validation.

## Case 3: "Need numeric ID but only have doc number"

`doLoadEntity` requires the numeric ID; the doc number (e.g. `TA0000...`) doesn't work.

Fix: **capture the list query API first.** Open the document list page in UI, capture the pagination request. List responses contain both doc number and numeric ID. Map them, then call `doLoadEntity`.

Shortcut: if UI has "copy document", clicking it triggers `doLoadEntity` internally — the numeric ID appears in DevTools.

## Case 4: `getItemInfoByIds` param format unknown

Search the frontend JS bundle for the call site; the argument structure is visible there. Try in order: `{"ids": ["..",".."]}`, `{"ids": "a,b"}`, `{"itemIds": [...]}`.

## Case 5: Slider keeps failing

Stop after 3 attempts. Hand to human. Note the failure count — repeated failures tighten risk control.

## General rules

- A 4xx with message = validation error (fix fields). A 500 = backend crash (compare with real body).
- Never invent field meanings; mark uncertain ones "pending verification".
- Every documented interface must be replay-verified outside the browser.
