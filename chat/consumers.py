"""
WebSocket consumer for real-time chat.
"""
import json
import logging
import asyncio
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import Conversation, Message, QueryHistory
from .services.mcp_client import MCPClient
from .services.nl_to_sql import NLToSQLConverter

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for chat interface."""

    async def connect(self):
        """Handle WebSocket connection."""
        if self.scope["user"].is_anonymous:
            await self.close()
            return

        self.user = self.scope["user"]
        self.conversation_id = None

        # Accept connection
        await self.accept()

        logger.info(f"WebSocket connected for user {self.user.id}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        logger.info(f"WebSocket disconnected for user {self.user.id}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message = data.get('message', '').strip()
            action = data.get('action', 'send_message')
            conversation_id = data.get('conversation_id')

            if not message:
                await self.send_error('消息不能为空')
                return

            logger.info(f"Received WebSocket message from user {self.user.id}: {message[:50]}...")

            if action == 'send_message':
                await self.handle_send_message(message, conversation_id)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await self.send_error('请求体中的JSON格式无效')
        except Exception as e:
            logger.error(f"Error in receive: {e}", exc_info=True)
            await self.send_error(f'服务器错误：{str(e)}')

    async def handle_send_message(self, user_message, conversation_id=None):
        """Process and send message through WebSocket."""
        try:
            # Send user message confirmation
            await self.ws_send_message('user_message', {
                'content': user_message
            })

            # Get or create conversation
            if conversation_id:
                conversation = await database_sync_to_async(Conversation.objects.get)(
                    id=conversation_id,
                    user=self.user
                )
            else:
                # Create new conversation
                conversation = await database_sync_to_async(Conversation.objects.create)(
                    user=self.user,
                    title=user_message[:50] + ('...' if len(user_message) > 50 else '')
                )
                logger.info(f"Created new conversation {conversation.id}")

            # Save user message to database
            user_msg = await database_sync_to_async(Message.objects.create)(
                conversation=conversation,
                role='user',
                content=user_message
            )

            # Send user message with ID
            await self.ws_send_message('message', {
                'role': 'user',
                'content': user_message,
                'message_id': user_msg.id
            })

            # Process message
            await self.process_query(conversation, user_message)

        except Exception as e:
            logger.error(f"Error in handle_send_message: {e}", exc_info=True)
            await self.send_error(f'处理消息时出错：{str(e)}')

    async def process_query(self, conversation, user_message):
        """Process natural language query and send real-time updates."""
        try:
            mcp_client = MCPClient()
            converter = NLToSQLConverter()

            # Get enable_thinking config from converter
            enable_thinking = True
            try:
                from .models import OpenAIConfig
                config = await database_sync_to_async(lambda: OpenAIConfig.objects.filter(is_active=True).first())()
                if config:
                    enable_thinking = config.enable_thinking
            except Exception as e:
                logger.warning(f"Could not get enable_thinking config: {e}")

            # Analyze message intent
            message_lower = user_message.lower()

            # Check if this is a data-related query
            is_data_query = any(keyword in message_lower for keyword in [
                'show', 'list', 'get', 'count', 'find', 'search',
                'how many', 'total', 'average', 'sum', 'max', 'min',
                '显示', '列出', '获取', '查询', '统计', '计数', '总计', '平均', '最大', '最小', '看'
            ])

            # Check for database/table list requests
            has_database = 'database' in message_lower or '数据库' in message_lower
            has_all_tables = ('all' in message_lower or '所有' in message_lower or '全部' in message_lower) and \
                             ('table' in message_lower or '表' in message_lower)
            has_list_tables = ('list' in message_lower or 'show' in message_lower or '列出' in message_lower or '显示' in message_lower) and \
                              ('tables' in message_lower or 'table' in message_lower or '表' in message_lower)

            # Handle list databases
            if has_database and (has_list_tables or 'all' in message_lower or '所有' in message_lower):
                await self.send_thinking('正在获取数据库列表...', enable_thinking)
                databases = await mcp_client.list_databases()

                db_list = "\n".join([
                    f"- {db.get('name', 'Database ' + str(db.get('id', '')))} (ID: {db.get('id')})"
                    for db in databases
                ])

                response_text = f"可用数据库：\n\n{db_list}\n\n您可以查询以上任何一个数据库。"

                # Save and send assistant message
                await self.save_and_send_assistant_message(conversation, response_text, databases=databases)
                return

            # Handle list tables
            if has_all_tables or has_list_tables:
                await self.send_thinking('正在获取表列表...', enable_thinking)
                databases = await mcp_client.list_databases()

                if databases:
                    db_id = databases[0].get('id')
                    db_name = databases[0].get('name')

                    await self.send_thinking(f'正在读取数据库：{db_name}', enable_thinking)

                    tables_result = await mcp_client.call_tool("list_tables", {"database_id": db_id})
                    tables_data = tables_result.get('data', tables_result)
                    if isinstance(tables_data, dict) and 'data' in tables_data:
                        tables_list = tables_data['data']
                    else:
                        tables_list = tables_data if isinstance(tables_data, list) else []

                    # Get row counts
                    await self.send_thinking('正在统计表行数...', enable_thinking)
                    for idx, table in enumerate(tables_list, 1):
                        table_name = table.get('name')
                        if table_name:
                            await self.send_thinking(f'正在统计 {table_name} ({idx}/{len(tables_list)})...', enable_thinking)
                            try:
                                count_query = f"SELECT COUNT(*) as row_count FROM `{table_name}`"
                                count_result = await mcp_client.execute_query(db_id, count_query)

                                if count_result and 'rows' in count_result:
                                    rows = count_result['rows']
                                    if rows and len(rows) > 0 and len(rows[0]) > 0:
                                        table['estimated_row_count'] = rows[0][0]
                                    else:
                                        table['estimated_row_count'] = 0
                                else:
                                    table['estimated_row_count'] = 0
                            except Exception as e:
                                logger.warning(f"Could not count rows for table {table_name}: {e}")
                                table['estimated_row_count'] = 0

                    # Send response
                    tables_info = "\n".join([
                        f"- {table.get('name', 'Unknown')} (ID: {table.get('id')}, 行数: {table.get('estimated_row_count', 'Unknown')})"
                        for table in tables_list
                    ])

                    response_text = f"{db_name} 数据库中的表：\n\n{tables_info}\n\n共找到 {len(tables_list)} 个表。"

                    await self.save_and_send_assistant_message(conversation, response_text, tables=tables_list)
                return

            # Handle data queries
            if is_data_query:
                await self.send_thinking('正在分析您的查询...', enable_thinking)
                await self.send_thinking('正在连接数据库...', enable_thinking)

                databases = await mcp_client.list_databases()

                if not databases:
                    await self.send_error('没有可用的数据库')
                    return

                db_id = databases[0].get('id')
                db_name = databases[0].get('name', 'Unknown')

                await self.send_thinking(f'已连接到数据库：{db_name}', enable_thinking)
                await self.send_thinking('准备获取数据库结构（首次查询较慢）...', enable_thinking)

                # Get conversation history
                get_history = database_sync_to_async(lambda: list(conversation.messages.filter(
                    role__in=['user', 'assistant']
                ).order_by('created_at')[:10]))
                history_messages = await get_history()

                conversation_history = [
                    {'role': msg.role, 'content': msg.content}
                    for msg in history_messages
                ]

                await self.send_thinking('正在获取数据库结构（使用缓存）...', enable_thinking)

                # Convert to SQL
                result = await converter.convert(
                    user_message,
                    db_id,
                    conversation_history=conversation_history
                )

                await self.send_thinking('正在调用DeepSeek R1模型生成SQL...', enable_thinking)

                sql_query = result.get('sql', '')

                if not sql_query or sql_query.startswith('--'):
                    response_text = f"我无法根据您的请求生成正确的SQL查询。\n\n{sql_query}\n\n请更具体地说明表名以及您想要查看的内容。"
                    await self.save_and_send_assistant_message(conversation, response_text)
                    return

                await self.send_thinking('正在优化生成的SQL...', enable_thinking)
                await self.send_thinking('正在执行SQL查询...', enable_thinking)

                # Execute query
                query_result = await mcp_client.execute_query(db_id, sql_query)

                # Format results
                rows = query_result.get('rows', [])
                cols = query_result.get('cols', [])
                result_count = len(rows) if rows else 0

                response_text = f"以下是您的查询结果：\n\n```sql\n{sql_query}\n```\n\n找到 {result_count} 条记录。"

                # Save to history
                assistant_msg = await database_sync_to_async(Message.objects.create)(
                    conversation=conversation,
                    role='assistant',
                    content=response_text
                )

                await database_sync_to_async(QueryHistory.objects.create)(
                    message=assistant_msg,
                    database_id=db_id,
                    sql_query=sql_query,
                    natural_language=user_message,
                    result_count=result_count
                )

                # Send response
                await self.ws_send_message('message', {
                    'role': 'assistant',
                    'content': response_text,
                    'message_id': assistant_msg.id,
                    'query_result': query_result
                })
                return

            # General help message
            response_text = """您好！我是您的Metabase AI助手。我可以帮助您：

