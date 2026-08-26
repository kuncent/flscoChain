# 联盟链实训平台 · API 文档

> **Base URL**：`http://127.0.0.1:8000`
> **交互式文档**：`http://localhost:8000/docs`（Swagger UI，可直接试调）
> **健康检查**：`GET /health` → `{"status":"ok","mode":"evm"}`

---

## 一、通用约定

### 1. 请求方法

| 类型 | 参数位置 | Content-Type |
|------|---------|--------------|
| GET | URL Query | — |
| POST / PUT / DELETE | JSON Body | `application/json` |
| 文件上传 | form-data | `multipart/form-data` |

### 2. 公共请求头

所有接口可选，但登录态相关接口（成绩、班级、报告）必须携带：

| Header | 必填场景 | 说明 |
|--------|---------|------|
| `X-Wallet` | 学习行为埋点 | 当前操作钱包地址，如 `0xlearner` |
| `X-User-Id` | 成绩/班级接口 | 登录用户 ID |
| `X-Role-Id` | 成绩/班级接口 | 1=管理员, 3=教师, 4=学生 |
| `X-User-Name` | 成绩接口 | URL 编码后的中文用户名 |
| `X-Class-Id` | 班级接口 | 班级 ID |
| `Authorization` | 会话校验 | `Bearer <accessToken>` |

前端 axios 拦截器会自动从 `localStorage` 注入上述头部，无需手动设置。

### 3. 响应格式

- **成功**：直接返回数据对象，或 `{ "ok": true, ...data }`
- **失败**：`{ "detail": "错误描述" }`，HTTP 状态码 400/403/404/500

---

## 二、接口模块总览

| # | 模块 | 前缀 | 接口数 | 说明 |
|---|------|------|--------|------|
| 1 | 认证 | `/api/auth` | 5 | 登录、会话、班级学生、平台进度 |
| 2 | 链状态与搭链教程 | `/api/chain` | 6 | 链状态、10 步搭链教程 |
| 3 | 合约管理 | `/api/contracts` | 10 | 编译、部署、调用、审计 |
| 4 | 合约 IDE | `/api/ide` | 8 | 项目与文件管理 |
| 5 | 绿色低碳联盟链 | `/api/eco` | 25 | 角色、能量、证书、勋章、市场 |
| 6 | 钱包管理 | `/api/wallet` | 6 | ERC20 发行、转账、余额 |
| 7 | NFT 资产 | `/api/nft` | 6 | 铸造、购买、交易记录 |
| 8 | 区块链浏览器 | `/api/explorer` | 13 | 链上数据浏览与统计 |
| 9 | 调用监听器 | `/api/monitor` | 3 | 合约调用统计 |
| 10 | 云桌面 | `/api/cloud` | 4 | 虚拟文件系统、命令补全 |
| 11 | 实训报告 | `/api/report` | 3 | 数据聚合、报告下载 |
| 12 | 成绩管理 | `/api/grades` | 8 | 实训/教师/综合成绩闭环 |
| 13 | 成就系统 | `/api/achievements` | 8 | 成就、挑战任务 |
| 14 | 文件上传 | `/api/files` | 3 | 通用文件上传/下载 |

合计 **108** 个接口。

---

## 三、认证模块 `/api/auth`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/encrypt?pwd=` | 明文密码 RSA 加密（用于账号密码登录前） |
| 2 | POST | `/login` | 用户登录（支持账号密码 / SSO Token 两种方式） |
| 3 | GET | `/session` | 会话校验（仅判断本地登录态，不调外部 SSO） |
| 4 | GET | `/class-students` | 班级学生列表 + 实训进度（教师/管理员） |
| 5 | GET | `/platform-progress` | 平台整体进度概览（按角色返回不同粒度） |

### POST `/api/auth/login`

**请求体**（两种方式二选一，URL 携带 `?token=xxx` 时优先走 SSO）：

```json
// 方式一：账号密码
{
  "username": "student01",
  "passwordEncode": "调用 /encrypt 获取的加密密码"
}

// 方式二：SSO Token
{ "TOKEN": "xxx" }
```

**响应**：

```json
{
  "userId": 1001,
  "name": "李同学",
  "username": "student01",
  "studentId": "2026001",
  "accessToken": "...",
  "roleId": 4,
  "roleName": "学生",
  "classId": "cls001"
}
```

