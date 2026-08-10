#!/bin/bash
set -e

# ============================================================
# 油价查询服务 - Nginx远程服务器一键部署脚本
# 用法: ./deploy-remote.sh 服务器IP
# 示例: ./deploy-remote.sh 123.456.789.0
# ============================================================

SERVER_IP=$1

if [ -z "$SERVER_IP" ]; then
    echo "用法: $0 <服务器IP>"
    echo "示例: $0 123.456.789.0"
    exit 1
fi

echo "===== 油价查询服务Nginx部署 ====="
echo "目标服务器: $SERVER_IP"
echo ""

# 1. 本地打包
echo "[1/5] 正在本地打包代码..."
cd "$(dirname "$0")"
tar czvf /tmp/oil-server-deploy.tar.gz \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='*.tar.gz' \
    api.py config.py requirements.txt \
    spider/ Dockerfile docker-compose.yml \
    nginx.conf deploy.sh

# 2. 上传到服务器
echo "[2/5] 正在上传到服务器..."
scp /tmp/oil-server-deploy.tar.gz root@$SERVER_IP:/tmp/

# 3. 服务器上执行部署
echo "[3/5] 正在服务器上部署..."
ssh root@$SERVER_IP << EOF
    set -e
    
    # 创建应用目录
    mkdir -p /opt/oil-server
    cd /opt/oil-server
    
    # 解压代码
    tar xzvf /tmp/oil-server-deploy.tar.gz
    
    # 构建并启动
    echo "[4/5] 正在构建Docker镜像..."
    docker-compose down 2>/dev/null || true
    docker-compose up -d --build
    
    # 等待服务启动
    echo "[5/5] 等待服务启动..."
    sleep 10
    
    # 健康检查
    if curl -s http://localhost/api/health > /dev/null; then
        echo ""
        echo "✅ 部署成功！"
        echo ""
        echo "访问地址:"
        echo "  - HTTP: http://$SERVER_IP"
        echo ""
        echo "API接口:"
        echo "  - 健康检查: GET http://$SERVER_IP/api/health"
        echo "  - 油价查询: GET http://$SERVER_IP/api/oil"
        echo "  - 油价预测: GET http://$SERVER_IP/api/oil/prediction"
        echo "  - 省份油价: GET http://$SERVER_IP/api/oil/province/:name"
        echo "  - 附近加油站: GET http://$SERVER_IP/api/station/nearby"
        echo ""
        echo "运维命令:"
        echo "  - 查看日志: cd /opt/oil-server && docker-compose logs -f"
        echo "  - 重启服务: cd /opt/oil-server && docker-compose restart"
        echo "  - 停止服务: cd /opt/oil-server && docker-compose down"
        echo "  - 查看Nginx日志: docker logs wx-oil-nginx"
    else
        echo "❌ 服务启动失败，查看日志:"
        docker-compose logs
        exit 1
    fi
EOF

# 4. 清理本地临时文件
rm -f /tmp/oil-server-deploy.tar.gz

echo ""
echo "===== 部署完成 ====="
echo "请确保服务器防火墙/安全组已开放 80 端口"
