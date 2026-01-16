#!/bin/bash
# 一键配置脚本 - 交互式引导

echo "=========================================="
echo "  A股量化系统 - 部署配置向导"
echo "=========================================="
echo ""

# 1. 检查Docker
echo "🔍 检查Docker安装..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装"
    echo ""
    echo "请先安装Docker:"
    echo "  macOS: brew install --cask docker"
    echo "  或访问: https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo "✅ Docker已安装"
echo ""

# 2. 配置.env文件
if [ ! -f .env ]; then
    echo "📝 配置环境变量..."
    echo ""
    echo "请输入Tushare Token (在 https://tushare.pro 注册获取):"
    read -p "Token: " tushare_token

    echo "请输入一个随机字符串作为SECRET_KEY (按回车使用默认值):"
    read -p "Secret Key [默认: $(openssl rand -hex 16)]: " secret_key
    secret_key=${secret_key:-$(openssl rand -hex 16)}

    # 创建.env文件
    cat > .env << EOF
# Tushare API配置
TUSHARE_TOKEN=${tushare_token}

# Flask配置
FLASK_ENV=production
SECRET_KEY=${secret_key}

# 数据库配置
DB_PATH=./cache/stock_data.db

# Redis配置
REDIS_HOST=redis
REDIS_PORT=6379

# 日志级别
LOG_LEVEL=INFO

# 服务器配置
HOST=0.0.0.0
PORT=5000
WORKERS=4
EOF

    echo "✅ .env配置文件已创建"
else
    echo "✅ .env文件已存在，跳过配置"
fi
echo ""

# 3. 选择部署方式
echo "🚀 选择部署方式:"
echo "  1) 仅本地测试（推荐先测试）"
echo "  2) 部署到阿里云服务器"
echo ""
read -p "请选择 [1/2]: " deploy_choice

case $deploy_choice in
    1)
        echo ""
        echo "📦 开始本地构建..."
        chmod +x deploy-local.sh
        ./deploy-local.sh
        ;;
    2)
        echo ""
        echo "📦 准备部署到阿里云..."
        echo ""
        echo "请输入以下信息:"
        echo ""

        read -p "阿里云镜像仓库地址 [默认: registry.cn-hangzhou.aliyuncs.com]: " registry
        registry=${registry:-registry.cn-hangzhou.aliyuncs.com}

        read -p "命名空间 (在阿里云容器镜像服务创建): " namespace

        read -p "镜像仓库用户名: " aliyun_username

        read -p "服务器IP地址: " server_ip

        read -p "服务器SSH端口 [默认: 22]: " server_port
        server_port=${server_port:-22}

        read -p "服务器SSH用户名 [默认: root]: " server_user
        server_user=${server_user:-root}

        # 修改部署脚本
        sed -i.bak "s|ALIYUN_REGISTRY=.*|ALIYUN_REGISTRY=\"${registry}\"|" deploy-aliyun.sh
        sed -i.bak "s|ALIYUN_NAMESPACE=.*|ALIYUN_NAMESPACE=\"${namespace}\"|" deploy-aliyun.sh
        sed -i.bak "s|SERVER_HOST=.*|SERVER_HOST=\"${server_ip}\"|" deploy-aliyun.sh
        sed -i.bak "s|SERVER_PORT=.*|SERVER_PORT=\"${server_port}\"|" deploy-aliyun.sh
        sed -i.bak "s|SERVER_USER=.*|SERVER_USER=\"${server_user}\"|" deploy-aliyun.sh
        sed -i.bak "s|your-aliyun-username|${aliyun_username}|g" deploy-aliyun.sh

        rm deploy-aliyun.sh.bak

        echo ""
        echo "✅ 配置完成"
        echo ""
        echo "接下来执行:"
        echo "  chmod +x deploy-aliyun.sh"
        echo "  ./deploy-aliyun.sh"
        echo ""
        echo "⚠️  注意: 首次部署需要确保服务器已安装Docker"
        echo "   服务器执行: curl -fsSL https://get.docker.com | bash"
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "  配置完成！"
echo "=========================================="