• **探索数据库** - 询问"列出数据库"或"显示表"
• **查询数据** - 提出问题，如"显示所有用户"或"统计订单数量"
• **生成报告** - 我可以帮助您从数据中创建可视化内容

试着问我：
- "显示所有数据库"
- "列出所有表"
- "统计users表的用户数量"
- "显示orders表最近的订单"

您想要探索什么？"""

            await self.save_and_send_assistant_message(conversation, response_text)

        except Exception as e:
            logger.error(f"Error in process_query: {e}", exc_info=True)
            await self.send_error(f'查询执行失败：{str(e)}')

    async def save_and_send_assistant_message(self, conversation, content, **extra_data):
        """Save assistant message to database and send via WebSocket."""
        assistant_msg = await database_sync_to_async(Message.objects.create)(
            conversation=conversation,
            role='assistant',
            content=content
        )

        message_data = {
            'role': 'assistant',
            'content': content,
            'message_id': assistant_msg.id
        }
        message_data.update(extra_data)

        await self.ws_send_message('message', message_data)

    async def ws_send_message(self, message_type, data):
        """Send message through WebSocket."""
        await self.send(text_data=json.dumps({
            'type': message_type,
            'data': data
        }))

    async def send_thinking(self, status, enable_thinking=None):
        """Send thinking status if enabled in config."""
        # If enable_thinking is explicitly False, skip sending
        if enable_thinking is False:
            return

        # Check if thinking is enabled in config
        if enable_thinking is None:
            try:
                from .models import OpenAIConfig
                config = await database_sync_to_async(lambda: OpenAIConfig.objects.filter(is_active=True).first())()
                if config and not config.enable_thinking:
                    return
            except Exception:
                pass  # If config check fails, default to sending

        await self.send(text_data=json.dumps({
            'type': 'thinking',
            'data': {
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
        }))

    async def send_error(self, error_message):
        """Send error message."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'data': {
                'error': error_message
            }
        }))

    async def send_progress(self, status, details=None, progress=None):
        """Send progress update."""
        data = {'status': status}
        if details:
            data['details'] = details
        if progress is not None:
            data['progress'] = progress

        await self.send(text_data=json.dumps({
            'type': 'progress',
            'data': data
        }))
