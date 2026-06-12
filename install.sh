#!/bin/bash
# Polymarket AI Agent — 一键安装脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/LinChunliangliang/polymarket-ai-agent/002-polymarket-ai-agent/install.sh | bash
set -e

REPO="https://github.com/LinChunliangliang/polymarket-ai-agent.git"
BRANCH="002-polymarket-ai-agent"
INSTALL_DIR="$HOME/polymarket-agent"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${GREEN}=== $1 ===${NC}"; }

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   Polymarket AI Agent  — 安装程序     ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── 1. 检查系统依赖 ───────────────────────────────────────────
section "检查依赖"

command -v git    >/dev/null 2>&1 || { warn "git 未安装，正在安装..."; sudo apt-get install -y git -qq; }
command -v python3 >/dev/null 2>&1 || { warn "python3 未安装，正在安装..."; sudo apt-get install -y python3 python3-venv python3-pip -qq; }

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PYTHON_VER"
info "git $(git --version | awk '{print $3}')"

# ── 2. 克隆或更新仓库 ─────────────────────────────────────────
section "获取代码"

if [ -d "$INSTALL_DIR/.git" ]; then
    warn "目录已存在，拉取最新代码..."
    cd "$INSTALL_DIR"
    git pull --ff-only
    info "代码已更新"
else
    info "克隆仓库到 $INSTALL_DIR ..."
    git clone -b "$BRANCH" "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    info "克隆完成"
fi

cd "$INSTALL_DIR"

# ── 3. 创建虚拟环境 ───────────────────────────────────────────
section "配置 Python 环境"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    info "虚拟环境已创建"
else
    info "虚拟环境已存在，跳过"
fi

info "安装依赖包..."
.venv/bin/pip install -r requirements.txt --quiet
info "依赖安装完成"

# ── 4. 初始化数据库 ───────────────────────────────────────────
section "初始化数据库"

mkdir -p logs
.venv/bin/python3 -c "from src.storage.db import init_db; init_db()"
info "agent.db 初始化完成"

# ── 5. 配置文件 ───────────────────────────────────────────────
section "配置文件"

if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    warn "config.yaml 已创建，请填写以下必填项："
    echo ""
    echo "  nano $INSTALL_DIR/config.yaml"
    echo ""
    echo "  必填项："
    echo "    polymarket.private_key      — Polygon 钱包私钥"
    echo "    polymarket.chain_id         — 137 (主网) 或 80002 (沙盒)"
    echo "    deepseek.api_key            — DeepSeek API Key"
    echo "    notify.telegram_bot_token   — Telegram Bot Token"
    echo "    notify.telegram_chat_id     — 你的 Telegram Chat ID"
    echo "    risk.starting_balance_usd   — 你的起始资金（USDC）"
else
    info "config.yaml 已存在，跳过"
fi

# ── 完成 ──────────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         安装完成！                    ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "  安装目录: $INSTALL_DIR"
echo ""
echo "  下一步操作："
echo "  ① 编辑配置:      nano $INSTALL_DIR/config.yaml"
echo "  ② 检查连通性:    bash $INSTALL_DIR/deploy/start.sh check"
echo "  ③ 启动服务:      bash $INSTALL_DIR/deploy/start.sh"
echo "  ④ 查看面板:      http://$(hostname -I | awk '{print $1}' 2>/dev/null || echo 'your-vps-ip'):8080"
echo ""
