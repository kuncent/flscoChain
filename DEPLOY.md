# 部署指南

> 联盟链实训平台 = 前端 (Vue3 + Vite) + 后端 (FastAPI) + 链 (EVM 沙盒)
>
> **默认 `CHAIN_MODE=evm`，零外部依赖，无需 Docker 即可运行。**

---

## 一、环境要求

| 依赖 | 最低版本 | 用途 |
|------|---------|------|
| Python | 3.10+ | 后端运行时 |
| Node.js | 18+ | 前端构建 |
| Git | 任意 | 拉取代码 |

生产环境可选：Nginx（反代）、Docker（仅当使用真实 FISCO-BCOS 链时）。

---

## 二、快速开始（开发环境，3 步搞定）

### Step 1 · 拉代码

```bash
git clone <your-repo-url> chain
cd chain
```

### Step 2 · 启动后端

**Linux / macOS：**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 默认 evm 模式，无需改动
python run.py
```

**Windows (PowerShell)：**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python run.py
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。
浏览器打开 http://localhost:8000/docs 可见 API 文档。

> **提示**：首次启动会自动播种实训基础数据（部署 3 份系统合约 + 预置角色钱包），约需 10 秒。

### Step 3 · 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 即可使用。

---

## 三、生产部署（Linux）

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm nginx curl
```

如果 Node 版本 < 18，升级到 20：

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2. 部署后端

```bash
sudo mkdir -p /opt/chain
sudo chown $USER /opt/chain
cd /opt/chain
git clone <your-repo-url> .

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

注册为系统服务（开机自启 + 崩溃自动重启）：

```bash
# 创建运行用户（若不存在）
sudo useradd -r -s /sbin/nologin chain-app 2>/dev/null || true
sudo chown -R chain-app:chain-app /opt/chain

# 注册服务
sudo cp /opt/chain/deploy/chain-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chain-backend

# 确认状态：应显示 active (running)
sudo systemctl status chain-backend
```

### 3. 构建前端

```bash
cd /opt/chain/frontend
npm ci
npm run build                  # 产物在 dist/

