#!/bin/bash
# 本地构建和测试脚本

echo "=========================================="
echo "  A股量化系统 - 本地构建测试"
echo "=========================================="

# 1. 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装，请先安装Docker Desktop"
    exit 1
fi

echo "✅ Docker已安装"

# 2. 检查.env文件
if [ ! -f .env ]; then
    echo "⚠️  未找到.env文件，从.env.example复制..."
    cp .env.example .env
    echo "⚠️  请编辑.env文件，填入你的TUSHARE_TOKEN"
    echo "   编辑命令: nano .env 或 vim .env"
    exit 1
fi

echo "✅ .env配置文件已存在"

# 3. 构建Docker镜像
echo ""
echo "📦 开始构建Docker镜像..."
docker build -t quant-system:latest .

if [ $? -eq 0 ]; then
    echo "✅ 镜像构建成功"
else
    echo "❌ 镜像构建失败"
    exit 1
fi

# 4. 启动容器（仅Web应用，不含Nginx）
echo ""
echo "🚀 启动容器..."
docker-compose up -d quant-web

if [ $? -eq 0 ]; then
    echo "✅ 容器启动成功"
    echo ""
    echo "=========================================="
    echo "  访问地址："
    echo "  http://localhost:5000"
    echo "=========================================="
    echo ""
    echo "查看日志: docker logs quant-web -f"
    echo "停止服务: docker-compose down"
else
    echo "❌ 容器启动失败"
    exit 1
fi