roleId 含义：`1=管理员`、`3=教师`、`4=学生`。

---

## 四、链状态与搭链教程 `/api/chain`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/status` | 链状态（模式/引擎/块高/账户/RPC） |
| 2 | GET | `/tutorial` | 获取 10 步搭链教程（48 条命令） |
| 3 | GET | `/tutorial/progress?wallet=` | 查询某钱包的搭链进度 |
| 4 | POST | `/tutorial/exec` | 按步骤序号执行教程命令（返回真实链上输出） |
| 5 | POST | `/tutorial/command` | 交互式执行单条命令 |
| 6 | POST | `/tutorial/progress/reset` | 重置搭链进度 |

### GET `/api/chain/status`

```json
{
  "mode": "evm",
  "engine": "py-evm",
  "height": 4,
  "accounts": ["0xadmin", "0xlearner", "0xmetro", "..."],
  "rpc": "http://127.0.0.1:8545",
  "group_id": 1
}
```

### POST `/api/chain/tutorial/exec`

按步骤执行预置命令，自动记录进度并触发学习事件。

```json
{ "step": 1, "cmd_index": 0, "wallet": "0xlearner" }
```

### POST `/api/chain/tutorial/command`

学生可在云桌面终端自由输入命令，后端解析并执行。

```json
{ "wallet": "0xlearner", "input": "bash build_chain.sh" }
```

---

## 五、合约管理 `/api/contracts`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/builtin` | 内置合约模板列表（ERC20/721/1155/GreenEnergy 等） |
| 2 | GET | `/builtin/{name}` | 获取内置合约源码 |
| 3 | POST | `/compile` | solc 编译合约源码 |
| 4 | POST | `/deploy` | 部署合约到链上 |
| 5 | GET | `/deployed` | 已部署合约列表 |
| 6 | GET | `/deployed/{address}` | 按地址查询已部署合约 |
| 7 | POST | `/call` | 调用已部署合约方法（读 / 写） |
| 8 | GET | `/deployed/{address}/interfaces` | 按 ABI 生成可调试接口列表 |
| 9 | POST | `/audit` | 合约安全审计 |
| 10 | GET | `/error-codes` | 错误码字典 |

### POST `/api/contracts/compile`

```json
{
  "name": "GreenEnergy",
  "source": "pragma solidity ^0.8.0; contract GreenEnergy { ... }"
}
```

响应：`{ ok, errors, abi, bytecode, standard, name, solc_version }`

### POST `/api/contracts/deploy`

```json
{
  "name": "GreenEnergy",
  "source": "...",
  "abi": [...],
  "bytecode": "0x...",
  "deployer": "0xlearner",
  "standard": "ERC20",
  "ctor_args": [1000000]
}
```

### POST `/api/contracts/call`

```json
{
  "address": "0x83c82edd...",
  "method": "balanceOf",
  "args": ["0xlearner"],
  "caller": "0xlearner"
}
```

---

## 六、合约 IDE `/api/ide`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/projects` | 项目列表 |
| 2 | POST | `/projects` | 新建项目（名称需含 `.sol`） |
| 3 | DELETE | `/projects/{pid}` | 删除项目 |
| 4 | GET | `/projects/{pid}/files` | 项目文件列表 |
| 5 | GET | `/files/{fid}` | 读取文件内容 |
| 6 | POST | `/files` | 保存文件 |
| 7 | DELETE | `/files/{fid}` | 删除文件 |
| 8 | GET | `/projects/{pid}/interfaces` | 项目合约接口列表 |

---

## 七、绿色低碳联盟链 `/api/eco`

> 平台核心业务模块，覆盖 6 个联盟角色、能量发放、植树证书、勋章、资产市场等闭环场景。

### 7.1 角色管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/roles` | 获取 6 个联盟角色定义 |
| 2 | POST | `/role/select` | 选择/切换角色 |
| 3 | GET | `/role/current?wallet=` | 查询当前选中角色 |

**POST `/api/eco/role/select`**

```json
{ "wallet": "0xmetro", "role_key": "metro" }
```

