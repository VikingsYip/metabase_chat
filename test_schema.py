import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metabase_chat.settings')
django.setup()

import asyncio
from chat.services.nl_to_sql import NLToSQLConverter

async def test():
    converter = NLToSQLConverter()

    # Test query with time-based grouping
    query = '统计news按category和月份'
    print(f'测试查询: {query}\n')
    print('=' * 60)

    result = await converter.convert(query, 3)

    print(f'使用方法: {result.get("method")}')
    print(f'生成的SQL:\n{result.get("sql")}')
    print(f'置信度: {result.get("confidence")}')
    print('=' * 60)

if __name__ == '__main__':
    asyncio.run(test())
