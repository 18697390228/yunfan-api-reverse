# yunfan-api-reverse

Reverse-engineering skill for **Kemai Yunfan (科脉云帆) M3/M5** retail system backend APIs.

科脉官方没有公开的开发者文档，这个 skill 沉淀了 2026-10-07～14 实测验证的逆向方法论：浏览器抓包 + 重放验证，帮助其他 AI 智能体系统性地抓取、验证、文档化云帆接口。

## 目录结构

```
yunfan-api-reverse/
├── SKILL.md                  # 主文档：基础约定、通用单据模式、建档流程、调试入口、操作铁律
└── references/
    ├── login.md              # 滑块登录四步流程（两种 loginMode、顶号、token 生命周期）
    ├── debugging.md          # 排错手册（字段名猜不出、500 崩溃、数字 ID 反查）
    ├── modules.md            # 10 大模块接口清单 + 文档输出格式
    └── product-archive.md    # 商品档案建立全流程（规格字段 size、品名解析口径、验后保存铁律）
```

## 核心约定（已验证）

- API Host: `https://yunfan-api.kemai.com.cn`，全部 POST + JSON
- 返回信封 `{code, msg, data}`，`code: 0` 成功
- 金额 ×10000 存储；单会话机制（新登录顶掉旧 token）
- 单据通用六动作：`doNewEntity` / `doSaveEntity` / `doSubmit` / `doApprove` / `doDeleteEntity` / `doLoadEntity`
- 商品建档规格字段是 `size`（不是 `spec`），规格从品名解析，保存后必须回查核验

## 使用

把整个目录交给 AI 智能体，它会按 skill 指引开展接口抓取工作。

## 版本历史

- v1.1 (2026-10-15): 新增商品档案建立（product-archive.md），modules 清单更新已验证项
- v1.0 (2026-10-12): 初始版本（登录、调试、模块清单）
