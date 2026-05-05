#!/bin/bash
set -e

echo "===== 油价查询服务部署脚本 ====="

# 检查环境
if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose 未安装"
    exit 1
fi

# 检查 AMAP_KEY
if [ -z "$AMAP_KEY" ]; then
    echo "警告: 未设置 AMAP_KEY 环境变量，加油站搜索功能将不可用"
    echo "如需使用加油站搜索，请先执行: export AMAP_KEY=你的高德Key"
fi

# 构建并启动
echo "正在构建镜像..."
docker-compose build --no-cache

echo "正在启动服务..."
docker-compose up -d

echo "等待服务启动..."
sleep 5

# 健康检查
echo "检查服务健康状态..."
if curl -s http://localhost:8000/api/health > /dev/null; then
    echo "✅ 服务部署成功！"
    echo ""
    echo "访问地址:"
    echo "  - 本机: http://127.0.0.1:8000"
    echo "  - 公网: http://$(curl -s ifconfig.me 2>/dev/null || echo '你的服务器IP'):8000"
    echo ""
    echo "API 接口:"
    echo "  - 健康检查: GET /api/health"
    echo "  - 油价查询: GET /api/oil"
    echo "  - 油价预测: GET /api/oil/prediction"
    echo "  - 省份油价: GET /api/oil/province/:name"
    echo "  - 附近加油站: GET /api/station/nearby"
    echo ""
    echo "查看日志: docker-compose logs -f"
    echo "停止服务: docker-compose down"
else
    echo "❌ 服务启动失败，查看日志:"
    docker-compose logs
    exit 1
fi
