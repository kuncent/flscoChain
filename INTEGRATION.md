# 联调与启动说明

## 一、目录约定

```
chain/
├── frontend/      Vue 3 前端
├── backend/       FastAPI 后端
├── contracts/     内置 Solidity 合约
├── deploy/        FISCO-BCOS docker-compose + build_chain.sh
├── scripts/       一键启动脚本
└── README.md
```

## 二、启动顺序

### 1. 启动 FISCO-BCOS 联盟链（可选，mock 模式可跳过）

```bash
cd deploy
bash build_chain.sh          # 生成 4 节点配置
docker-compose up -d         # 启动 4 节点 + 控制台
```

### 2. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
python run.py
```

后端默认 http://localhost:8000 ，Swagger 文档 http://localhost:8000/docs 。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认 http://localhost:5173 。

### 4. 一键启动（Windows）

```bat
scripts\start.bat
```

## 三、链模式切换

复制 `.env.example` 为 `.env`，修改 `CHAIN_MODE`：

| 值 | 说明 |
| --- | --- |
| `mock` | 内存模拟链，无需真实节点，全部 UI 流程可用（默认）|
| `real` | 通过 FISCO-BCOS Python SDK 连接真实节点，需安装 python-sdk 并配置证书 |

real 模式需：
1. 安装 [FISCO-BCOS Python SDK](https://github.com/FISCO-BCOS/python-sdk)
2. 在 `.env` 中配置 `FISCO_CERT_DIR` 指向节点证书目录
3. 完善 `backend/app/chain_client.py` 中 `RealFiscoClient` 的 deploy/call 实现

## 四、功能联调路径

| 需求 | 操作路径 |
| --- | --- |
| 搭建真实链 | 云桌面 → 6 步教程（启动节点/查进程/查日志/控制台/部署/调用）|
| 编写合约 | 合约 IDE → 新建工程/文件 → 载入内置协议 → 编译 → 部署 |
| 调用合约 | 接口调试 → 选择合约 → 自动生成接口 → 填参数 → 调用 |
| 监听调用 | 调用监听器 → 选择合约 → 查看次数/方法分布/最近记录 |
| 浏览链数据 | 区块链浏览器 → 搜索块/交易/地址 → 查看详情与参数解析 |
| NFT 实践 | NFT 交易市场 → 一键铸造（上传图片）→ 详情/下载 → Token 购买 |
| 钱包实践 | ERC20 钱包 → 发行 Token → 转账 → 查看记录 → 市场 buying |

## 五、数据持久化

- SQLite: `backend/storage/db/chain.sqlite3`（自动创建）
- 上传文件: `backend/storage/uploads/`（NFT 图片等）
- 静态访问: `/static/<filename>`

## 六、验证清单

- [ ] 后端 `/health` 返回 `{"status":"ok","mode":"mock"}`
- [ ] 前端总览页显示块高、交易数、合约数
- [ ] 云桌面终端可输入 `help` 返回命令列表
- [ ] 合约 IDE 载入 ERC20 模板 → 编译成功 → 部署返回地址
- [ ] 接口调试调用 `transfer` 返回 tx_hash
- [ ] 监听器显示调用次数与方法分布
- [ ] 浏览器搜索合约地址返回交易列表
- [ ] NFT 市场上传图片铸造 → 详情可下载 → Token 购买成功
- [ ] ERC20 钱包发行 Token → 转账 → 余额与记录更新
