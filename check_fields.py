import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metabase_chat.settings')
django.setup()

import asyncio
from chat.services.mcp_client import MCPClient

async def check_fields():
    client = MCPClient()

    # Get news table fields
    result = await client.call_tool("list_tables", {"database_id": 3})
    tables_data = result.get('data', result)
    if isinstance(tables_data, dict) and 'data' in tables_data:
        tables_list = tables_data['data']
    else:
        tables_list = tables_data if isinstance(tables_data, list) else []

    # Find news table
    news_table = None
    for table in tables_list:
        if table.get('name') == 'news':
            news_table = table
            break

    if news_table:
        print(f"News Table ID: {news_table.get('id')}")
        print(f"News Table Name: {news_table.get('name')}")

        # Get table fields
        fields = await client.call_tool("get_table_fields", {"table_id": news_table.get('id')})
        print("\nNews Table Fields:")
        print("-" * 60)

        fields_data = fields.get('data', fields)
        if isinstance(fields_data, dict):
            fields_list = fields_data.get('fields', [])
        else:
            fields_list = fields_data.get('fields', []) if isinstance(fields_data, dict) else []

        for field in fields_list:
            field_name = field.get('name')
            field_type = field.get('base_type', 'unknown')
            print(f"  {field_name:30} {field_type}")

if __name__ == '__main__':
    asyncio.run(check_fields())
