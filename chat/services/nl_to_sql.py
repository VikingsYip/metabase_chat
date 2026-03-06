"""
自然语言到SQL转换服务。

此服务使用LLM集成将自然语言查询转换为SQL。
"""
import os
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


class NLToSQLConverter:
    """使用带有模式上下文的LLM将自然语言转换为SQL。"""

    # Class-level cache for schema information
    _schema_cache = {}
    _cache_timestamps = {}
    _cache_ttl = timedelta(minutes=30)  # Cache expires after 30 minutes

    def __init__(self):
        self.mcp_client = MCPClient()
        self.openai_config = None
        self.has_openai = False
        self.client = None

        # Load config from database
        self._load_config()

    @classmethod
    def clear_schema_cache(cls, database_id: Optional[int] = None):
        """
        Clear schema cache.

        Args:
            database_id: If provided, only clear cache for this database.
                        Otherwise, clear all cache.
        """
        if database_id is not None:
            cls._schema_cache.pop(database_id, None)
            cls._cache_timestamps.pop(database_id, None)
            logger.info(f"Cleared schema cache for database {database_id}")
        else:
            cls._schema_cache.clear()
            cls._cache_timestamps.clear()
            logger.info("Cleared all schema cache")

    @classmethod
    def is_cache_valid(cls, database_id: int) -> bool:
        """Check if cached schema is still valid."""
        if database_id not in cls._cache_timestamps:
            return False

        cache_age = datetime.now() - cls._cache_timestamps[database_id]
        return cache_age < cls._cache_ttl

    async def _get_table_fields_async(self, table_id: int, table_name: str) -> str:
        """
        Get fields for a single table asynchronously.

        Returns formatted table schema string.
        """
        try:
            fields_result = await self.mcp_client.call_tool("get_table_fields", {"table_id": table_id})
            fields_data = fields_result.get('data', fields_result)

            # Extract fields list
            if isinstance(fields_data, dict):
                fields_list = fields_data.get('fields', [])
            elif isinstance(fields_data, list):
                fields_list = fields_data
            else:
                fields_list = []

            # Build field descriptions
            field_descs = []
            for field in fields_list:
                field_name = field.get('name')
                field_type = field.get('base_type', 'unknown')
                field_descs.append(f"  - {field_name} ({field_type})")

            return f"Table: {table_name}\n" + "\n".join(field_descs)

        except Exception as e:
            logger.warning(f"Could not get fields for table {table_name}: {e}")
            return f"Table: {table_name}\n  (Fields unavailable)"

    def _load_config(self):
        """Load OpenAI configuration from database."""
        try:
            # Check if OpenAI package is available first
            try:
                from openai import OpenAI
            except ImportError:
                logger.warning("OpenAI package not installed. NL-to-SQL will use basic pattern matching.")
                return

            # Try environment variable first (synchronous, safe)
            self.openai_api_key = os.getenv('OPENAI_API_KEY')
            if self.openai_api_key:
                self.openai_config = {
                    'api_key': self.openai_api_key,
                    'base_url': os.getenv('OPENAI_BASE_URL'),
                    'model': os.getenv('OPENAI_MODEL', 'gpt-4'),
                    'temperature': float(os.getenv('OPENAI_TEMPERATURE', 0.1)),
                    'max_tokens': int(os.getenv('OPENAI_MAX_TOKENS', 1000)),
                    'enable_thinking': os.getenv('OPENAI_ENABLE_THINKING', 'true').lower() == 'true'
                }
                self.has_openai = True
                self._init_client()
                logger.info("Using OpenAI config from environment variable")
                return

            # Try to load from database (deferred - will be called in async context)
            logger.info("No OpenAI config in environment. Will try loading from database during first async call.")

        except Exception as e:
            logger.error(f"Error loading OpenAI config: {e}")

    async def _ensure_config_loaded(self):
        """Ensure OpenAI config is loaded from database (async-safe)."""
        if self.has_openai:
            return  # Already loaded from environment

        try:
            from openai import OpenAI
            from ..models import OpenAIConfig
            from asgiref.sync import sync_to_async

            # Try to get active config from database (async-safe)
            get_config = sync_to_async(lambda: OpenAIConfig.objects.filter(is_active=True).first())
            config = await get_config()

            if config and config.api_key:
                self.openai_config = {
                    'api_key': config.api_key,
                    'base_url': config.base_url,
                    'model': config.model,
                    'temperature': config.temperature,
                    'max_tokens': config.max_tokens,
                    'enable_thinking': config.enable_thinking
                }
                self.has_openai = True
                self._init_client()
                logger.info(f"Loaded OpenAI config from database: {config.name}")
            else:
                logger.info("No active OpenAI config found in database. NL-to-SQL will use basic pattern matching.")

        except Exception as e:
            logger.error(f"Error loading OpenAI config from database: {e}")
            logger.info("NL-to-SQL will use basic pattern matching.")

    def _init_client(self):
        """Initialize OpenAI client with current config."""
        if not self.has_openai or not self.openai_config:
            return

        try:
            from openai import OpenAI

            client_kwargs = {'api_key': self.openai_config['api_key']}
            if self.openai_config['base_url']:
                client_kwargs['base_url'] = self.openai_config['base_url']

            self.client = OpenAI(**client_kwargs)
            logger.info("OpenAI client initialized")
        except ImportError:
            logger.warning("OpenAI package not installed. NL-to-SQL will use basic pattern matching.")
            self.has_openai = False
            self.client = None

    async def get_active_config(self):
        """Get active OpenAI config from database (async wrapper)."""
        from ..models import OpenAIConfig
        get_config = sync_to_async(lambda: OpenAIConfig.objects.filter(is_active=True).first())
        return await get_config()

    async def get_schema_context(self, database_id: int, table_ids: list = None) -> str:
        """
        收集模式信息作为上下文。

        使用缓存和并行获取来优化性能。

        参数:
            database_id: 数据库ID
            table_ids: 可选的特定表ID列表以获取模式信息

        返回:
            包含模式信息的字符串
        """
        # Check cache first
        if self.is_cache_valid(database_id):
            logger.info(f"Using cached schema for database {database_id}")
            return self._schema_cache[database_id]

        schema_info = []

        try:
            logger.info(f"Fetching schema for database {database_id}...")

            # Get tables list
            tables_result = await self.mcp_client.call_tool("list_tables", {"database_id": database_id})
            tables_data = tables_result.get('data', tables_result)
            if isinstance(tables_data, dict) and 'data' in tables_data:
                tables_list = tables_data['data']
            else:
                tables_list = tables_data if isinstance(tables_data, list) else []

            schema_info.append(f"Database ID: {database_id}")

            # Filter tables if table_ids is provided
            if table_ids:
                tables_list = [t for t in tables_list if t.get('id') in table_ids]

            # Build detailed schema information for each table IN PARALLEL
            # This is much faster than sequential fetching
            logger.info(f"Fetching fields for {len(tables_list)} tables in parallel...")

            # Create tasks for parallel execution
            tasks = [
                self._get_table_fields_async(table.get('id'), table.get('name'))
                for table in tables_list
            ]

            # Execute all tasks in parallel and wait for completion
            table_schemas = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            processed_schemas = []
            for i, schema in enumerate(table_schemas):
                if isinstance(schema, Exception):
                    table_name = tables_list[i].get('name', 'Unknown')
                    logger.warning(f"Error fetching schema for table {table_name}: {schema}")
                    processed_schemas.append(f"Table: {table_name}\n  (Fields unavailable)")
                else:
                    processed_schemas.append(schema)

            schema_info.append("\n\n".join(processed_schemas))
            result = "\n\n".join(schema_info)

            # Cache the result
            self._schema_cache[database_id] = result
            self._cache_timestamps[database_id] = datetime.now()
            logger.info(f"Schema cached for database {database_id} (TTL: {self._cache_ttl})")

            return result

        except Exception as e:
            logger.error(f"Error getting schema context: {e}")
            return f"Database ID: {database_id}\n(Schema information temporarily unavailable)"

    async def convert(
        self,
        natural_query: str,
        database_id: int,
        table_ids: Optional[list] = None,
        conversation_history: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        将自然语言转换为SQL查询。

        参数:
            natural_query: 用户的自然语言查询
            database_id: 要查询的数据库ID
            table_ids: 要关注的可选表ID列表
            conversation_history: 上下文的可选对话历史

        返回:
            包含生成的SQL查询的字典，'sql'键包含SQL语句
        """
        logger.info(f"Converting natural language query: {natural_query[:50]}...")

        # Ensure config is loaded (async-safe)
        await self._ensure_config_loaded()

        # Try OpenAI if available
        if self.has_openai and self.client:
            return await self._convert_with_openai(
                natural_query,
                database_id,
                table_ids,
                conversation_history
            )
        else:
            # Fall back to basic pattern matching
            return self._convert_with_patterns(natural_query, database_id)

    async def _convert_with_openai(
        self,
        natural_query: str,
        database_id: int,
        table_ids: Optional[list],
        conversation_history: Optional[list]
    ) -> Dict[str, Any]:
        """使用OpenAI API进行转换。"""

        try:
            # Step 1: Get schema context
            schema_context = await self.get_schema_context(database_id, table_ids)

            # Build prompt with conversation history
            messages = [
                {
                    "role": "system",
                    "content": f"""You are a SQL expert. Convert natural language queries to SQL.

Available Database Schema:
{schema_context}

Rules:
1. Use proper SQL syntax compatible with the database (MySQL)
2. Use appropriate JOINs when needed
3. Return ONLY the executable SQL query, NO comments or explanations
4. If the query is unclear, ask for clarification
5. Use SELECT * for simple queries unless specific columns are mentioned
6. Always include a LIMIT clause to prevent runaway queries (default to 100 rows)
7. For counting, use COUNT(*) with a clear alias
8. Use inline comments (-- comment) AFTER SQL statements if needed, never BEFORE

Examples:
- "Show me all users" -> SELECT * FROM users LIMIT 100;
- "Count all orders" -> SELECT COUNT(*) as order_count FROM orders;
- "List recent orders" -> SELECT * FROM orders ORDER BY created_at DESC LIMIT 50;
"""
                }
            ]

            # Add conversation history for context
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages for context
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })

            # Add current query
            messages.append({
                "role": "user",
                "content": natural_query
            })

            # Call OpenAI
            logger.debug("Sending request to OpenAI API")
            response = self.client.chat.completions.create(
                model=self.openai_config.get('model', 'gpt-4'),
                messages=messages,
                temperature=self.openai_config.get('temperature', 0.1),
                max_tokens=self.openai_config.get('max_tokens', 1000)
            )

            sql_query = response.choices[0].message.content.strip()

            # Extract SQL if it's wrapped in markdown code blocks
            if "```sql" in sql_query:
                sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
            elif "```" in sql_query:
                sql_query = sql_query.split("```")[1].split("```")[0].strip()

            # Remove leading comment lines (lines starting with --)
            lines = sql_query.split('\n')
            while lines and lines[0].strip().startswith('--'):
                lines.pop(0)
            sql_query = '\n'.join(lines).strip()

            # Remove any existing LIMIT and add our own
            if "LIMIT" not in sql_query.upper():
                sql_query += " LIMIT 100"

            logger.info(f"OpenAI generated SQL: {sql_query[:100]}...")

            return {
                "sql": sql_query,
                "confidence": "high",
                "method": "openai",
                "enable_thinking": self.openai_config.get('enable_thinking', True)
            }

        except Exception as e:
            logger.error(f"Error using OpenAI for NL-to-SQL: {e}")
            # Fall back to pattern matching
            return self._convert_with_patterns(natural_query, database_id)

    def _convert_with_patterns(self, natural_query: str, database_id: int) -> Dict[str, Any]:
        """使用基本模式匹配进行转换（备用方法）。"""

        logger.info("Using pattern matching for NL-to-SQL conversion")

        # Common field name mappings (Chinese to English)
        field_mappings = {
            '分类': 'category',
            '类别': 'category',
            '来源': 'sourceName',
            '作者': 'author',
            '标题': 'title',
            '内容': 'content',
            '链接': 'link',
            '时间': 'publishedAt',
            '日期': 'publishedAt',
            '创建时间': 'createdAt',
            '更新时间': 'updatedAt',
        }

        query_lower = natural_query.lower()

        # Replace Chinese field names with English
        for chinese, english in field_mappings.items():
            if chinese in query_lower:
                query_lower = query_lower.replace(chinese, english)

        # Try to extract table name from the query
        # Common patterns: "show X table", "看X表", "get X", "list X"
        table_name = None
        group_by_field = None
        limit = 100

        # Common field name mappings (Chinese to English) - same as above
        field_mappings = {
            '分类': 'category',
            '类别': 'category',
            '来源': 'sourceName',
            '作者': 'author',
            '标题': 'title',
            '内容': 'content',
            '链接': 'link',
            '时间': 'publishedAt',
            '日期': 'publishedAt',
            '创建时间': 'createdAt',
            '更新时间': 'updatedAt',
        }

        # First, extract GROUP BY fields if present
        import re
        group_by_fields = []

        # Chinese patterns: "按category和月份" or "按category分组" or "按category统计"
        # Match patterns like "按A和B" or "按A和B统计" - use non-greedy matching
        group_match = re.search(r'按(\S+?)\s*(?:和|与)\s*(\S+?)(?:\s*分组|\s*统计)?', query_lower)
        if group_match:
            group_by_fields.append(group_match.group(1))
            # Check if second field is a time field
            second_field = group_match.group(2)
            if second_field in ['月', '年月', '时间', '月份', '年', '期']:
                group_by_fields.append('month')
            else:
                group_by_fields.append(second_field)
        else:
            # Single field pattern: "按category分组" or "按category统计"
            group_match = re.search(r'按(\S+?)\s*(?:分组|统计)', query_lower)
            if group_match:
                group_by_fields.append(group_match.group(1))

        # Check for time-based grouping: "按月", "按年", "时间", "月份", etc. (if not already added)
        if any(word in query_lower for word in ['时间', '月份', '年月', '按月', '按年']) and 'month' not in group_by_fields:
            group_by_fields.append('month')

        elif 'group by' in query_lower:
            group_match = re.search(r'group by\s+(\w+)', query_lower)
            if group_match:
                group_by_fields.append(group_match.group(1))

        # Chinese pattern: "看表名表" or "看表名" or "统计表名"
        if '看' in query_lower or '显示' in query_lower or '查询' in query_lower or '统计' in query_lower:
            # Remove common keywords to find table name
            # Remove "看", "显示", "查询", "统计", "表", "所有", "全部", "前", "条", "按", "分组", "的", "中", "和", "与", "时间", "数量"
            # Also remove time-related words
            cleaned = re.sub(r'[看显示查询统计表所有全部前条按分组数量降序排列的中的和与增加新增时间月份年月]', ' ', query_lower)
            # Extract first word as potential table name (skip if it's in group_by_fields)
            words = cleaned.strip().split()
            for word in words:
                if word and word not in group_by_fields and len(word) > 2:  # Skip short words
                    table_name = word.strip()
                    break

            # Check for limit pattern like "前10条" or "前10"
            limit_match = re.search(r'前\s*(\d+)', query_lower)
            if limit_match:
                limit = int(limit_match.group(1))

        # English pattern: "show X table", "list X", "get X"
        if not table_name:
            import re
            # Try to extract table name after "show", "list", "get", "all"
            match = re.search(r'(?:show|list|get|from)\s+(\w+)', query_lower)
            if match:
                table_name = match.group(1)

            # Check for limit pattern like "first 10", "top 10", "limit 10"
            limit_match = re.search(r'(?:first|top|limit)\s+(\d+)', query_lower)
            if limit_match:
                limit = int(limit_match.group(1))

        # Build SQL based on extracted table name
        if table_name and len(table_name) > 1:
            # Check if user specified particular fields
            specified_fields = []

            # Pattern: "看news表的标题和时间" or "看news：标题和时间"
            # Check if there are field names mentioned after table name in original query
            original_query = natural_query.lower()
            table_name_patterns = [
                rf'{re.escape(table_name)}\s*[表:：]\s*([\w\u4e00-\u9fff\s]+?)(?:\s+限制|\s+limit|\s+前|$)',
                rf'看\s+{re.escape(table_name)}\s*[表:：的]\s*([\w\u4e00-\u9fff\s]+?)(?:\s+限制|\s+limit|\s+前|$)',
            ]

            for pattern in table_name_patterns:
                table_field_pattern = re.search(pattern, original_query)
                if table_field_pattern:
                    field_text = table_field_pattern.group(1).strip()
                    # Remove leading "的" if present
                    field_text = re.sub(r'^的', '', field_text)
                    # Extract field names from the text
                    # Common separators: 和, 与, ,, 、
                    possible_fields = re.split(r'[和与,,、、\s]+', field_text)
                    for field in possible_fields:
                        field = field.strip()
                        if field and field not in ['限制', 'limit', '前', '条', '所有', '全部', '记录', '数据', '表', '显示', '查看']:
                            # Map Chinese field names to English
                            for chinese, english in field_mappings.items():
                                if chinese == field:
                                    field = english
                                    break
                            if field not in specified_fields and len(field) > 1:
                                specified_fields.append(field)
                    break

            # Check if it's a count/aggregation query
            if any(word in query_lower for word in ['count', 'how many', '计数', '多少', '统计', '数量', '汇总']):
                if group_by_fields:
                    # GROUP BY with COUNT
                    order = 'DESC' if '降序' in query_lower or 'desc' in query_lower else 'ASC'

                    # Build SELECT and GROUP BY clauses
                    select_parts = []
                    group_by_parts = []

                    for field in group_by_fields:
                        if field == 'month':
                            # Add month extraction
                            select_parts.append("DATE_FORMAT(publishedAt, '%Y-%m') as month")
                            group_by_parts.append("DATE_FORMAT(publishedAt, '%Y-%m')")
                        else:
                            select_parts.append(field)
                            group_by_parts.append(field)

                    # Add COUNT
                    select_parts.append("COUNT(*) as count")

                    sql = f"SELECT {', '.join(select_parts)} FROM {table_name} GROUP BY {', '.join(group_by_parts)} ORDER BY count {order};"
                else:
                    # Simple COUNT
                    sql = f"SELECT COUNT(*) as count FROM {table_name};"
            elif specified_fields:
                # User specified particular fields
                sql = f"SELECT {', '.join(specified_fields)} FROM {table_name} LIMIT {limit};"
            else:
                sql = f"SELECT * FROM {table_name} LIMIT {limit};"

            return {
                "sql": sql,
                "confidence": "medium",
                "method": "pattern_matching",
                "enable_thinking": self.openai_config.get('enable_thinking', True) if self.has_openai else True,
                "note": f"Generated using pattern matching. Table: {table_name}, Fields: {specified_fields if specified_fields else 'all'}, Group by: {group_by_fields}, Limit: {limit}"
            }
        else:
            # Could not determine table name
            if any(word in query_lower for word in ['count', 'how many', '计数', '多少']):
                sql = "-- Count query. Please specify table name:\n"
                sql += "SELECT COUNT(*) as count FROM your_table_name;"
            elif any(word in query_lower for word in ['recent', 'latest', '最近']):
                sql = "-- Recent records query. Please specify table and date column:\n"
                sql += "SELECT * FROM your_table_name ORDER BY date_column DESC LIMIT 50;"
            else:
                sql = "-- Please be more specific about your query.\n"
                sql += "-- Examples:\n"
                sql += "-- 'Show all users from the users table'\n"
                sql += "-- 'Count all orders in the orders table'\n"
                sql += "-- 'List recent products from the products table'\n"
                sql += "-- Chinese: '看news表' or '看users表前10条'\n"
                sql += "\nSELECT * FROM your_table_name LIMIT 100;"

            return {
                "sql": sql,
                "confidence": "low",
                "method": "pattern_matching",
                "enable_thinking": self.openai_config.get('enable_thinking', True) if self.has_openai else True,
                "note": "OpenAI not available. Using basic pattern matching. Please specify table names clearly."
            }
