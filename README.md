# AI Toolbox

本地 AI 编码工具的用量监控 + 聊天记录导出。支持 [Reasonix](https://github.com/nichuanfang/reasonix) 和 [opencode](https://github.com/opencode-ai/opencode)。

## 功能

- **用量仪表盘** — 实时查看两个工具的 API Token 消耗、模型分布、每日趋势
- **聊天记录导出** — 一键将聊天记录导出为 Markdown 文件
- **悬浮详情** — 图表悬浮显示当日各模型具体用量

## 快速开始

### 前置条件

- Python 3.10+
- Reasonix 或 opencode（至少安装一个）

### 启动

```bash
# 克隆仓库
git clone https://github.com/anyuer678/ai-toolbox.git
cd ai-toolbox

# 双击启动（Windows）
启动工具箱.bat

# 或命令行启动
python scripts/server.py
```

浏览器会自动打开 http://localhost:9876

### 使用

| 按钮 | 功能 |
|------|------|
| **刷新用量** | 实时采集最新 API 用量数据 |
| **导出聊天记录** | 导出 Reasonix + opencode 的聊天记录为 Markdown |

## 数据安全

- **所有数据仅在本地采集和展示**，不会上传到任何服务器
- 聊天记录导出到本地 聊天记录/ 目录，已通过 .gitignore 排除
- 用量数据从本地数据库/文件直接读取，不经过外部 API

## 支持的工具

| 工具 | 数据源 | 说明 |
|------|--------|------|
| Reasonix | %APPDATA%/reasonix/stats/*.jsonl | Token 用量统计 |
| opencode | ~/.local/share/opencode/opencode.db | SQLite 数据库 |

## 自定义

编辑 scripts/server.py 顶部的配置：

```python
PORT = 9876                          # 服务端口
REASONIX_DIR = ...                   # Reasonix 数据目录
OPENCODE_DB = ...                    # opencode 数据库路径
EXPORT_DIR = BASE / "聊天记录"        # 导出目录
```

## 技术栈

- 后端：Python 标准库（http.server + sqlite3）
- 前端：纯 HTML/CSS/JS，无依赖
- UI 风格：参考 [kb-ui](https://github.com/anyuer678/kb-ui)（暖色调 + 衬线字体）

## License

MIT
