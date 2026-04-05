# smart-signal CLI

`smart-signal` 是 BNSmartMoneyMonitor 后端核心功能的 Go CLI 实现。它提供了以下能力：

- **查询** SQLite 数据库中的 Smart Signal 快照数据
- **启动** Web Dashboard 和 JSON API 服务
- **运行** 币安期货 WebSocket 价格流
- **管理** 币安 USDT 永续合约交易对列表

## 构建

### 前置条件

- Go 1.21+
- GCC（用于 SQLite CGO 编译）

### 编译

```bash
cd cli
go build -o smart-signal .
```

或使用 Makefile:

```bash
cd cli
make build
```

编译后的二进制文件 `smart-signal` 可在任何支持的平台上独立运行，无需 Python 环境。

### 运行测试

```bash
cd cli
make test
```

## 使用说明

### 总览

```
smart-signal <command> [flags]

Commands:
  query       查询 SQLite 中的 Smart Signal 快照数据
  serve       启动 Dashboard Web 服务和 JSON API
  stream      运行币安期货价格 WebSocket 流
  symbols     列出或刷新币安 USDT 永续合约交易对
  version     打印版本信息
```

---

### query - 查询快照数据

查询 SQLite 数据库中的 Smart Signal 数据，支持表格和 JSON 输出格式。

#### query latest

显示最新时间桶中所有交易对的汇总视图（按交易对透视）。

```bash
smart-signal query latest [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--db-path` | `data/smart_signal.sqlite3` | SQLite 数据库路径 |
| `--symbol` | | 筛选特定交易对 |
| `--limit` | `20` | 最大返回条数 |
| `--format` | `table` | 输出格式：`table` 或 `json` |

示例：

```bash
# 查看最新的前 20 个交易对
smart-signal query latest

# 查看 BTCUSDT 的最新数据（JSON 格式）
smart-signal query latest --symbol BTCUSDT --format json

# 指定数据库路径
smart-signal query latest --db-path /path/to/smart_signal.sqlite3 --limit 50
```

#### query snapshots

显示原始快照行数据。

```bash
smart-signal query snapshots [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--db-path` | `data/smart_signal.sqlite3` | SQLite 数据库路径 |
| `--ts-utc` | （最新时间桶） | 精确的 UTC 时间桶 |
| `--symbol` | | 筛选特定交易对 |
| `--cohort` | | 筛选 `trader` 或 `whale` |
| `--side` | | 筛选 `long` 或 `short` |
| `--limit` | `50` | 最大返回条数 |
| `--format` | `table` | 输出格式：`table` 或 `json` |

示例：

```bash
# 查看最新时间桶的 BTCUSDT 快照
smart-signal query snapshots --symbol BTCUSDT

# 查看 whale 的 long 数据
smart-signal query snapshots --cohort whale --side long --limit 20

# JSON 输出
smart-signal query snapshots --symbol ETHUSDT --format json
```

#### query history

显示单个交易对的历史数据。

```bash
smart-signal query history <SYMBOL> [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--db-path` | `data/smart_signal.sqlite3` | SQLite 数据库路径 |
| `--limit` | `40` | 最大返回条数 |
| `--format` | `table` | 输出格式：`table` 或 `json` |

示例：

```bash
# 查看 BTCUSDT 的历史数据
smart-signal query history BTCUSDT

# 查看更多历史记录
smart-signal query history ETHUSDT --limit 100 --format json
```

---

### serve - 启动 Web 服务

启动 HTTP 服务器，提供 Dashboard UI 和 JSON REST API。

```bash
smart-signal serve [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 绑定地址 |
| `--port` | `8765` | 绑定端口 |
| `--db-path` | `data/smart_signal.sqlite3` | SQLite 数据库路径 |
| `--price-snapshot-path` | `data/futures_price_snapshot.json` | 价格快照 JSON 路径 |
| `--frontend-dir` | `frontend` | 前端静态文件目录 |

示例：

```bash
# 默认配置启动
smart-signal serve

# 自定义端口和数据库
smart-signal serve --port 9090 --db-path /data/smart_signal.sqlite3

