# Metabase Chat - AI 数据助手

基于 Django 的 Web 应用，通过自然语言与 Metabase 数据进行交互。

## 功能特性

- 自然语言查询 - 用日常语言与数据对话
- 实时流式响应 - 使用 SSE 即时获取结果
- 数据可视化 - 查询结果以格式化表格展示
- AI 驱动的 SQL 转换 - 支持 OpenAI 自然语言转 SQL
- 查询历史 - 记录所有查询和结果
- JWT 认证 - 安全的令牌认证
- 响应式界面 - Django Templates + HTMX + TailwindCSS

## 技术架构

```
浏览器 (Django + HTMX + TailwindCSS)
       ↓ HTTP/SSE
Django 应用
       ↓ HTTP
MCP 服务器 (端口 8000)
       ↓ HTTP
Metabase (端口 3000)
```

## 环境要求

- Python 3.10+
- Django 4.2
- Metabase 实例
- MCP 服务器 (端口 8000)
- (可选) OpenAI API Key

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下内容：

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# MCP 服务器
MCP_SERVER_URL=http://localhost:8000

# Metabase
METABASE_URL=http://localhost:3000
METABASE_API_KEY=your-metabase-api-key
METABASE_EMBED_KEY=your-metabase-embedding-key

# OpenAI (可选)
OPENAI_API_KEY=your-openai-api-key
```

### 3. 获取 Metabase API 凭证

1. API Key: 进入 `http://localhost:3000/admin/settings/api` 创建
2. Embedding Key: 进入 `http://localhost:3000/admin/settings/embedding-secret-key` 获取

### 4. 初始化数据库

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. 启动服务

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
bash start.sh
```

访问 http://localhost:8001

## 项目结构

```
metabase_chat/
├── api/              # API 视图和路由
├── chat/             # 聊天应用
│   ├── models.py     # 数据模型
│   ├── views.py      # 视图
│   ├── consumers.py  # WebSocket 消费者
│   └── services/     # 服务层
│       ├── mcp_client.py    # MCP 客户端
│       └── nl_to_sql.py     # 自然语言转 SQL
├── metabase_chat/    # Django 项目配置
│   ├── settings.py   # 设置
│   ├── urls.py       # 路由
│   └── asgi.py       # ASGI 配置
└── requirements.txt  # 依赖
```

## 配置说明

### OpenAI 配置 (可选)

如需使用 OpenAI 进行自然语言转 SQL，需要：
1. 在 .env 中设置 OPENAI_API_KEY
2. 在管理后台启用 OpenAI 配置

### Thinking 模式

支持启用 Claude 的 Thinking 模式以获得更详细的思考过程。

## 许可证

MIT License
