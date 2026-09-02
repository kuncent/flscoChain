# 生产部署文档

> 联盟链实训平台：前端 Vue3 + Vite ｜ 后端 FastAPI ｜ 链默认为内置 EVM 沙盒（零外部依赖）
>
> 目标架构：**Nginx（静态 + 反代）→ 后端 8000 端口**，单机即可运行。

---

## 1. 环境要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端运行时 |
| Node.js | 18+ | 仅构建前端，装完可卸 |
| Nginx | 任意稳定版 | 静态托管 + API 反代 |

```bash
# Ubuntu/Debian 一键安装
sudo apt update
sudo apt install -y python3-venv python3-pip nginx
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## 2. 部署后端

```bash
sudo mkdir -p /opt/chain && sudo chown $USER /opt/chain
cd /opt/chain
git clone <your-repo-url> .

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2.1 修改 `.env`（生产必改项）

```ini
CHAIN_MODE=evm                 # 默认即可，零外部依赖
JWT_SECRET=<openssl rand -base64 48 的输出>
KEYSTORE_PASSWORD=<强口令，设置后勿再更换，否则已有私钥无法解密>
AUTH_DEV_HEADER_FALLBACK=false # 生产必须为 false
# 同域部署经 Nginx 反代时，把访问域名加入 CORS 白名单
CORS_ORIGINS=https://chain.your-school.edu.cn
```

### 2.2 注册 systemd 服务

```bash
sudo useradd -r -s /sbin/nologin chain-app 2>/dev/null || true
sudo chown -R chain-app:chain-app /opt/chain

# 编辑服务文件：evm 模式链状态为进程内单例，必须 --workers 1（多进程会分裂链数据）
sudo cp /opt/chain/deploy/chain-backend.service /etc/systemd/system/
sudo sed -i 's/--workers 4/--workers 1/' /etc/systemd/system/chain-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now chain-backend
sudo systemctl status chain-backend     # 应显示 active (running)
```

验证：`curl http://127.0.0.1:8000/health` 返回 `{"status":"ok","mode":"evm"}` 即成功。
首次启动会自动播种基础数据（部署 3 份系统合约 + 预置角色钱包），约 10 秒。

---

## 3. 构建并发布前端

```bash
cd /opt/chain/frontend
cp .env.production.example .env.production   # 同域部署 VITE_API_BASE 留空即可
npm ci
npm run build

sudo mkdir -p /var/www/chain
sudo rm -rf /var/www/chain/*
sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain
```

---

## 4. 配置 Nginx

```bash
sudo cp /opt/chain/deploy/nginx.chain.conf /etc/nginx/sites-available/chain
sudo ln -sf /etc/nginx/sites-available/chain /etc/nginx/sites-enabled/chain
sudo rm -f /etc/nginx/sites-enabled/default

# 全局替换为你的域名
sudo sed -i 's/chain.your-school.edu.cn/你的域名/g' /etc/nginx/sites-available/chain

sudo nginx -t && sudo systemctl reload nginx
```

> 该配置已包含：SPA 路由兜底、`/api/` 反代、云桌面 WebSocket（`/api/cloud/ws`）、
> SSE 事件推送（`/api/notify/` 禁缓冲）、静态上传 `/static/`、健康检查 `/health`。

### 4.1 启用 HTTPS（DNS 已解析后执行）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名 --non-interactive --agree-tos -m 你的邮箱
```

### 4.2 开放防火墙

```bash
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable
```

---

## 5. 验证部署

```bash
curl https://你的域名/health          # {"status":"ok","mode":"evm"}
curl -I https://你的域名/             # HTTP/2 200
```

浏览器打开 `https://你的域名/`，登录后能看到 Dashboard 即部署完成。

**切换为真实 FISCO-BCOS 链（可选）：**
```bash
cd /opt/chain/deploy
bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545
docker compose up -d
# backend/.env 改为 CHAIN_MODE=fisco 后：sudo systemctl restart chain-backend
```

---

## 6. 日常运维

```bash
sudo systemctl restart chain-backend          # 重启后端
journalctl -u chain-backend -f                # 后端实时日志
sudo systemctl reload nginx                   # 重载 Nginx
sudo tail -f /var/log/nginx/chain.error.log   # Nginx 错误日志
```

### 发布新版本

```bash
cd /opt/chain && git pull
cd backend && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart chain-backend
cd ../frontend && npm ci && npm run build
sudo rm -rf /var/www/chain/* && sudo cp -r dist/. /var/www/chain/
sudo chown -R www-data:www-data /var/www/chain
sudo systemctl reload nginx
```

### 数据备份

SQLite 数据库位于 `backend/app/storage/db/chain.sqlite3`：

```bash
cp /opt/chain/backend/app/storage/db/chain.sqlite3 backup-$(date +%Y%m%d).sqlite3
# 恢复：停服务 → 覆盖文件 → 起服务
```

---

## 7. 故障排查速查

| 现象 | 解决 |
|------|------|
| 页面空白 / API 404 | 检查 Nginx `location /api/` 反代是否生效 |
| 浏览器控制台 CORS 报错 | 把实际访问域名加入 `backend/.env` 的 `CORS_ORIGINS` 后重启后端 |
| 登录失败 | 检查 `.env` 中 SSO 地址 `EXTERNAL_API_BASE` |
| 云桌面终端 / SSE 事件不推送 | 确认 Nginx 配置保留了 WebSocket 与 `/api/notify/` 段落 |
| 合约调用报错 | 首次启动自动播种；或在「合约管理」页手动部署 |
| 服务 failed 启动不了 | `journalctl -u chain-backend -n 50` 看日志；确认 venv 路径与目录属主 `chain-app` |

> Windows Server 部署（NSSM + IIS）：参见 `scripts/deploy-windows.bat` 与旧版文档归档。
