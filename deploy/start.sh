#!/bin/bash
# 启动 / 更新 / 停止服务
# 用法:
#   bash deploy/start.sh          — 拉取最新代码并启动
#   bash deploy/start.sh stop     — 停止所有服务
#   bash deploy/start.sh restart  — 重启所有服务
#   bash deploy/start.sh status   — 查看运行状态
#   bash deploy/start.sh check    — 检查 API 连通性
#   bash deploy/start.sh logs     — 查看 Agent 日志

set -e
COMMAND=${1:-start}
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

PYTHON=".venv/bin/python3"
AGENT_LOG="logs/agent.log"
WEB_LOG="logs/web.log"
AGENT_PID="agent.pid"
WEB_PID="web.pid"

mkdir -p logs

stop_service() {
    local pid_file=$1
    local name=$2
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "  $name 已停止 (PID $PID)"
        fi
        rm -f "$pid_file"
    else
        echo "  $name 未在运行"
    fi
}

case "$COMMAND" in

start)
    echo "=== 拉取最新代码 ==="
    git pull --ff-only 2>/dev/null || echo "  (跳过 git pull，本地修改存在)"

    echo ""
    echo "=== 更新依赖 ==="
    .venv/bin/pip install -r requirements.txt --quiet

    echo ""
    echo "=== 停止旧进程 ==="
    stop_service "$AGENT_PID" "Agent"
    stop_service "$WEB_PID"   "Web 面板"
    rm -f agent.stop
    sleep 1

    echo ""
    echo "=== 启动服务 ==="

    # 启动 Agent
    nohup $PYTHON cli.py start >> "$AGENT_LOG" 2>&1 &
    echo $! > "$AGENT_PID"
    echo "  ✓ Agent 启动 (PID $!)"

    # 启动 Web 面板
    nohup $PYTHON cli.py web --port 8080 >> "$WEB_LOG" 2>&1 &
    echo $! > "$WEB_PID"
    echo "  ✓ Web 面板启动 (PID $!) → http://$(hostname -I | awk '{print $1}'):8080"

    echo ""
    echo "查看日志: bash deploy/start.sh logs"
    ;;

stop)
    echo "=== 停止服务 ==="
    # 优雅停止 Agent
    $PYTHON cli.py stop 2>/dev/null || true
    sleep 2
    stop_service "$AGENT_PID" "Agent"
    stop_service "$WEB_PID"   "Web 面板"
    echo "已停止。"
    ;;

restart)
    bash "$0" stop
    sleep 1
    bash "$0" start
    ;;

status)
    echo "=== 服务状态 ==="
    for entry in "Agent:$AGENT_PID" "Web面板:$WEB_PID"; do
        name="${entry%%:*}"
        pid_file="${entry##*:}"
        if [ -f "$pid_file" ]; then
            PID=$(cat "$pid_file")
            if kill -0 "$PID" 2>/dev/null; then
                echo "  ✓ $name 运行中 (PID $PID)"
            else
                echo "  ✗ $name 已退出 (PID 文件残留)"
            fi
        else
            echo "  ✗ $name 未运行"
        fi
    done
    echo ""
    $PYTHON cli.py status 2>/dev/null || echo "  (数据库未初始化)"
    ;;

check)
    $PYTHON cli.py check
    ;;

logs)
    echo "=== Agent 日志 (Ctrl+C 退出) ==="
    tail -f "$AGENT_LOG"
    ;;

*)
    echo "用法: bash deploy/start.sh [start|stop|restart|status|check|logs]"
    exit 1
    ;;

esac