### 7.2 系统合约部署

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 4 | GET | `/contracts/status` | 3 份系统合约（GreenEnergy/PlantCertificate/EcoBadge）部署状态 |
| 5 | GET | `/contracts/builtin` | 内置合约源码 |
| 6 | POST | `/contracts/deploy` | 部署系统合约（链上 owner 为 0xadmin） |

**POST `/api/eco/contracts/deploy`**

```json
{ "wallet": "0xadmin", "contract_name": "GreenEnergy" }
```

### 7.3 能量发放（核心闭环）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 7 | POST | `/energy/issue` | 联盟角色凭业务凭证签发能量 |
| 8 | GET | `/energy/records?wallet=` | 能量发放记录 |
| 9 | GET | `/energy/balance?wallet=` | 能量余额 |

**POST `/api/eco/energy/issue`**

由联盟角色钱包签发，发到学生钱包。`proof` 字段按 `role_key` 不同传入对应业务凭证：

```json
{
  "wallet": "0xlearner",
  "role_key": "metro",
  "proof": {
    "station_in": "国贸站",
    "station_out": "西二旗站",
    "distance_km": 12,
    "trip_no": "BJ202608070001"
  },
  "force": false
}
```

响应（含完整溯源字段）：

```json
{
  "ok": true,
  "points": 50,
  "tx_hash": "0x...",
  "action": "地铁通勤",
  "proof_no": "BJ202608070001",
  "proof_validated": true,
  "proof_threshold": "distance_km ≥ 10 km",
  "issued_by": "0xmetro",
  "received_by": "0xlearner",
  "contract": "0x83c82edd...",
  "method": "GreenEnergy.mint(to,value,reason)"
}
```

> 凭证需满足阈值校验（地铁 ≥10km、公交 ≥5min、骑行 ≥2km、外卖无需餐具、回收 ≥1kg），否则 `proof_validated=false` 且不发能量。

### 7.4 植树证书

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 10 | GET | `/trees` | 可兑换树种列表 |
| 11 | POST | `/trees/add` | 添加树种（管理员） |
| 12 | POST | `/certificates/exchange` | 兑换植树证书（消耗能量） |
| 13 | GET | `/certificates/list?wallet=` | 证书列表 |

**POST `/api/eco/trees/add`**

```json
{
  "name": "银杏树",
  "required_energy": 1000,
  "image_url": "",
  "description": "城市绿化",
  "wallet": "0xadmin"
}
```

**POST `/api/eco/certificates/exchange`**

```json
{ "wallet": "0xlearner", "species_id": 1 }
```

### 7.5 勋章与骑行券

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 14 | GET | `/badges/types` | 勋章类型列表 |
| 15 | POST | `/badges/types/add` | 新增勋章类型（联盟角色） |
| 16 | POST | `/badges/exchange` | 兑换勋章（消耗能量） |
| 17 | POST | `/badges/mint` | 联盟角色直接铸造发放 |
| 18 | GET | `/badges/list?wallet=` | 用户勋章列表 |

**POST `/api/eco/badges/exchange`**

```json
{ "wallet": "0xlearner", "badge_type": "badge", "type_id": 1 }
```

**POST `/api/eco/badges/mint`**

```json
{
  "wallet": "0xmetro",
  "role_key": "metro",
  "type_id": 1,
  "to_wallet": "0xlearner",
  "quantity": 1
}
```

### 7.6 资产市场

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 19 | POST | `/market/list` | 挂牌绿色资产（能量/证书/勋章） |
| 20 | GET | `/market/items` | 市场在售资产列表 |
| 21 | POST | `/market/buy` | 购买资产（能量转账 + NFT 转移） |
| 22 | POST | `/market/cancel` | 取消挂牌 |

**POST `/api/eco/market/list`**

```json
{
  "seller": "0xlearner",
  "asset_type": "certificate",
  "asset_id": 1,
  "price_energy": 1000
}
```

**POST `/api/eco/market/buy`**

```json
{ "buyer": "0xalice", "listing_id": 1 }
```

### 7.7 联盟钱包与异常

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 23 | GET | `/wallet/{wallet}` | 联盟钱包综合数据（角色/能量/证书/勋章） |
| 24 | POST | `/errors/record` | 记录操作异常 |
| 25 | GET | `/errors/list?wallet=` | 异常记录列表 |

