#!/usr/bin/env bash
# 飞书发布表读写共享库（被 docker/build_image.sh 写、ictrek.app/scripts/package.sh 读）。
#
# 表结构（与 image-studio/nowen-video 共用同一张发布表）：
#   A 列 = 日期（每行一个构建日，数据区从第 4 行起）
#   组件列 = 每个镜像一列：第 1 行组件名、第 2 行镜像 repository、第 4+ 行 tag
#
# 依赖：curl + python3。凭据按序尝试 FEISHU_CONFIG_CANDIDATES 中的 JSON 文件
# （字段：feishu_app_id / feishu_app_secret）。
#
# 读侧：feishu_resolve_image <sheet标题> <组件名> <默认repo>   → 输出 repo:tag
# 写侧：feishu_record_build     <sheet标题> <组件名> <repo> <tag>
set -euo pipefail

FEISHU_SPREADSHEET_TOKEN="${FEISHU_SPREADSHEET_TOKEN:-Htotsn3oahO1zxt73YMcaB1zn8e}"
FEISHU_CONFIG_CANDIDATES=(
  "${FEISHU_CONFIG_FILE:-${HOME}/.feishu.components.json}"
  "${FEISHU_FALLBACK_CONFIG_FILE:-${HOME}/.feishu.json}"
)

_feishu_log() { echo "[feishu] $*"; }
_feishu_die() { echo "[feishu][ERROR] $*" >&2; exit 1; }

_feishu_read_field() { # <config文件> <字段>
  python3 - "$1" "$2" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
value = data.get(sys.argv[2], "")
print(value if isinstance(value, str) else str(value))
PY
}

feishu_get_token() {
  curl -sS -X POST \
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
    -H 'Content-Type: application/json' \
    -d "{\"app_id\":\"${FEISHU_APP_ID}\",\"app_secret\":\"${FEISHU_APP_SECRET}\"}" \
    | python3 -c 'import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(f"feishu token 接口响应异常（非 JSON）: {raw[:300]!r}")
if data.get("code") != 0:
    raise SystemExit(f"get_feishu_token failed: {data}")
print(data["tenant_access_token"])'
}

feishu_load_auth() {
  local file tried=""
  for file in "${FEISHU_CONFIG_CANDIDATES[@]}"; do
    [[ -n "$file" && "$tried" != *"|$file|"* ]] || continue
    tried="${tried}|${file}|"
    [[ -r "$file" ]] || continue
    FEISHU_APP_ID="$(_feishu_read_field "$file" feishu_app_id)"
    FEISHU_APP_SECRET="$(_feishu_read_field "$file" feishu_app_secret)"
    if [[ -n "${FEISHU_APP_ID}" && -n "${FEISHU_APP_SECRET}" ]]; then
      FEISHU_TOKEN="$(feishu_get_token)"
      _feishu_log "使用飞书凭据 ${file}"
      return 0
    fi
  done
  _feishu_die "无法读取飞书凭据（尝试过：${FEISHU_CONFIG_CANDIDATES[*]}）"
}

feishu_api() { # <METHOD> <url> [body]
  # 不用 --fail：理由同 feishu_get_token，错误响应体要流到下游解析并报出
  if [[ -n "${3:-}" ]]; then
    curl -sS -X "$1" "$2" -H "Authorization: Bearer ${FEISHU_TOKEN}" \
      -H 'Content-Type: application/json' --data "$3"
  else
    curl -sS -X "$1" "$2" -H "Authorization: Bearer ${FEISHU_TOKEN}"
  fi
}

