import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metabase_chat.settings')
django.setup()

import asyncio
from chat.services.nl_to_sql import NLToSQLConverter

async def test():
    converter = NLToSQLConverter()

    test_queries = [
        '看news的分类是国际媒体',
        '显示news表中category为科技媒体的记录',
    ]

    for query in test_queries:
        print(f'\n测试查询: {query}')
        result = await converter.convert(query, 3)
        print(f'使用方法: {result.get("method")}')
        print(f'生成的SQL: {result.get("sql")}')
        print(f'置信度: {result.get("confidence")}')
        print('-' * 60)

if __name__ == '__main__':
    asyncio.run(test())
