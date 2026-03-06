"""
测试schema缓存性能优化效果。

运行此脚本来比较优化前后的性能差异。
"""
import os
import django
import time
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'metabase_chat.settings')
django.setup()

from chat.services.nl_to_sql import NLToSQLConverter


async def test_cache_performance():
    converter = NLToSQLConverter()

    print("=" * 70)
    print("Schema缓存性能测试")
    print("=" * 70)

    # 清除缓存以确保从空开始
    NLToSQLConverter.clear_schema_cache()
    print("\n[OK] 已清除所有缓存\n")

    # 第一次查询 - 应该从数据库获取
    print("【第一次查询】 - 从数据库获取schema（无缓存）")
    print("-" * 70)
    start = time.time()
    schema1 = await converter.get_schema_context(3)
    time1 = time.time() - start
    print(f"耗时: {time1:.2f}秒")
    print(f"Schema长度: {len(schema1)} 字符\n")

    # 第二次查询 - 应该从缓存获取
    print("【第二次查询】 - 从缓存获取schema")
    print("-" * 70)
    start = time.time()
    schema2 = await converter.get_schema_context(3)
    time2 = time.time() - start
    print(f"耗时: {time2:.2f}秒")
    print(f"Schema长度: {len(schema2)} 字符\n")

    # 验证两次获取的内容一致
    assert schema1 == schema2, "Schema内容不一致！"
    print("[OK] 验证通过：两次获取的schema内容一致\n")

    # 性能对比
    print("=" * 70)
    print("性能对比结果")
    print("=" * 70)
    print(f"首次获取（无缓存）: {time1:.2f}秒")
    print(f"二次获取（有缓存）: {time2:.2f}秒")

    if time1 > 0:
        speedup = time1 / time2 if time2 > 0 else float('inf')
        print(f"\n加速比: {speedup:.1f}x")
        print(f"节省时间: {time1 - time2:.2f}秒 ({(1 - time2/time1)*100:.1f}%)")

    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)

    # 显示缓存状态
    print("\n缓存信息:")
    print(f"  - 缓存TTL: {NLToSQLConverter._cache_ttl}")
    print(f"  - 已缓存的数据库: {list(NLToSQLConverter._schema_cache.keys())}")


if __name__ == '__main__':
    asyncio.run(test_cache_performance())
