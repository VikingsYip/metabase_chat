"""
Chat views for the Django chat interface.
"""
import json
import asyncio
import logging
from datetime import datetime
from asgiref.sync import async_to_sync, sync_to_async
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Conversation, Message, QueryHistory
from .services.mcp_client import MCPClient
from .services.nl_to_sql import NLToSQLConverter

logger = logging.getLogger(__name__)


@login_required
@ensure_csrf_cookie
def chat_interface(request):
    """Main chat interface."""
    conversations = Conversation.objects.filter(
        user=request.user
    ).order_by('-updated_at')

    return render(request, 'chat/chat_interface.html', {
        'conversations': conversations
    })


@login_required
def conversation_detail(request, conversation_id):
    """Load specific conversation messages."""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )
    messages = conversation.messages.all().order_by('created_at')

    return render(request, 'chat/components/messages.html', {
        'messages': messages
    })


async def send_message_async(request, conversation_id=None):
    """
    Handle incoming chat messages with SSE streaming.

    This endpoint processes user messages, converts them to SQL if needed,
    executes queries against Metabase, and streams results back via Server-Sent Events.
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()

        if not user_message:
            return JsonResponse({'error': '消息不能为空'}, status=400)

        logger.info(f"Received message from user {request.user.id}: {user_message[:50]}...")

        # Get or create conversation (wrap sync ORM in sync_to_async)
        if conversation_id:
            get_conversation = sync_to_async(get_object_or_404)
            conversation = await get_conversation(
                Conversation,
                id=conversation_id,
                user=request.user
            )
        else:
            # Create new conversation with first 50 chars of message as title
            create_conversation = sync_to_async(Conversation.objects.create)
            conversation = await create_conversation(
                user=request.user,
                title=user_message[:50] + ('...' if len(user_message) > 50 else '')
            )
            logger.info(f"Created new conversation {conversation.id}")

        # Save user message (wrap sync ORM in sync_to_async)
        create_message = sync_to_async(Message.objects.create)
        user_msg = await create_message(
            conversation=conversation,
            role='user',
            content=user_message
        )

        # Process with AI and stream results
        async def event_stream():
            """Generator function for SSE events."""
            try:
                # Send user message confirmation
                yield f"event: message\ndata: {json.dumps({'role': 'user', 'content': user_message, 'message_id': user_msg.id})}\n\n"

                # Initialize services
                mcp_client = MCPClient()
                converter = NLToSQLConverter()

                # Analyze message intent
                message_lower = user_message.lower()

                # Check if this is a data-related query (supports both English and Chinese)
                is_data_query = any(keyword in message_lower for keyword in [
                    # English keywords
                    'show', 'list', 'get', 'count', 'find', 'search',
                    'how many', 'total', 'average', 'sum', 'max', 'min',
                    # Chinese keywords
                    '显示', '列出', '获取', '查询', '统计', '计数', '总计', '平均', '最大', '最小', '看'
                ])

                # Check if user wants to see databases or tables (supports both English and Chinese)
                has_database = 'database' in message_lower or '数据库' in message_lower
                has_all_tables = ('all' in message_lower or '所有' in message_lower or '全部' in message_lower) and \
                                 ('table' in message_lower or '表' in message_lower)
                has_list_tables = ('list' in message_lower or 'show' in message_lower or '列出' in message_lower or '显示' in message_lower) and \
                                  ('tables' in message_lower or 'table' in message_lower or '表' in message_lower)

                if has_database and (has_list_tables or 'all' in message_lower or '所有' in message_lower):
                    # List databases
                    yield f"event: thinking\ndata: {json.dumps({'status': '🔍 正在获取数据库列表...', 'progress': 20, 'details': '正在连接Metabase'})}\n\n"

                    try:
                        databases = await mcp_client.list_databases()

                        db_list = "\n".join([
                            f"- {db.get('name', 'Database ' + str(db.get('id', '')))} (ID: {db.get('id')})"
                            for db in databases
                        ])

                        response_text = f"可用数据库：\n\n{db_list}\n\n您可以查询以上任何一个数据库。"

                        create_assistant_msg = sync_to_async(Message.objects.create)
                        assistant_msg = await create_assistant_msg(
                            conversation=conversation,
                            role='assistant',
                            content=response_text
                        )

                        yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': response_text, 'message_id': assistant_msg.id, 'databases': databases})}\n\n"

                    except Exception as e:
                        logger.error(f"Error listing databases: {e}")
                        yield f"event: error\ndata: {json.dumps({'error': f'获取数据库列表失败：{str(e)}'})}\n\n"

                elif has_all_tables or has_list_tables:
                    # List all tables - need database ID
                    yield f"event: thinking\ndata: {json.dumps({'status': '🔍 正在获取表列表...', 'progress': 10, 'details': '正在连接数据库'})}\n\n"

                    # Force yield control to event loop so the event gets sent immediately
                    await asyncio.sleep(0)

                    try:
                        databases = await mcp_client.list_databases()

                        if databases:
                            db_id = databases[0].get('id')
                            db_name = databases[0].get('name')

                            yield f"event: thinking\ndata: {json.dumps({'status': '📋 正在读取表信息...', 'progress': 20, 'details': f'数据库: {db_name}'})}\n\n"
                            await asyncio.sleep(0)

                            # Get tables data - need to call the REST API to get raw table data
                            tables_result = await mcp_client.call_tool("list_tables", {"database_id": db_id})
                            tables_data = tables_result.get('data', tables_result)
                            if isinstance(tables_data, dict) and 'data' in tables_data:
                                tables_list = tables_data['data']
                            else:
                                tables_list = tables_data if isinstance(tables_data, list) else []

                            table_count = len(tables_list)
                            yield f"event: thinking\ndata: {json.dumps({'status': '📊 正在统计行数...', 'progress': 30, 'details': f'找到 {table_count} 个表，正在统计...'})}\n\n"

                            # Get row counts for each table
                            for idx, table in enumerate(tables_list, 1):
                                table_name = table.get('name')
                                if table_name:
                                    try:
                                        # Update progress for each table
                                        progress = 30 + int((idx / table_count) * 60)
                                        yield f"event: thinking\ndata: {json.dumps({'status': '📊 正在统计行数...', 'progress': progress, 'details': f'正在统计 {table_name} ({idx}/{table_count})'})}\n\n"

                                        # Execute COUNT query for each table
                                        count_query = f"SELECT COUNT(*) as row_count FROM `{table_name}`"
                                        count_result = await mcp_client.execute_query(db_id, count_query)

                                        # Extract row count from result
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

                            # Create text response
                            tables_info = "\n".join([
                                f"- {table.get('name', 'Unknown')} (ID: {table.get('id')}, 行数: {table.get('estimated_row_count', 'Unknown')})"
                                for table in tables_list
                            ])

                            response_text = f"{db_name} 数据库中的表：\n\n{tables_info}\n\n共找到 {len(tables_list)} 个表。"

                            create_assistant_msg = sync_to_async(Message.objects.create)
                            assistant_msg = await create_assistant_msg(
                                conversation=conversation,
                                role='assistant',
                                content=response_text
                            )

                            # Send both text message and tables data with row counts
                            yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': response_text, 'message_id': assistant_msg.id, 'tables': tables_list})}\n\n"
                        else:
                            yield f"event: error\ndata: {json.dumps({'error': '未找到数据库'})}\n\n"

                    except Exception as e:
                        logger.error(f"Error listing tables: {e}", exc_info=True)
                        yield f"event: error\ndata: {json.dumps({'error': f'获取表列表失败：{str(e)}'})}\n\n"

                elif is_data_query:
                    # This is a data query - convert to SQL and execute
                    yield f"event: thinking\ndata: {json.dumps({'status': '🔍 正在分析您的查询...', 'progress': 10})}\n\n"
                    await asyncio.sleep(0)

                    try:
                        # Get available databases
                        yield f"event: thinking\ndata: {json.dumps({'status': '📡 正在连接数据库...', 'progress': 15, 'details': '正在获取数据库列表'})}\n\n"
                        await asyncio.sleep(0)

                        databases = await mcp_client.list_databases()

                        if not databases:
                            yield f"event: error\ndata: {json.dumps({'error': '没有可用的数据库'})}\n\n"
                            return

                        # Use first database (in production, you'd ask user to specify)
                        db_id = databases[0].get('id')
                        db_name = databases[0].get('name', 'Unknown')

                        yield f"event: thinking\ndata: {json.dumps({'status': '📡 已连接到数据库', 'progress': 20, 'details': f'数据库: {db_name}'})}\n\n"
                        await asyncio.sleep(0)

                        # Get conversation history for context (wrap in sync_to_async)
                        get_history = sync_to_async(lambda: list(conversation.messages.filter(
                            role__in=['user', 'assistant']
                        ).order_by('created_at')[:10]))
                        history_messages = await get_history()

                        conversation_history = [
                            {'role': msg.role, 'content': msg.content}
                            for msg in history_messages
                        ]

                        # Tell user we're about to fetch schema (this may take 10-30s if not cached)
                        yield f"event: thinking\ndata: {json.dumps({'status': '📊 准备获取数据库结构...', 'progress': 22, 'details': '首次查询需要10-30秒，后续将使用缓存'})}\n\n"
                        await asyncio.sleep(0)

                        # Convert natural language to SQL with detailed progress
                        # The converter will yield progress updates directly
                        async def convert_with_progress():
                            # Step 1: Get database schema
                            yield f"event: thinking\ndata: {json.dumps({'status': '📊 正在获取数据库结构（9个表）...', 'progress': 25, 'details': '并行获取表字段信息，首次查询较慢'})}\n\n"
                            await asyncio.sleep(0)

                            # Actually fetch the schema (this is where the 24s delay happens if not cached)
                            result = await converter.convert(
                                user_message,
                                db_id,
                                conversation_history=conversation_history
                            )

                            # Step 2: Schema fetched, now calling AI
                            yield f"event: thinking\ndata: {json.dumps({'status': '🤖 正在调用DeepSeek R1模型生成SQL...', 'progress': 40, 'details': '这可能需要10-60秒，请耐心等待'})}\n\n"
                            await asyncio.sleep(0)

                            # Step 3: Process result
                            yield f"event: thinking\ndata: {json.dumps({'status': '✨ 正在优化生成的SQL...', 'progress': 90, 'details': '添加LIMIT和格式化'})}\n\n"
                            await asyncio.sleep(0)

                            # Yield final result
                            yield result

                        # Execute the conversion generator
                        async for item in convert_with_progress():
                            if isinstance(item, dict):
                                # This is the final result
                                result = item
                                break
                            else:
                                # It's a progress update (SSE event string), yield it to send to client
                                yield item
                                await asyncio.sleep(0)

                        sql_query = result.get('sql', '')

                        if not sql_query or sql_query.startswith('--'):
                            # Couldn't generate proper SQL
                            response_text = f"我无法根据您的请求生成正确的SQL查询。\n\n{sql_query}\n\n请更具体地说明表名以及您想要查看的内容。\n\n示例：\n-- '查看news表'\n-- '统计users表的数量'\n-- '查看orders表前10条记录'"

                            create_assistant_msg = sync_to_async(Message.objects.create)
                            assistant_msg = await create_assistant_msg(
                                conversation=conversation,
                                role='assistant',
                                content=response_text
                            )

                            yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': response_text, 'message_id': assistant_msg.id})}\n\n"
                            return

                        # Execute the query
                        yield f"event: thinking\ndata: {json.dumps({'status': '⚡ 正在执行SQL查询...', 'progress': 95, 'details': f'执行查询并获取结果'})}\n\n"
                        await asyncio.sleep(0)

                        query_result = await mcp_client.execute_query(db_id, sql_query)

                        # Format results - query_result already contains rows and cols at top level
                        rows = query_result.get('rows', [])
                        cols = query_result.get('cols', [])

                        result_count = len(rows) if rows else 0

                        response_text = f"以下是您的查询结果：\n\n```sql\n{sql_query}\n```\n\n"
                        response_text += f"找到 {result_count} 条记录。"

                        # Save assistant message
                        create_assistant_msg = sync_to_async(Message.objects.create)
                        assistant_msg = await create_assistant_msg(
                            conversation=conversation,
                            role='assistant',
                            content=response_text
                        )

                        # Save to query history
                        create_query_history = sync_to_async(QueryHistory.objects.create)
                        await create_query_history(
                            message=assistant_msg,
                            database_id=db_id,
                            sql_query=sql_query,
                            natural_language=user_message,
                            result_count=result_count
                        )

                        # Send response with query results
                        yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': response_text, 'message_id': assistant_msg.id, 'query_result': query_result})}\n\n"

                    except Exception as e:
                        logger.error(f"Error executing query: {e}", exc_info=True)
                        yield f"event: error\ndata: {json.dumps({'error': f'查询执行失败：{str(e)}'})}\n\n"

                else:
                    # General conversation - provide help
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

                    create_assistant_msg = sync_to_async(Message.objects.create)
                    assistant_msg = await create_assistant_msg(
                        conversation=conversation,
                        role='assistant',
                        content=response_text
                    )

                    yield f"event: message\ndata: {json.dumps({'role': 'assistant', 'content': response_text, 'message_id': assistant_msg.id})}\n\n"

                # Send done event
                yield "event: done\ndata: {}\n\n"

            except Exception as e:
                logger.error(f"Error in event_stream: {e}", exc_info=True)
                yield f"event: error\ndata: {json.dumps({'error': f'服务器错误：{str(e)}'})}\n\n"

        response =  StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )

        # Disable buffering for real-time streaming
        response['X-Accel-Buffering'] = 'no'  # For nginx
        response['Cache-Control'] = 'no-cache'
        response['Connection'] = 'keep-alive'

        return response

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse({'error': '请求体中的JSON格式无效'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in send_message: {e}", exc_info=True)
        return JsonResponse({'error': f'服务器错误：{str(e)}'}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def send_message(request, conversation_id=None):
    """
    Sync wrapper for async send_message handler.
    This wrapper allows @csrf_exempt to work properly.
    """
    # Check authentication in sync context
    if not request.user.is_authenticated:
        return JsonResponse({'error': '需要身份验证'}, status=401)

    return async_to_sync(send_message_async)(request, conversation_id)
