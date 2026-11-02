# Login Flow (slider CAPTCHA required)

```
GET  /validate/initImg       → slider puzzle (returns sliderToken + images)
  ↓ solve for gap x coordinate
POST /validate/checkLogin    → verify slider {sliderToken, x, y}
  ↓ pass
POST /login                  → login, returns token
```

## Step 1: Get slider images

```
GET https://yunfan-api.kemai.com.cn/validate/initImg
```

Returns: background image (with white gap), slider strip image, `sliderToken`.

## Step 2: Solve gap x

1. Locate the white gap's bounding box in the background image; take its left-edge x.
2. Subtract the x0 offset of the puzzle content inside the strip.
3. Result is `x`. `y` is typically fixed (observed value: `5`, but confirm from response).

**Discipline**: max 3 auto attempts, then hand to human. Do not brute-force.

## Step 3: Verify slider

```
POST https://yunfan-api.kemai.com.cn/validate/checkLogin
Content-Type: application/json

{"sliderToken": "<from initImg>", "x": <gap x>, "y": 5}
```

Use the freshest `sliderToken` for the next step.

## Step 4: Login

Two login modes. **Both modes work for both M3 and M5 tenants — the mode is the user's choice, not a per-tenant property.** Do not assume M3 = user-code and M5 = account.

**Account login** (`loginMode: 1`):
```json
{
  "shopAdminId": "<merchant no>",
  "username": "<phone/account>",
  "loginMode": 1,
  "password": "<password>",
  "webLoginCheckType": "2",
  "sourcePlat": 2,
  "sliderToken": "<verified>",
  "x": <gap x>,
  "y": 5
}
```

**User-code login** (`loginMode: 4`):
```json
{
  "shopAdminId": "<merchant no>",
  "userCode": "<user code>",
  "loginMode": 4,
  "password": "<password>",
  "webLoginCheckType": "2",
  "sourcePlat": 2,
  "sliderToken": "<verified>",
  "x": <gap x>,
  "y": 5
}
```

## Step 5: Session conflict (code 301544)

Account is single-session. If `301544`, add `"continueLogin": 1` to the login body **only with explicit user authorization** — it kicks the other session's token immediately.

## Verified 2026-11-02

- User-code login (`loginMode: 4`) verified working: slider solved on first attempt, login returned code 0, token verified against the stock API (`/web/api/stock/report/stock/getListData` returned code 0 with rows).
- M3 account login with the credentials tried earlier returned 295002 (password error); user-code login with its own credentials succeeded. If one mode fails on credentials, try the other mode with its own credentials.
- `loginName` header = the login identifier of the mode used: phone/account for account login, userCode for user-code login.

## Auth headers for all subsequent requests

| Header | Source |
|---|---|
| `token` | login response `data.token` |
| `loginName` | login identifier of the mode used (phone/account for account login, userCode for user-code login) |
| `shopAdminId` | merchant number |
| `merchantName` | company name, `encodeURIComponent`-encoded |

## Token lifecycle

- Reuse the token; re-login only on `140001`/`140002`/`301537`.
- Passwords go through Secure Vault; never write plaintext credentials in docs or code.
