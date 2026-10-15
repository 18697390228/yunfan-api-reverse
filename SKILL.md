# 科脉云帆 API 逆向与操作

## 先抓包再写代码

- 先在云帆前端里把业务动作完整做一遍，再到 DevTools 的 Network 面板把对应的 XHR 请求体原样抄下来。字段名、嵌套层级、字符串还是数字、有没有包一层，全都照抄，绝不靠猜。

- 用户方便开 F12 时，给他精确到点击哪一行的抓包指引，让他把请求体贴回来。用户不方便时，用自建 Chromium 加 Playwright 自己进页面抓，绝不用打不开 DevTools 的浏览器。

- 这套抓包方法的通用版本在 local-backend-field-capture-first 里，这个 skill 只管云帆这一家的接口目录和已验证字段。

- 抓到之后先重放验证，再用读取接口把结果读回来，确认真的落库。返回成功不等于写进去了。

## 按六动作操作单据

- 云帆所有业务单据都走同一套动作。doNewEntity 取空模板，doSaveEntity 保存，doLoadEntity 按数字 ID 读取，doSubmit 提交，doApprove 审核，doDeleteEntity 删除。基址加上动作名就是完整 URL。

- 五种常用单据的基址要背下来，**不要探测猜测**（猜出的路径一律不存在）。调零售价单 TA 是 /web/api/shop/retailPrice。调进价单 TH 是 /web/api/shop/purchasePriceChange。进售价调整单 TG 是 /web/api/shop/compositePriceChange。采购计划单 CJ 是 /web/api/purchase/purchasePlanOrder。生鲜验收单 PI 是 /web/api/stock/purchaseIn。
- **用户说"综合调价"（同时调进价+售价）就是 TG**，不要往 TA 上靠。
- **调价单明细必须用全字段结构（约103字段），不可精简**——只传几个字段会导致服务端 `系统开会小差` 崩溃。做法：从本仓库 `references/price_detail_template.json` 深拷贝完整结构，只替换商品ID/编码/品名/条码/包装ID及四个新旧价格（2026-10-15 实测）。
- **调价单只存草稿，不调用 doSubmit**（2026-10-15 用户立：已提交的单据浏览器端无法直接勾选"更新档案价"，须先召回；草稿可直接打开勾选后审核）。

- doSaveEntity 直接发送 entity 本体，不要在外面再包一层。doApprove 的 body 是 {"id": "单据ID"}，这是 2026-10-13 用用户浏览器 F12 抓包确认的。doSubmit 的 body 是 {"ids": "单据ID"}，ID 用字符串，这是 2026-10-14 实测确认的。doLoadEntity 用单数的 id。

- 金额一律按元乘 10000 传。价格类字段多为字符串，比如 12 元传 "120000"。

- 单据明细数组的字段名是 details。validLowestRetailPrices 只在保存前做校验用，不会持久化。

- TA 查列表用 POST /web/api/shop/retailPrice/getListData，必须带 operDateFrom 和 operDateTo 两个参数。

- 每个请求都要带 token、loginName、shopAdminId、merchantName 这四个头，merchantName 需要 URL 编码。所有接口都是 POST 加 JSON，返回 {code, msg, data}，code 为 0 才是成功。

- 调价单 TA、TH、TG 在审核前默认勾选更新档案价，否则审核后档案价不回写。这个字段的映射还没有抓包确认过，只保留行为口径，不写成定论。

- 商品按条码查询用 POST /web/api/product/common/getItemByBarcodeOrCode，body 是 {"keyword": "条码"}。商品规格字段是 size 不是 spec，规格从品名里解析填进去，以品名为准。doSaveEntity 之后单据是草稿状态，要去 UI 里审核，并且必须回查确认真的落库。

- 销售汇总用 /web/api/report/builtInReport/retailSalesSummarySummary/query，日期参数用 gmtSaleStart 和 gmtSaleEnd。/web/api/order/statistics/ 下面的接口日期参数不生效。库存查询用 /web/api/stock/report/stock/getListData。

- 客流口径（2026-10-15 用户立）：默认取交易笔数（订单数）。云帆 POS 报表没有进店人数字段，门店也没有客流计数器设备；客单价=销售额/交易笔数。

- 每调通一个接口，就把 URL、前端触发路径、请求和响应样例记进 references，保证下次可复现。M5 已验证的字段细节在 ~/workspace/custom-skills/local-yunfan-m5-api/references/api_fields.md。

## 登录且不顶号

- 登录用 ~/workspace/custom-skills/local-yunfan-m5-api/bin/yunfan_login.py，依次传入账号、商户号、密码。密码也可以走 YF_PWD 环境变量传入。密码绝不落盘，用完即焚。

- 滑块验证码最多尝试 3 次，3 次解不开就把页面交回给用户人工过，绝不反复硬刷。

- 云帆账号是单会话，API 登录会把浏览器顶掉，浏览器登录也会把 API 的 token 顶掉。动手前先跟同时用这个账号的人错开时间，顶号之前先说一声。

- token 失效码 140001、140002、301537 都是去重新登录。301544 和 301543 是会话冲突，也是去重登。

- 绝不访问 royal-pre.cs.kemai.com.cn/login，那会触发重登加滑块。直接用云帆前端的业务页面。

## 验证落库并排错

- doSaveEntity 返回成功之后，立刻用 doLoadEntity 或列表接口把单子读回来，逐字段确认真的写进去了。

- 报 500 且前端校验已通过时，多半是缺了某个字段导致后端空指针。把抓到的真实请求体拿出来逐字段比对，不要猜。

- 同一份 body 每次报的错字段不一样，这是字段名猜错的典型信号。停下来回去抓包，不要追着报错信息改。

- 凡是被用户纠正过一次的字段映射，在抓包确认之前一律标待验证，绝不写成定论。

- 新发现、新纠正、验证结论都直接迭代更新这个 skill，保持它和 GitHub 公开库的同步。

## Available connectors

- Use `muse.connector_search` to find other connectors and `muse.skill_search` to find related skills.

- If nothing here fits, look on the web for a maintained API or MCP server and set it up with [Custom Connectors and MCPs](/opt/muse/skills/custom-connector-setup/SKILL.md), or build a custom connector.

## Websites

- [云帆前端](https://yunfan.kemai.com.cn/) for 先在业务页面里把动作做一遍再抓 XHR。把单据类型和数字 ID 带进抓包任务，抓完核对请求体里的字段。

## Alternatives for better results

- 审核动作在 API 下不稳定时，改走用户浏览器会话人工点审，API 只负责建单和保存。

- 批量操作之前，先拿一条数据走通建单到审核的全链路，确认每个环节都落库再放量。

- 距上次使用超过一段时间或前端改版后，把关键接口重抓一遍再动手。