feishu_get_sheet_id_by_title() { # <标题>
  # 响应必须先捕获到变量再经 argv 传给 python：
  # 若写成 "feishu_api ... | python3 - <<PY"，heredoc 会覆盖管道的 stdin，
  # json.load(sys.stdin) 读到 EOF（空串）→ "Expecting value: char 0"
  local resp
  resp="$(feishu_api GET "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/sheets/query")"
  python3 - "$1" "$resp" <<'PY'
import json, sys
title, data = sys.argv[1], json.loads(sys.argv[2])
if data.get("code") != 0:
    raise SystemExit(f"query sheets failed: {data}")
for sheet in data.get("data", {}).get("sheets", []):
    if sheet.get("title") == title:
        print(sheet["sheet_id"])
        raise SystemExit(0)
raise SystemExit(f"sheet title not found: {title}")
PY
}

feishu_get_range_values() { # <sheet_id>!<range>
  feishu_api GET "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values/$1"
}

# ---------------- 读侧 ----------------

feishu_find_component_column() { # <sheet_id> <组件名> -> 列字母（第 1 行匹配，缺失报错）
  local resp
  resp="$(feishu_get_range_values "$1!A1:ZZ1")"
  python3 - "$2" "$resp" <<'PY'
import json, sys
target, data = sys.argv[1], json.loads(sys.argv[2])
if data.get("code") != 0:
    raise SystemExit(f"read header failed: {data}")
row = (data.get("data", {}).get("valueRange", {}).get("values") or [[]])[0]

def text(v):
    if v is None: return ""
    if isinstance(v, str): return v.strip()
    if isinstance(v, dict): return str(v.get("text") or v.get("link") or "").strip()
    if isinstance(v, list): return "".join(text(x) for x in v).strip()
    return str(v).strip()

def col(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s

for i, v in enumerate(row, start=1):
    if text(v) == target:
        print(col(i))
        raise SystemExit(0)
raise SystemExit(f"component column not found: {target}")
PY
}
# 注：与 desensitize/nowen-video 对齐，此函数只做"找列"；
# 组件名/repository/日期行的写入由 feishu_record_build 完成

feishu_find_component_repository() { # <sheet_id> <列字母> -> 第 2 行的 repository
  feishu_get_range_values "$1!${2}2:${2}2" \
    | python3 -c 'import json, sys
data = json.load(sys.stdin)
if data.get("code") != 0:
    raise SystemExit(f"read component repository failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
if not values or not values[0] or not str(values[0][0]).strip():
    raise SystemExit("component repository missing from row2")
print(str(values[0][0]).strip())'
}

feishu_find_latest_tag() { # <sheet_id> <列字母> -> 数据区首个非空 tag
  feishu_get_range_values "$1!${2}4:${2}2000" \
    | python3 -c 'import json, sys
data = json.load(sys.stdin)
if data.get("code") != 0:
    raise SystemExit(f"read latest tag failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
for row in values:
    if row and row[0] is not None and str(row[0]).strip():
        print(str(row[0]).strip())
        raise SystemExit(0)
raise SystemExit("latest tag not found")'
}

feishu_resolve_image() { # <sheet标题> <组件名> <默认repo> -> repo:tag
  local sheet_id col repo tag
  # 注意：feishu_get_sheet_id_by_title 只收标题一个参数（token 走全局 FEISHU_TOKEN），
  # 不要把 tenant token 当标题传入
  sheet_id="$(feishu_get_sheet_id_by_title "$1")"
  col="$(feishu_find_component_column "$sheet_id" "$2")"
  repo="$(feishu_find_component_repository "$sheet_id" "$col" 2>/dev/null || true)"
  repo="${repo:-$3}"
  tag="$(feishu_find_latest_tag "$sheet_id" "$col")"
  [[ -n "$tag" ]] || _feishu_die "sheet ${1} 组件 ${2} 无可用 tag"
  printf '%s:%s\n' "$repo" "$tag"
}

# ---------------- 写侧 ----------------

feishu_find_date_row() { # <sheet_id> <YYYYMMDD> -> 行号（无则输出空）
  # 同 feishu_get_sheet_id_by_title：响应须经 argv 传入，不能与 heredoc 抢 stdin
  local resp
  resp="$(feishu_get_range_values "$1!A4:A2000")"
  python3 - "$2" "$resp" <<'PY'
import json, sys
target = sys.argv[1]
data = json.loads(sys.argv[2] or "{}")
if data.get("code") != 0:
    raise SystemExit(f"read date column failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
for row_num, row in enumerate(values, start=4):
    if row and str(row[0]).strip() == target:
        print(row_num)
        raise SystemExit(0)
print("")
PY
}

feishu_prepend_date_row() { # <sheet_id> <YYYYMMDD>
  feishu_api POST \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values_prepend" \
    "{\"valueRange\":{\"range\":\"$1!A4:A4\",\"values\":[[\"$2\"]]}}" \
    | python3 -c 'import json, sys
data = json.load(sys.stdin)
if data.get("code") != 0:
    raise SystemExit(f"prepend date row failed: {data}")'
}

feishu_write_cell() { # <sheet_id> <单元格> <值>
  feishu_api PUT \
    "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/${FEISHU_SPREADSHEET_TOKEN}/values" \
    "{\"valueRange\":{\"range\":\"$1!$2:$2\",\"values\":[[\"$3\"]]}}" \
    | python3 -c 'import json, sys
data = json.load(sys.stdin)
if data.get("code") != 0:
    raise SystemExit(f"write cell failed: {data}")'
}

feishu_record_build() { # <sheet标题> <组件名> <repo> <tag>
  local sheet="$1" component="$2" repository="$3" tag="$4"
  local sheet_id date_row resp col_idx col
  sheet_id="$(feishu_get_sheet_id_by_title "$sheet")"
  _feishu_log "sheet: ${sheet} -> ${sheet_id}"

  date_row="$(feishu_find_date_row "$sheet_id" "$(date +%Y%m%d)")"
  if [[ -z "$date_row" ]]; then
    _feishu_log "日期行不存在，在数据区顶部新建"
    feishu_prepend_date_row "$sheet_id" "$(date +%Y%m%d)"
    date_row=4
  fi

  # 组件列：第 1 行找名字，缺失则插入/追加新列
  resp="$(feishu_get_range_values "${sheet_id}!A1:ZZ2")"
  col_idx="$(python3 - "$component" "$resp" <<'PY'
import json, sys
target, data = sys.argv[1], json.loads(sys.argv[2] or "{}")
if data.get("code") != 0:
    raise SystemExit(f"read header failed: {data}")
values = data.get("data", {}).get("valueRange", {}).get("values", [])
header = values[0] if values else []
repo_row = values[1] if len(values) > 1 else []

def text(v):
    if v is None: return ""
    if isinstance(v, str): return v.strip()
    if isinstance(v, dict): return str(v.get("text") or v.get("link") or "").strip()
    if isinstance(v, list): return "".join(text(x) for x in v).strip()
    return str(v).strip()

last = 1
for row in (header, repo_row):
    for i, v in enumerate(row, start=1):
        if text(v): last = max(last, i)
for i, v in enumerate(header, start=1):
    if text(v) == target:
        print(i); raise SystemExit(0)
for i in range(2, max(len(header), len(repo_row)) + 2):
    h = text(header[i-1]) if i <= len(header) else ""
    r = text(repo_row[i-1]) if i <= len(repo_row) else ""
    if not h and not r:
        print(i); raise SystemExit(0)
print(last + 1)
PY
)"

  col="$(python3 - "$col_idx" <<'PY'
import sys
n = int(sys.argv[1]); s = ""
while n > 0:
    n, r = divmod(n - 1, 26)
    s = chr(ord("A") + r) + s
print(s)
PY
)"

  feishu_write_cell "$sheet_id" "${col}1" "$component"
  feishu_write_cell "$sheet_id" "${col}2" "$repository"
  feishu_write_cell "$sheet_id" "${col}${date_row}" "$tag"
  _feishu_log "已登记：${sheet}!${col}${date_row} = ${tag} (${component})"
}