---

## 八、钱包管理 `/api/wallet`

> ERC20 通用钱包：发行、转账、余额查询。

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/issue` | 发行 ERC20 代币（仅 `0xadmin` 管理员可操作） |
| 2 | GET | `/tokens` | 代币列表 |
| 3 | GET | `/balance?wallet=&token_address=` | 查询余额 |
| 4 | GET | `/balances/{wallet}` | 钱包所有代币余额 |
| 5 | POST | `/transfer` | ERC20 转账 |
| 6 | GET | `/transfers/{wallet}` | 转账记录 |

**POST `/api/wallet/issue`**

```json
{
  "name": "GreenEnergy",
  "symbol": "GE",
  "decimals": 18,
  "total_supply": "1000000",
  "owner": "0xadmin"
}
```

**POST `/api/wallet/transfer`**

```json
{
  "token_address": "0x83c82edd...",
  "from_addr": "0xlearner",
  "to_addr": "0xadmin",
  "amount": "100"
}
```

---

## 九、NFT 资产 `/api/nft`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/mint` | 铸造 NFT（ERC721/ERC1155） |
| 2 | GET | `/list` | NFT 列表 |
| 3 | GET | `/{token_id}` | NFT 详情 |
| 4 | POST | `/buy` | 购买 NFT |
| 5 | GET | `/{token_id}/trades` | NFT 交易记录 |
| 6 | POST | `/upload` | 上传 NFT 图片 |

**POST `/api/nft/mint`**

```json
{
  "standard": "ERC721",
  "title": "植树证书 #1",
  "description": "银杏树",
  "image_url": "https://...",
  "author": "0xlearner",
  "price": "100",
  "contract_address": null
}
```

---

## 十、区块链浏览器 `/api/explorer`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/overview` | 链上总览（块高/交易数/合约数/Gas） |
| 2 | GET | `/blocks?limit=` | 最近区块列表 |
| 3 | GET | `/blocks/{number}` | 按高度查询区块 |
| 4 | GET | `/txs?limit=` | 最近交易列表 |
| 5 | GET | `/txs/{tx_hash}` | 按哈希查询交易 |
| 6 | GET | `/contracts` | 已部署合约列表 |
| 7 | GET | `/contracts/{address}` | 按地址查询合约 |
| 8 | GET | `/address/{addr}` | 地址详情（余额/交易/合约） |
| 9 | GET | `/gas/analysis` | Gas 消耗分析 |
| 10 | GET | `/gas/trend` | Gas 趋势 |
| 11 | GET | `/token/economics` | 代币经济模型 |
| 12 | GET | `/data/consistency` | 数据一致性检查 |
| 13 | GET | `/performance/metrics` | 性能指标 |

---

## 十一、调用监听器 `/api/monitor`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/{address}` | 合约调用统计 |
| 2 | GET | `/{address}/methods` | 方法级调用统计 |
| 3 | GET | `/{address}/recent` | 最近调用记录 |

---

## 十二、云桌面 `/api/cloud`

> 学生在浏览器内体验 Linux 终端，配合搭链教程使用。

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/files` | 虚拟文件系统列表 |
| 2 | POST | `/files` | 创建/保存文件 |
| 3 | GET | `/tree` | 文件树结构 |
| 4 | GET | `/autocomplete?input=` | 命令自动补全 |

---

## 十三、实训报告 `/api/report`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/aggregate` | 全平台数据聚合报告（管理员/教师） |
| 2 | GET | `/wallet/{wallet}` | 按 wallet 生成学生实训报告 |
| 3 | GET | `/download?wallet=&format=` | 下载报告（`format=markdown|json`） |

---

## 十四、成绩管理 `/api/grades`

