#!/usr/bin/env bash
# 一键生成 FISCO-BCOS 4 节点联盟链配置
# 用法: bash deploy/build_chain.sh
set -e
cd "$(dirname "$0")"

CHAIN_BIN=./build_chain.sh
if [ ! -f "$CHAIN_BIN" ]; then
  echo "下载 build_chain.sh ..."
  curl -#LO https://github.com/FISCO-BCOS/FISCO-BCOS/releases/download/v2.9.1/build_chain.sh
  chmod +x build_chain.sh
fi

echo "生成 4 节点链配置（国密关闭）..."
bash build_chain.sh -l 127.0.0.1:4 -p 30300,20200,8545 -o nodes

echo "完成。目录: deploy/nodes/"
echo "启动: cd deploy && docker-compose up -d"
