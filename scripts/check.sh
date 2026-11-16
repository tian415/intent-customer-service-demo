#!/usr/bin/env sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root/backend"
if [ ! -x .venv/bin/python ]; then
  echo "请先按 README 安装 backend/.venv 中的依赖。" >&2
  exit 1
fi
.venv/bin/python -m pytest
cd "$project_root/frontend"
npm test
npm run build
