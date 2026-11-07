# 科脉云帆 API 逆向与操作

## 先抓包再写代码

- 先在云帆前端里把业务动作完整做一遍，再到 DevTools 的 Network 面板把对应的 XHR 请求体原样抄下来。字段名、嵌套层级、字符串还是数字、有没有包一层，全都照抄，绝不靠猜。

- 用户方便开 F12 时，给他精确到点击哪一行的抓包指引，让他把请求体贴回来。用户不方便时，用自建 Chromium 加 Playwright 自己进页面抓，绝不用打不开 DevTools 的浏览器。

- 这套抓包方法的通用版本在 local-backend-field-capture-first 里，这个 skill 只管云帆这一家的接口目录和已验证字段。

- 抓到之后先重放验证，再用读取接口把结果读回来，确认真的落库。返回成功不等于写进去了。

## 按六动作操作单据

- 云帆所有业务单据都走同一套动作。doNewEntity 取空模板，doSaveEntity 保存，doLoadEntity 按数字 ID 读取，doSubmit 提交，doApprove 审核，doDeleteEntity 删除。基址加上动作名就是完整 URL。

- 五种常用单据的基址要背下来，**不要探测猜测**（猜出的路径一律不存在）。调零售价单 TA 是 /web/api/shop/retailPrice。调进价单 TH 是 /web/api/shop/purchasePriceChange。进售价调整单 TG 是 /web/api/shop/compositePriceChange。采购计划单 CJ 是 /web/api/purchase/purchasePlanOrder。生鲜验收单 PI 是 /web/api/stock/purchaseIn。
- - **第二轮单据基址（2026-11-02 实测，M3 禹州店，列表统一走 {base}/getListData、明细统一走 {base}/doLoadEntity）**：采购退货单 RO 是 /web/api/stock/purchaseOut，**列表必须带 dateType:"1"，否则报 300001“时间类型不能为空”**（先前误以为是基址错，实为缺参数）。领用出库单 LC 是 /web/api/stock/use。其他出库单 QC 是 /web/api/stock/otherOutOrder（不是 otherOut，少了 Order）。供应商转入单 OR 是 /web/api/stock/supplierIn。供应商转出单 OC 是 /web/api/stock/supplierOut。快速盘点单 PQ 是 /web/api/stock/quickCheck。六种单据 2026-11-02 全量拉取（8 月→11 月 2 日）154 张、明细 12,985 行，RO/LC/QC/OR/OC 明细行与出入库流水行分毫不差。
  - - **调拨 TO 没有独立单据类型**：调拨为 BC 出库 / BR 收货 / TS 申请 / BD 差异，本店流水为 0，无需拉取。
    - - **盘点类流水挂接键**：流水行的 sheetNo 自成一号（如 PY0000…），须用 businessSheetNo 挂回源单据（businessSheetType 为 PH 或 PQ）；PQ 明细是全量盘点清单，PY 行只记有差异的调整行，行数不等是正常的（2026-11-02 实测：20 张 PQ 单张张有 PY 行挂接，抽查单 PY 品全在明细内）。
- **用户说"综合调价"（同时调进价+售价）就是 TG**，不要往 TA 上靠。
- **调价单明细必须用全字段结构（约103字段），不可精简**——只传几个字段会导致服务端 `系统开会小差` 崩溃。做法：从本仓库 `references/price_detail_template.json` 深拷贝完整结构，只替换商品ID/编码/品名/条码/包装ID及四个新旧价格（2026-10-15 实测）。
- **调价单只存草稿，不调用 doSubmit**（2026-10-15 用户立：已提交的单据浏览器端无法直接勾选"更新档案价"，须先召回；草稿可直接打开勾选后审核）。
- **采购计划单 CJ 已打通**（2026-10-15）：base `/web/api/purchase/purchasePlanOrder`。表头必填 `receiveBranchId=45050580`、`receiveBranchCode=000002`、`receiveBranchName=002`、`receiveBranchType=2`、`planType=0`。明细模板见本仓库 `references/cj_detail_template.json`：qty 等数量为字符串（×10000），price 为数字（×10000）。

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

## 组合拆分分割关系

- 生鲜分割关系定义父表：POST /web/api/product/split/item/getListData，标准 getListData 入参（page、rows、params）。2026-11-02 实测（M3 禹州店）：返回 total 为 1，只有一条父商品——白条（商品编码 itemCode 240017，商品标识 itemId 2090985605576536104，商品条码 itemSubno 2999900000012，类别编码 itemClsCode 24031203 冷鲜肉类，单位公斤，档案价 150000 即 15.00 元，商品标志 itemFlag 为 2 表示生鲜分割商品）。注意：列表接口返回的 details 字段为 null，子项不在列表里，列表只能拿到父商品。

