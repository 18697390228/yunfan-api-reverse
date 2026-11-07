# yunfan-api-reverse

Reverse-engineering notes and scripts for **Kemai Yunfan (科脉云帆) M3/M5** retail system backend APIs.

科脉官方没有公开的开发者文档，这个仓库沉淀了 2026-10-07～11-06 实测验证的逆向方法论与接口目录：浏览器抓包 + 重放验证，帮助其他 AI 智能体系统性地抓取、验证、文档化云帆接口，并用脚本把已验证的接口跑起来。

## 目录结构

```
yunfan-api-reverse/
├── SKILL.md                  # 主文档：抓包方法、六动作单据、分割关系、登录、查毛利与日报口径
├── skill.yaml                # skill 元数据
├── README.md                 # 本文件
├── references/               # 接口目录与模板
│   ├── login.md              # 滑块登录四步流程（两种 loginMode、顶号、token 生命周期）
│   ├── debugging.md          # 排错手册（字段名猜不出、500 崩溃、数字 ID 反查）
│   ├── modules.md            # 10 大模块接口清单 + 已验证报表端点（101、内置报表、异常报表）
│   ├── product-archive.md    # 商品档案建立全流程（规格字段 size、品名解析口径、验后保存铁律）
│   ├── cj_detail_template.json       # 采购计划单 CJ 明细模板
│   ├── pi_detail_template.json       # 生鲜验收单 PI 明细模板
│   └── price_detail_template.json    # 调价单全字段明细模板（约 103 字段，不可精简）
├── scripts/                  # 可直接跑的脚本（凭证一律走环境变量，见下）
│   ├── yunfan_login.py              # 账号登录（loginMode=1），滑块解题，token 只返内存
│   ├── yunfan_login_usercode.py     # 用户编码登录（loginMode=4），token 写本地 0600 文件
│   ├── verify_token.py             # 验 token：调一次库存接口，只打印状态与条数
│   ├── pull_full_20261102.py       # 全量拉取：商品/分类/流水/销售/库存/日报/单据
│   ├── pull_round2_20261102.py     # 第二轮单据拉取：RO/LC/QC/OR/OC/PQ
│   ├── load_round2_20261102.py     # 第二轮单据入库
│   ├── etl_full_20261102.py        # 全量 ETL：原始拉取结果写入镜像库
│   ├── probe_round2.py             # 探活：第二轮单据列表调用验证
│   ├── probe_doc_load.py           # 探活：PI 单据列表 + doLoadEntity 体格式确认
│   ├── pq_link_check_20261102.py   # 校验：PQ 明细与 PY 调整行的挂接
│   ├── pi_helper.py                # 入库单（生鲜验收 PI）极简接口：条码 + 数量
│   ├── ppo_helper.py               # 采购计划单（CJ）创建：浏览器原字段名
│   ├── sync_local.py               # 每日同步（本机版）：按自然日拉取并对账写日报
│   ├── sync.py                     # 每日同步（阿里云版）：systemd 定时跑
│   ├── build_dws.py                # 汇总层回填：从明细层重建按天/课组/单品/库存汇总
│   └── capture_category_supplier_20261016.md  # 抓包记录：商品分类树与供应商查询接口
├── docs/                     # 接口流程说明
│   └── m5-api-fields.md      # M5 已验证字段参考（销售汇总等）
└── update/
    └── version.json          # 云帆助手 App 自动更新清单（与接口逆向无关，历史遗留）
```

## 核心约定（已验证）

- API Host: `https://yunfan-api.kemai.com.cn`，全部 POST + JSON
- 返回信封 `{code, msg, data}`，`code: 0` 成功
- 金额 ×10000 存储；单会话机制（新登录顶掉旧 token）
- 单据通用六动作：`doNewEntity` / `doSaveEntity` / `doSubmit` / `doApprove` / `doDeleteEntity` / `doLoadEntity`，基址加动作名就是完整 URL
- 常用单据基址：调零售价 TA `/web/api/shop/retailPrice`、调进价 TH `/web/api/shop/purchasePriceChange`、进售价调整 TG `/web/api/shop/compositePriceChange`、采购计划 CJ `/web/api/purchase/purchasePlanOrder`、生鲜验收 PI `/web/api/stock/purchaseIn`
- 第二轮单据基址（2026-11-02 实测）：采购退货 RO `/web/api/stock/purchaseOut`（列表须带 `dateType:"1"`）、领用出库 LC `/web/api/stock/use`、其他出库 QC `/web/api/stock/otherOutOrder`、供应商转入 OR `/web/api/stock/supplierIn`、供应商转出 OC `/web/api/stock/supplierOut`、快速盘点 PQ `/web/api/stock/quickCheck`；调拨 TO 无独立单据类型
- 生鲜分割关系：父表 `/web/api/product/split/item/getListData`，子项全量 `/web/api/product/split/item/doLoadEntity`（入参必须是 `{"itemId": ...}`，传 `{"id": ...}` 会返回空）；白条（240017）共 22 项子项
- 商品建档规格字段是 `size`（不是 `spec`），规格从品名解析，保存后必须回查核验
- 101 经营总览日报：`POST /web/api/report/businessAnalysis/get101ListData`，交易笔数取 `salePayCnt` 字段（接口里另有个 `saleCnt` 字段是另一口径，绝不能当交易笔数用）；客单价 = saleAmt ÷ salePayCnt
- 接口报表成本/毛利字段全部为空不等于系统无毛利，查毛利走网页端零售毛利分析；查毛利前先核对门店名与商户号（禹州店与腾兴广场店是不同租户）

## 凭证安全（铁律）

- **凭证绝不入库**：密码、token、cookie、`.env` 文件一律不进仓库，`.gitignore` 已排除 `.env`、`yf_token*.json`、`*token*.json`、`*.db` 等。
- **密码走环境变量**：`YF_PWD`（密码）、`YF_SHOP`（商户号）、`YF_ACCOUNT`（账号登录用）、`YF_USERCODE`（用户编码登录用）、`YF_TOKEN`（已登录的 token，仅当次用）。脚本只从环境变量读凭证，不打印 token 值、不写日志。
- token 只放内存，当次用完即丢；必须落盘时只写本地 0600 文件，由调用方决定。
- 登录滑块最多尝试 3 次；会话冲突（301544）时不自动顶号，须用户明确授权。

## 使用

把整个目录交给 AI 智能体，它会按 `SKILL.md` 指引开展接口抓取工作；或直接跑 `scripts/` 里的脚本（先按各脚本头部的说明设置环境变量）。

## 版本历史

- v1.2 (2026-11-07): 全量整理——skill 同步（新增查毛利先验租户、日报价权威笔数两节）、登录/拉取/ETL/同步脚本、分割关系、M5 字段参考；101 交易笔数口径纠正为 `salePayCnt`
- v1.1 (2026-10-15): 新增商品档案建立（product-archive.md），modules 清单更新已验证项
- v1.0 (2026-10-12): 初始版本（登录、调试、模块清单）
