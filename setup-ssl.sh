#!/bin/bash
set -e

DOMAIN="youngtse.top"
SSL_DIR="$(dirname "$0")/ssl"

echo "===== 申请 Let's Encrypt SSL 证书 ====="

# 安装 acme.sh
if ! command -v ~/.acme.sh/acme.sh &> /dev/null; then
    echo "安装 acme.sh..."
    curl https://get.acme.sh | sh
fi

export PATH="$HOME/.acme.sh:$PATH"

# 申请证书（standalone 模式，需临时释放 80 端口）
echo "停止 nginx 容器以释放 80 端口..."
docker stop wx-oil-nginx 2>/dev/null || true

echo "申请证书..."
~/.acme.sh/acme.sh --issue -d "$DOMAIN" --standalone --force

echo "启动 nginx 容器..."
docker start wx-oil-nginx 2>/dev/null || true

# 安装证书到 ssl 目录
mkdir -p "$SSL_DIR"
~/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \
    --fullchain-file "$SSL_DIR/fullchain.pem" \
    --key-file "$SSL_DIR/privkey.pem"

echo "✅ 证书已安装到 $SSL_DIR/"
echo ""
echo "重启 nginx 加载证书..."
docker restart wx-oil-nginx

echo "✅ 完成！自动续签由 acme.sh 定时任务处理"