# 对外开放
smart-signal serve --host 0.0.0.0 --port 8080
```

#### API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | Dashboard HTML 页面 |
| `GET /api/meta` | 元数据（最新时间戳、交易对数量） |
| `GET /api/price?symbol=BTCUSDT` | 单个交易对的 WebSocket 最新价格 |
| `GET /api/latest?symbol=&sort_by=symbol&limit=100` | 最新快照（按交易对透视，含价格） |
| `GET /api/history?symbol=BTCUSDT&limit=80` | 单个交易对的原始历史行 |
| `GET /api/history-series?symbol=BTCUSDT&limit=60` | 单个交易对的时序数据 |
| `GET /api/snapshots?ts_utc=&symbol=&cohort=&side=&limit=100` | 原始快照行 |

---

### stream - 运行价格流

连接币安期货 WebSocket 接收全市场行情数据，定期写入 JSON 快照文件。

```bash
smart-signal stream [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--snapshot-path` | `data/futures_price_snapshot.json` | 价格快照输出路径 |
| `--flush-seconds` | `2.0` | 快照写入间隔（秒） |

示例：

```bash
# 默认配置运行
smart-signal stream

# 自定义输出路径
smart-signal stream --snapshot-path /data/prices.json --flush-seconds 5
```

该命令会：
- 连接 `wss://fstream.binance.com/ws/!ticker@arr`
- 接收所有期货交易对的实时行情
- 每 N 秒将最新价格写入 JSON 文件
- 23 小时后自动重连（避免会话超时）
- 断开后自动重试（指数退避）

---

### symbols - 管理交易对列表

列出或刷新币安 USDT 永续合约交易对。

```bash
smart-signal symbols [flags]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--list-path` | `config/binance_usdt_perpetual_symbols.txt` | 交易对列表文件路径 |
| `--refresh` | `false` | 强制从币安 API 刷新 |
| `--stage1-only` | `false` | 仅包含 BTCUSDT 和 ETHUSDT |
| `--allowlist` | | 逗号分隔的交易对白名单 |
| `--format` | `text` | 输出格式：`text` 或 `json` |

示例：

```bash
# 从本地缓存列出所有交易对
smart-signal symbols

# 从币安 API 刷新
smart-signal symbols --refresh

# 仅显示特定交易对
smart-signal symbols --allowlist BTCUSDT,ETHUSDT,SOLUSDT

# JSON 格式输出
smart-signal symbols --format json
```

---

## 架构说明

### 与 Python 后端的对应关系

| Go 包/命令 | Python 模块 | 功能 |
|------------|-------------|------|
| `internal/db` | `smart_signal.db` | SQLite 持久化、查询、透视、指标计算 |
| `internal/parser` | `smart_signal.parser` | 数字解析、信号载荷解析 |
| `internal/symbols` | `smart_signal.binance_symbols` | 交易对发现与缓存 |
| `internal/pricestream` | `smart_signal.price_stream` | WebSocket 价格流 |
| `internal/web` | `smart_signal.web` | Dashboard 和 JSON API 服务 |
| `cmd/query.go` | `smart_signal.query` | 查询 CLI 命令 |
| `main.go` | 各模块 `__main__` | CLI 入口 |

### 未移植的模块

| Python 模块 | 原因 |
|-------------|------|
| `collector.py` | 依赖 Playwright 浏览器自动化，Go 中无直接等价物。数据采集仍使用 Python 完成。 |
| `scheduler.py` | 编排 collector，依赖 Playwright。可通过 cron 或 systemd timer 替代。 |
| `bootstrap_login.py` | Playwright 浏览器登录会话创建，需人工交互。 |

### 数据兼容性

Go CLI 使用与 Python 后端完全相同的 SQLite 数据库 schema 和 JSON 价格快照格式，因此：

- Go CLI 可以直接读取 Python collector 写入的数据库
- Go `serve` 命令可以替代 Python `web.py` 提供 API 服务
- Go `stream` 命令可以替代 Python `price_stream.py` 运行价格流
- Go `query` 命令可以替代 Python `query.py` 查询数据

### 目录结构

```
cli/
├── main.go                         # CLI 入口，命令路由
├── Makefile                        # 构建脚本
├── go.mod                          # Go 模块定义
├── go.sum                          # 依赖校验
├── cmd/
│   └── query.go                    # 查询命令实现（表格/JSON 输出）
└── internal/
    ├── db/
    │   └── db.go                   # SQLite 持久化、查询、透视、指标计算
    ├── parser/
    │   ├── parser.go               # 数字解析、信号载荷解析
    │   └── parser_test.go          # 解析器测试
    ├── pricestream/
    │   └── stream.go               # WebSocket 价格流客户端
    ├── symbols/
    │   └── symbols.go              # 交易对发现与缓存管理
    └── web/
        └── server.go               # HTTP Dashboard 和 JSON API 服务
```

## 典型使用场景

### 1. 仅查询（使用 Python collector 采集的数据）

```bash
# Python 采集数据
TMPDIR=$PWD/.tmp PYTHONPATH=src python -m smart_signal.collector --headless

# Go CLI 查询
smart-signal query latest --limit 50
smart-signal query history BTCUSDT --format json
```

### 2. 替代 Python Web 服务

```bash
# 使用 Go CLI 启动 Dashboard
smart-signal serve --port 8765

# 在另一个终端运行价格流
smart-signal stream
```

### 3. 在 CI/CD 或脚本中使用

```bash
# 获取最新数据（JSON 格式，便于管道处理）
smart-signal query latest --format json | jq '.[] | select(.symbol == "BTCUSDT")'

# 获取所有交易对列表
smart-signal symbols --format json | jq '.symbols[]'
```
