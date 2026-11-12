"""MySQL/SQLite 查询结果的 JSON 兼容格式化工具。"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal


def default_encoder(obj):
    """格式化单个对象，将非标准类型转换为 JSON 兼容格式。"""
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, date):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, timedelta):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    return obj


class DateEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 date/datetime/timedelta/Decimal。"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, timedelta):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)


def dumps(payload: dict) -> str:
    """统一序列化入口。"""
    return json.dumps(payload, cls=DateEncoder, ensure_ascii=False, default=default_encoder)
