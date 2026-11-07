# 科脉云帆 M5 商品分类 / 供应商查询接口抓包记录

日期：2026-10-16
账套：腾兴广场（shopAdminId 216293）
方式：Playwright + Chromium（经本地转发代理）+ 前端 JS 源码分析 + API 实测验证
状态：只做查询，未做任何写入操作

## 一、商品分类树查询

**前端调用点**（`/js/app.6f92c7b0.js` 源码）：
```js
getItemClsTreeData: function(e,t,n){
  return r["a"].request({
    url: "/web/api/product/category/tree",
    data: e,
    method: "post",
    hideRuning: n
  })
}
```

**接口**：
```
POST https://yunfan-api.kemai.com.cn/web/api/product/category/tree
Content-Type: application/json
Headers: token / loginName / shopAdminId / merchantName（URL编码"腾兴广场"）
Body: {}（空对象即可）
```

**返回**（`code: 0` 时）：
```json
{
  "code": 0,
  "data": [
    {
      "id": "2108462170149638238",
      "code": "1",
      "name": "测试生鲜(旧)",
      "parentId": null,
      "leafFlag": false,
      "level": 1,
      "children": [ ... 递归 ... ]
    }
  ]
}
```

**字段映射**（建档用）：
| 建档字段 | 来源 |
|---|---|
| `itemClsId` | 节点的 `id`（字符串） |
| `itemClsCode` | 节点的 `code`（如 "3113"） |

**实测**：`code:"3113"`（扑克）→ `id:"2109203200083906585"`，与 2026-10-14 验证一致。

---

## 二、供应商查询（按条码/编码）

**前端调用点**（`/js/app.6f92c7b0.js` 源码）：
```js
getSupplierByBarcodeOrCode: function(e){
  return w["a"].request({
    url: "/web/api/purchase/supplier/common/getSupplierByBarcodeOrCode",
    data: e,
    method: "post"
  })
}
```

**接口**：
```
POST https://yunfan-api.kemai.com.cn/web/api/purchase/supplier/common/getSupplierByBarcodeOrCode
Content-Type: application/json
Headers: token / loginName / shopAdminId / merchantName（URL编码"腾兴广场"）
Body: {"keyword": "0101"}（供应商编码或名称关键词）
```

**返回**（`code: 0` 时）：
```json
{
  "code": 0,
  "data": [
    {
      "id": "2108464961023758416",
      "code": "0101",
      "name": "测试供应商B",
      "...": "其他字段省略"
    }
  ]
}
```

**字段映射**（建档用）：
| 建档字段 | 来源 |
|---|---|
| `supplierId` | `id`（字符串） |

**实测**：`keyword:"0101"` → `id:"2108464961023758416"`（测试供应商B），与 2026-10-14 验证一致。

---

## 三、备注

1. 两个接口均为前端商品档案新建页实际调用的接口（从 JS 源码的调用点确认，非猜测）。
2. 浏览器直接登录抓包未成功（前端路由守卫跳转登录页，localStorage 注入 token 未生效），改用"前端源码调用点 + API 实测"双重验证。
3. 单位查询接口（已知）：`POST /web/api/product/unit/getListData`，已知映射：盒=29、袋=17、个=1、包=6、箱=72、瓶=54。
4. 商品建档模板：`POST /web/api/product/item/doNewEntity`（157 字段，已验证）。
5. 本次未做任何写入操作，无测试单据产生。