sudo mkdir -p /var/www/chain
sudo rm -rf /var/www/chain/*
sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain
```

### 4. 配置 Nginx 反代

```bash
sudo cp /opt/chain/deploy/nginx.chain.conf /etc/nginx/sites-available/chain
sudo ln -sf /etc/nginx/sites-available/chain /etc/nginx/sites-enabled/chain
sudo rm -f /etc/nginx/sites-enabled/default

# 改成你的域名
sudo sed -i 's/chain.your-school.edu.cn/你的域名/g' /etc/nginx/sites-available/chain

sudo nginx -t                 # 语法检查
sudo systemctl reload nginx
```

### 5. 启用 HTTPS（需 DNS 已解析到本机）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名 --non-interactive --agree-tos -m 你的邮箱
```

### 6. 开放防火墙

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

### 7. 验证部署

```bash
curl https://你的域名/health     # 应返回 {"status":"ok","mode":"evm"}
curl -I https://你的域名/         # 应返回 HTTP/2 200
```

浏览器打开 `https://你的域名/`，登录后能看到 Dashboard 即部署完成。

---

## 四、生产部署（Windows Server）

### 1. 安装依赖

- [Python 3.10+](https://www.python.org/downloads/) （安装时勾选 "Add to PATH"）
- [Node.js 18+ LTS](https://nodejs.org/)
- [NSSM](https://nssm.cc/) （把后端注册为 Windows 服务）

### 2. 部署后端

```powershell
# 假设代码放在 C:\chain
cd C:\chain\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

用 NSSM 注册为 Windows 服务：

```powershell
nssm install ChainBackend C:\chain\backend\.venv\Scripts\python.exe
nssm set ChainBackend AppParameters "C:\chain\backend\run.py"
nssm set ChainBackend AppDirectory C:\chain\backend
nssm set ChainBackend AppEnvironmentExtra CHAIN_MODE=evm
nssm start ChainBackend
```

### 3. 构建并部署前端

```powershell
cd C:\chain\frontend
npm ci
npm run build
# 将 dist\ 目录下所有文件复制到 IIS 站点根目录
```

IIS 需添加 `web.config` 支持 SPA 路由（history 模式）和 `/api` 反代到 `http://127.0.0.1:8000`。

### 4. 一键脚本（可选）

```powershell
# 管理员身份执行
C:\chain\scripts\deploy-windows.bat
```

---

## 五、配置说明

### 后端配置 `backend/.env`

```ini
# 链模式：evm=进程内沙盒(默认) | fisco=连接真实FISCO节点 | mock=内存模拟
CHAIN_MODE=evm

# 后端服务
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# SSO 登录对接（按需修改）
EXTERNAL_API_BASE=https://ecosim.sztzjy.com:166/server

# ===== 以下仅 CHAIN_MODE=fisco 时生效 =====
FISCO_RPC_HOST=127.0.0.1
FISCO_RPC_PORT=8545
FISCO_GROUP_ID=1
FISCO_CERT_DIR=
```

### 前端配置 `frontend/.env.production`

```ini
# 同域部署（Nginx 反代 /api 到后端）：留空
VITE_API_BASE=

# 跨域部署：填后端完整地址
# VITE_API_BASE=https://api.chain.your-school.edu.cn
```

### 切换为真实 FISCO-BCOS 链（可选）

如果需要让学生接触真实的 4 节点联盟链：

```bash
cd /opt/chain/deploy
bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545
docker-compose up -d               # 启动 4 节点联盟链
```

修改 `/opt/chain/backend/.env`：

```ini
CHAIN_MODE=fisco
FISCO_RPC_HOST=127.0.0.1
FISCO_RPC_PORT=8545
```

重启后端即可：

```bash
sudo systemctl restart chain-backend
```

---

## 六、常用运维命令

### Linux

```bash
sudo systemctl restart chain-backend     # 重启后端
sudo systemctl reload nginx              # 重载 Nginx
journalctl -u chain-backend -f           # 后端实时日志
sudo tail -f /var/log/nginx/chain.error.log   # Nginx 错误日志
```

### Windows

```powershell
nssm restart ChainBackend                # 重启后端
nssm stop ChainBackend                   # 停止后端
nssm status ChainBackend                 # 查看状态
```

### 发布新版本

```bash
# Linux
cd /opt/chain && git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart chain-backend

cd ../frontend && npm ci && npm run build
sudo rm -rf /var/www/chain/* && sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain
sudo systemctl reload nginx
```

```powershell
# Windows
cd C:\chain && git pull
cd backend && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt
nssm restart ChainBackend
cd ..\frontend && npm ci && npm run build
# 复制 dist\ 到 IIS 站点目录
```

### 数据备份

数据库为 SQLite，文件位于 `backend/app/storage/db/chain.sqlite3`：

```bash
# 备份
cp backend/app/storage/db/chain.sqlite3 backup-$(date +%Y%m%d).sqlite3

# 恢复
systemctl stop chain-backend
cp backup-20260825.sqlite3 backend/app/storage/db/chain.sqlite3
systemctl start chain-backend
```

---

## 七、故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 前端 5173 打不开 | Vite 未启动 | `cd frontend && npm run dev` |
| 后端 8000 无响应 | 端口占用/进程未启 | `lsof -i:8000` 查端口；`systemctl status chain-backend` |
| 页面空白 + 控制台报 API 404 | Nginx 未反代 /api | 检查 nginx.chain.conf 的 `location /api/` |
| 登录失败 | SSO 地址不对 | 修改 `backend/.env` 中 `EXTERNAL_API_BASE` |
| 合约调用报错 | 合约未部署 | 首次启动会自动播种；或进「合约管理」页手动部署 |
| 云桌面终端无响应 | WebSocket 未代理 | Nginx 需配 `location /api/cloud/ws` 的 Upgrade 头（已含在 nginx.chain.conf） |
| 首次启动很慢 | 正在播种基础数据 | 等待约 10 秒，看后端日志确认 `seed_init_data` 完成 |
| `systemctl status` 显示 failed | venv 路径或权限错误 | 确认 `/opt/chain/backend/.venv/bin/uvicorn` 存在；`chown -R chain-app:chain-app /opt/chain` |
