#!/bin/bash
# 首次 VPS 部署脚本
# 用法: bash deploy/setup.sh
set -e

echo "=== Polymarket Agent 初始化部署 ==="

# 1. 系统依赖
echo "[1/5] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git screen

# 2. 创建虚拟环境
echo "[2/5] 创建 Python 虚拟环境..."
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
echo "[3/5] 安装 Python 依赖..."
pip install -r requirements.txt --quiet

# 4. 初始化配置
if [ ! -f config.yaml ]; then
    echo "[4/5] 创建配置文件..."
    cp config.example.yaml config.yaml
    echo ""
    echo "⚠️  请编辑 config.yaml 填入以下必填项："
    echo "    polymarket.private_key   — 钱包私钥"
    echo "    deepseek.api_key         — DeepSeek API Key"
    echo "    notify.telegram_bot_token / telegram_chat_id"
    echo ""
    echo "编辑命令: nano config.yaml"
else
    echo "[4/5] config.yaml 已存在，跳过。"
fi

# 5. 初始化数据库
echo "[5/5] 初始化数据库..."
.venv/bin/python3 -c "from src.storage.db import init_db; init_db(); print('  agent.db OK')"

echo ""
echo "=== 部署完成 ==="
echo "下一步："
echo "  1. 编辑配置: nano config.yaml"
echo "  2. 检查连通性: bash deploy/start.sh check"
echo "  3. 启动服务: bash deploy/start.sh"
