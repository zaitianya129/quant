#!/bin/bash
# 阿里云部署脚本

echo "=========================================="
echo "  A股量化系统 - 阿里云部署"
echo "=========================================="

# ==================== 配置区 ====================
# 请替换为你的阿里云信息
ALIYUN_REGISTRY="registry.cn-hangzhou.aliyuncs.com"  # 阿里云镜像仓库地址
ALIYUN_NAMESPACE="your-namespace"  # 你的命名空间
IMAGE_NAME="quant-system"
IMAGE_VERSION="v1.0.0"  # 版本号，每次更新递增

# 服务器SSH信息
SERVER_HOST="your-server-ip"  # 你的服务器公网IP
SERVER_USER="root"             # SSH用户名
SERVER_PORT="22"               # SSH端口

# ===============================================

# 完整镜像地址
FULL_IMAGE_NAME="${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${IMAGE_NAME}:${IMAGE_VERSION}"
LATEST_IMAGE_NAME="${ALIYUN_REGISTRY}/${ALIYUN_NAMESPACE}/${IMAGE_NAME}:latest"

echo ""
echo "📦 镜像信息:"
echo "   地址: ${FULL_IMAGE_NAME}"
echo "   服务器: ${SERVER_HOST}"
echo ""

# 1. 登录阿里云镜像仓库
echo "🔐 登录阿里云镜像仓库..."
echo "请输入阿里云镜像仓库密码:"
docker login --username=your-aliyun-username ${ALIYUN_REGISTRY}

if [ $? -ne 0 ]; then
    echo "❌ 登录失败"
    exit 1
fi

# 2. 构建镜像
echo ""
echo "🔨 构建镜像..."
docker build -t ${IMAGE_NAME}:${IMAGE_VERSION} .

if [ $? -ne 0 ]; then
    echo "❌ 构建失败"
    exit 1
fi

# 3. 打标签
echo ""
echo "🏷️  打标签..."
docker tag ${IMAGE_NAME}:${IMAGE_VERSION} ${FULL_IMAGE_NAME}
docker tag ${IMAGE_NAME}:${IMAGE_VERSION} ${LATEST_IMAGE_NAME}

# 4. 推送镜像
echo ""
echo "📤 推送镜像到阿里云..."
docker push ${FULL_IMAGE_NAME}
docker push ${LATEST_IMAGE_NAME}

if [ $? -ne 0 ]; then
    echo "❌ 推送失败"
    exit 1
fi

echo "✅ 镜像推送成功"

# 5. SSH到服务器并部署
echo ""
echo "🚀 开始部署到服务器..."
echo "连接到 ${SERVER_HOST}..."

ssh -p ${SERVER_PORT} ${SERVER_USER}@${SERVER_HOST} << EOF
    echo "=========================================="
    echo "  服务器部署开始"
    echo "=========================================="

    # 登录镜像仓库
    echo "🔐 登录镜像仓库..."
    docker login --username=your-aliyun-username ${ALIYUN_REGISTRY}

    # 拉取最新镜像
    echo "📥 拉取镜像..."
    docker pull ${LATEST_IMAGE_NAME}

    # 停止旧容器
    echo "⏸️  停止旧容器..."
    docker stop quant-web 2>/dev/null || true
    docker rm quant-web 2>/dev/null || true

    # 启动新容器
    echo "🚀 启动新容器..."
    docker run -d \\
        --name quant-web \\
        --restart always \\
        -p 5000:5000 \\
        -v /data/quant/cache:/app/cache \\
        -v /data/quant/logs:/app/logs \\
        -e TUSHARE_TOKEN=\$TUSHARE_TOKEN \\
        ${LATEST_IMAGE_NAME}

    # 检查容器状态
    sleep 3
    if docker ps | grep quant-web > /dev/null; then
        echo "✅ 容器启动成功"
        docker ps | grep quant-web
    else
        echo "❌ 容器启动失败"
        docker logs quant-web
        exit 1
    fi

    echo ""
    echo "=========================================="
    echo "  部署完成！"
    echo "  访问地址: http://${SERVER_HOST}:5000"
    echo "=========================================="
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 部署成功！"
    echo "访问地址: http://${SERVER_HOST}:5000"
else
    echo ""
    echo "❌ 部署失败，请检查日志"
fi