- 子项全量：POST /web/api/product/split/item/doLoadEntity，入参必须是 {"itemId": "父商品的 itemId"}，返回 data.entity.details 数组（2026-11-02 实测白条共 22 项）。坑：传 {"id": ...} 也会返回成功，但 details 为空数组，必须传 itemId 才能拿到子项。每个子项字段：商品编码 itemCode、商品条码 itemSubno、品名 itemName、类别编码 itemClsCode、类别名 itemClsName、单位名 unitName、价格 price（金额乘 10000）、子项标识 subItemId、分割比例 splitRule（乘 10000，10000 即 1.000）、组合比例 combineRule（分割场景下为空）。

- 同模块其他端点只列名字、不写验证结论（前端代码确认存在，本次未逐一调用验证）：拆分管理侧 /web/api/product/split/ManageStock/getListData 与 doLoadEntity；组合关系定义侧 /web/api/product/combination/item/getListData 与 doLoadEntity；/web/api/item/relation/splitDetails 只在前端通用函数里出现过，入参形状未探明，明确标注未验证、不要直接用。

- 探活方法（本次实战经验）：云帆网页端是 webpack 打包，组合拆分分割管理页（路由 composeSplitRelation）懒加载两个 chunk，chunk 文件名是 js/<chunk 名>.<哈希>.js，哈希在主 js（/js/app.<哈希>.js）的映射表里可查；先下主 js 找哈希，再下 chunk js 搜索接口路径，比盲猜端点可靠。商品档案的 component 字段恒为空，分割关系不要去商品档案里找。

## 登录且不顶号

- 登录用本仓库 scripts/yunfan_login.py（账号登录）或 scripts/yunfan_login_usercode.py（用户编码登录），凭证一律走环境变量传入。密码绝不落盘，用完即焚。

- 滑块验证码最多尝试 3 次，3 次解不开就把页面交回给用户人工过，绝不反复硬刷。

- 云帆账号是单会话，API 登录会把浏览器顶掉，浏览器登录也会把 API 的 token 顶掉。动手前先跟同时用这个账号的人错开时间，顶号之前先说一声。

- token 失效码 140001、140002、301537 都是去重新登录。301544 和 301543 是会话冲突，也是去重登。

- 绝不访问 royal-pre.cs.kemai.com.cn/login，那会触发重登加滑块。直接用云帆前端的业务页面。

## 查毛利前先验租户

- 在浏览器做任何报表工作前，先核对首页门店名和商户号是否就是本次要查的门店，禹州店和腾兴广场店是不同租户，绝不能凭自动登录默认租户正确。

- 自动登录落到另一个租户时，立刻停下报表工作，先退出再用目标门店凭证重新登录，重新核对首页后再翻报表。

- 接口报表成本和毛利字段全部为空时，绝不要直接断言系统没有毛利，先去网页端报表中心的零售毛利分析核对，接口为空不等于系统无毛利。

- 以网页端零售毛利分析作为月度毛利口径，路径是 yunfan.kemai.com.cn/report/retailProfitAnalysis。

- 同一份报告里分别标注接口销售额为毛额和网页端销售额为退货后净额，把差额说明为退货，不要混在同一个合计里。

- 每次写出毛利总额都同时写明起止日期，绝不要把不同日期口径的总额并列或相减当作单日毛利。

- 需要按二级分类出毛利时，先按二级分类对零售毛利分析做分组汇总，通用版没有独立自定义报表设计器时就用分组视图加筛选视图名保存，不要宣称新建了自定义报表。

- 打开已保存的分组视图时重新选择起止日期再查询，因为筛选视图不保存日期。

- 档案进价高于售价或倒挂时，先标记该档案价陈旧不可信，再用网页端系统成本或实际进货价加权成本核对。

## 日报只用权威交易笔数与客单价

- 用户问当日交易笔数与客单价时，绝不用邻近几天的笔数推算，也绝不用销售额除以一个猜出来的笔数，先去系统里能查到这两个数的模块取权威数。

- 从 101 经营总览日报取这两个数，接口是 POST /web/api/report/businessAnalysis/get101ListData，按日期取当日的行，salePayCnt 就是交易笔数（注意：接口里另有个 saleCnt 字段是另一口径，绝不能当交易笔数用），客单价等于 saleAmt 除以 salePayCnt，金额与笔数字段都按乘 10000 存储，先除以 10000 再算。

- 当日的 101 行还没有生成时，直接说该行尚未生成，并写明下一次同步会补上，绝不用推算数把空缺填上。

- 某一路登录返回密码错误时，停下不要拿同一凭证反复重试，改走上次走通的登录路径取数，取不到就向用户要当前凭证，反复重试有锁号风险。

- 每天把交易笔数与客单价同时写进镜像服务端汇总与日报，两种地方都要有，不要只在用户追问时才补。

- 日报里对销售额与毛利做两组对比，一组对昨天，一组对上周，标签按用户口径写，同比就是对昨天，环比就是对上周，不要按标准定义去纠正用户的标签。

- 每处上升或下降先顺着源头单据或课组数据把原因查清楚再写，查不清就写明原因尚未查清，不要猜一个原因交差。

- 日报一律以文档形式交付，不要在聊天里发长串数字。

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
