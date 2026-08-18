# FISCO-BCOS 联盟链学习平台

基于 **FISCO-BCOS**（国产主流联盟链）的工程化实训平台，参考 dinggerquant 项目 UI 风格。前端 Vue 3 + TypeScript + Vite，后端 Python FastAPI。

## 能力总览

| 模块 | 说明 |
| --- | --- |
| 云桌面 | 内嵌 Web 终端，6 步搭建真实联盟链（启动节点 / 查进程 / 查日志 / 控制台 / 部署合约 / 调用合约）|
| 智能合约 IDE | 多文件在线编辑、云端保存、在线编译 / 调试 / 部署、错误输出 |
| 接口调试 | 合约发布后自动生成接口，在线调试 + 调用监听器（次数 / 结果 / 统计）|
| 区块链浏览器 | 交易统计、块查询、交易详情、合约查询、参数解析、ERC20/721/1155 识别、地址查询 |
| NFT 仿真市场 | 一键生成 ERC721/1155、图片存储浏览下载、Token 赭买、历史记录 |
| ERC20 钱包 | 发行 Token、转账、交易记录、购买 NFT |

## 目录结构

```
chain/
├── frontend/          # Vue 3 前端
├── backend/           # FastAPI 后端
├── contracts/         # 内置 Solidity 合约（ERC20/721/1155）
├── deploy/            # FISCO-BCOS 部署 + docker-compose + systemd / nginx 模板
└── scripts/           # 启动 / 停止 / 备份 / 发布脚本
```

## 本地开发

```bash
# 1. 后端
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # CHAIN_MODE 默认 evm，零依赖
python run.py                                       # http://localhost:8000/docs

# 2. 前端
cd ../frontend
npm install
npm run dev                                         # http://localhost:5173
```

## 链模式说明

后端 `CHAIN_MODE` 三选一：

| 值 | 说明 | 外部依赖 |
| --- | --- | --- |
| `evm` | py-evm 进程内 EVM 单例（**默认，生产推荐**）| 无 |
| `fisco` | 连接真实 FISCO-BCOS 4 节点 | Docker + 节点配置 |
| `mock` | 内存模拟，重启丢失（兜底调试）| 无 |

---

## 生产部署

目标：在 Linux 服务器（Ubuntu 22.04）上把平台跑起来。链模式默认 `evm`（零外部依赖）。

### 1. 环境准备

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm nginx curl
# Node ≥ 18，若仓库版本低用 nodesource：
# curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

### 2. 拉代码

```bash
sudo mkdir -p /opt/chain && sudo chown $USER /opt/chain
cd /opt/chain
git clone <your-repo-url> .
```

### 3. 后端

```bash
cd /opt/chain/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 按需改 .env：CHAIN_MODE（默认 evm）、EXTERNAL_API_BASE（SSO 地址）
```

快速验证：

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# 另开终端：curl http://127.0.0.1:8000/health  → {"status":"ok","mode":"evm"}
# Ctrl+C 停止，下面用 systemd 守护
```

注册系统服务（模板见 [deploy/chain-backend.service](file:///e:/chain/deploy/chain-backend.service)）：

```bash
sudo cp /opt/chain/deploy/chain-backend.service /etc/systemd/system/
sudo sed -i "s|/opt/chain|$PWD|g" /etc/systemd/system/chain-backend.service  # 路径不匹配时改
sudo systemctl daemon-reload
sudo systemctl enable --now chain-backend
sudo systemctl status chain-backend   # active (running)
```

### 4. 前端构建

```bash
cd /opt/chain/frontend
npm ci
npm run build        # 产物在 dist/

# 部署到 Nginx 目录
sudo mkdir -p /var/www/chain
sudo rm -rf /var/www/chain/*
sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain
```

### 5. Nginx 配置

```bash
sudo cp /opt/chain/deploy/nginx.chain.conf /etc/nginx/sites-available/chain
sudo ln -sf /etc/nginx/sites-available/chain /etc/nginx/sites-enabled/chain
sudo rm -f /etc/nginx/sites-enabled/default
# 改 server_name 为你的域名
sudo sed -i 's/chain.your-school.edu.cn/你的域名/g' /etc/nginx/sites-available/chain
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS（可选，需 DNS 已解析）：

```bash
sudo certbot --nginx -d 你的域名 --non-interactive --agree-tos -m 你的邮箱
```

### 6. 防火墙

```bash
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable
```

### 7. 验证

```bash
curl https://你的域名/health        # {"status":"ok","mode":"evm"}
curl -I https://你的域名/           # HTTP/2 200
```

浏览器打开 `https://你的域名/`，登录 → Dashboard 进度看板 → 云桌面 → 合约 IDE，跑通即完成。

---

## 运维速查

```bash
sudo systemctl restart chain-backend        # 重启后端
sudo systemctl reload nginx                 # 重载 Nginx
journalctl -u chain-backend -f              # 后端日志
sudo tail -f /var/log/nginx/chain.error.log # Nginx 错误日志
```

## 发布新版本

```bash
cd /opt/chain && git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart chain-backend
cd ../frontend && npm ci && npm run build
sudo rm -rf /var/www/chain/* && sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain && sudo systemctl reload nginx
```