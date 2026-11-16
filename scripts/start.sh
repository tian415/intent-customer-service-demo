#!/usr/bin/env sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"
if [ ! -x backend/.venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo "请先按 README 安装前后端锁定依赖。" >&2
  exit 1
fi
backend_pid=''
frontend_pid=''
cleanup() {
  [ -z "$backend_pid" ] || kill "$backend_pid" 2>/dev/null || true
  [ -z "$frontend_pid" ] || kill "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
backend_pid=$!
(cd frontend && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) &
frontend_pid=$!
printf '%s\n' '前端 http://127.0.0.1:5173；首次使用先执行数据库账号初始化。Ctrl+C 停止两个服务。'
# Stop the sibling if either process exits; never kill a process not started here.
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done
exit 1