> **权限**：仅教师（roleId=3）和管理员（roleId=1）可访问，学生（roleId=4）禁止。
>
> **三段式成绩闭环**：
> - 实训成绩（training_score）：平台数据自动计算（链搭建 20% + 合约 30% + 链上验证 25% + 联盟治理 25%）
> - 教师评分（score）：教师手动录入
> - 综合成绩（final_score）：实训 × 0.6 + 教师 × 0.4

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `/list` | 成绩列表（含实训/教师/综合 3 项） |
| 2 | GET | `/stats` | 按课程聚合统计 |
| 3 | POST | `/compute-training` | 按 wallet 实时计算实训成绩明细（不入库） |
| 4 | POST | `/upsert` | 新增/更新成绩记录（按 学号+课程 唯一） |
| 5 | POST | `/refresh-training` | 批量重算所有记录的实训成绩（教师一键刷新） |
| 6 | GET | `/my?wallet=` | 学生查看自身成绩 |
| 7 | POST | `/auto-draft` | 学生完成 10 步教程后自动创建成绩草稿 |
| 8 | DELETE | `/{grade_id}` | 删除成绩记录 |

**POST `/api/grades/compute-training`**

```json
{ "wallet": "0xlearner", "manual_score": 85 }
```

响应（4 维加权明细）：

```json
{
  "training_score": 78.5,
  "detail": {
    "chain_setup":  { "score": 80, "weight": 0.20, "metrics": {} },
    "contract_dev": { "score": 90, "weight": 0.30, "metrics": {} },
    "chain_verify": { "score": 70, "weight": 0.25, "metrics": {} },
    "alliance_gov": { "score": 75, "weight": 0.25, "metrics": { "energy_issue": 21 } }
  }
}
```

**POST `/api/grades/upsert`**

```json
{
  "student_id": "2026001",
  "student_name": "李同学",
  "course": "联盟链实训",
  "score": 85,
  "wallet": "0xlearner",
  "class_id": "cls001"
}
```

---

## 十五、成就系统 `/api/achievements`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET | `` | 所有成就定义 |
| 2 | GET | `/my?wallet=` | 用户已获成就 |
| 3 | POST | `/check` | 检查并发放成就 |
| 4 | GET | `/stats` | 成就统计 |
| 5 | GET | `/challenges` | 挑战任务列表 |
| 6 | GET | `/challenges/my?wallet=` | 用户挑战进度 |
| 7 | POST | `/challenges/start` | 开始挑战 |
| 8 | POST | `/challenges/progress` | 更新挑战进度 |

**POST `/api/achievements/challenges/start`**

```json
{ "wallet": "0xlearner", "challenge_id": 1 }
```

**POST `/api/achievements/challenges/progress`**

```json
{ "wallet": "0xlearner", "challenge_id": 1, "progress": 50 }
```

---

## 十六、文件上传 `/api/files`

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/upload` | 上传文件（multipart/form-data） |
| 2 | GET | `/download/{name}` | 下载文件 |
| 3 | GET | `/meta/{name}` | 文件元信息 |

---

## 附录 A：角色与钱包映射

| 角色 Key | 角色名称 | 钱包地址 | 能量规则 |
|----------|---------|----------|---------|
| admin | 管理员 | 0xadmin | 不发能量，管理树种/系统合约 |
| metro | 地铁集团 | 0xmetro | 乘坐地铁(≥10km) +50 |
| bus | 公交集团 | 0xbus | 乘坐公交(≥5min) +20 |
| bike | 共享单车 | 0xbike | 骑行(≥2km) +15 |
| takeout | 外卖平台 | 0xtakeout | 无需餐具 +10 |
| recycling | 回收公司 | 0xrecycle | 回收(≥1kg) +100 |
| — | 学习者 | 0xlearner | 学生默认钱包，合约部署者 |
| — | Alice | 0xalice | 低碳用户 |
| — | Bob | 0xbob | 低碳用户 |
| — | 铸造专员 | 0xminter | NFT 铸造方 |

## 附录 B：学习事件类型（用于成绩计算）

| event_type | 含义 | 计入维度 |
|------------|------|---------|
| `chain_setup` | 搭链步骤完成 | 链搭建 |
| `interface_invoke` | 接口调用 | 链上验证 |
| `contract_deploy` | 合约部署 | 合约开发 |
| `contract_call` | 合约调用 | 链上验证 |
| `eco_role_switch` | 联盟角色切换 | 联盟治理 |
| `energy_issue` | 能量发放 | 联盟治理 |
| `nft_mint` | NFT 铸造 | 联盟治理 |
| `transfer` | 转账 | 联盟治理 |
| `report_view` | 报告查看 | 链上验证 |
