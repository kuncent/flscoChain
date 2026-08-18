# 生产部署快速指南

目标：在 Linux 服务器（Ubuntu 22.04）上把 FISCO 联盟链学习平台跑起来。链模式默认 `evm`（零外部依赖）。

## 1. 环境准备

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm nginx curl
# Node ≥ 18，若仓库版本低用 nodesource：
# curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

## 2. 拉代码

```bash
sudo mkdir -p /opt/chain && sudo chown $USER /opt/chain
cd /opt/chain
git clone <your-repo-url> .
```

## 3. 后端

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

## 4. 前端构建

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

## 5. Nginx 配置

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

## 6. 防火墙

```bash
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable
```

## 7. 验证

```bash
curl https://你的域名/health        # {"status":"ok","mode":"evm"}
curl -I https://你的域名/           # HTTP/2 200
```

浏览器打开 `https://你的域名/`，登录 → Dashboard 进度看板 → 云桌面 → 合约 IDE，跑通即完成。

---

## 常用命令

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

