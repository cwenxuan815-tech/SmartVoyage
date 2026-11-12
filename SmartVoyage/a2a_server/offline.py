"""离线规则路由：不调用 LLM，但仍走完整 A2A → MCP → 数据库链路。

用于 SV_OFFLINE=1 或未配置 API Key 时的自动化测试与本地演示。
"""
import json
import re
from datetime import date, timedelta

CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "西安", "三亚",
    "重庆", "武汉", "苏州", "丽江", "大理", "青岛", "厦门", "天津", "长沙",
    "昆明", "拉萨", "桂林", "洛阳", "张家界",
]
SEAT_TYPES = ["二等座", "一等座", "商务座", "硬座", "软卧", "经济舱", "商务舱", "头等舱"]
TICKET_TYPES = ["看台票", "内场票", "VIP", "贵宾票"]
CAR_TYPES = ["经济型", "SUV", "豪华型", "MPV"]
INSURANCE_TYPES = ["综合型", "意外型", "医疗型", "境外型"]

DATE_RE = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
SHORT_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日?")


def extract_date(text: str, default: bool = False):
    """提取日期；支持绝对日期与今天/明天/后天等相对表达。"""
    match = DATE_RE.search(text or "")
    if match:
        y, m, d = (int(g) for g in match.groups())
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            pass
    match = SHORT_DATE_RE.search(text or "")
    if match:
        try:
            return date(date.today().year, int(match.group(1)), int(match.group(2))).isoformat()
        except ValueError:
            pass
    if re.search(r"后天", text or ""):
        return (date.today() + timedelta(days=2)).isoformat()
    if re.search(r"明天|明日", text or ""):
        return (date.today() + timedelta(days=1)).isoformat()
    if re.search(r"今天|今日", text or ""):
        return date.today().isoformat()
    return date.today().isoformat() if default else None


def extract_cities(text: str) -> list:
    """按文本出现顺序提取城市名。"""
    found = []
    for match in re.finditer("|".join(CITIES), text or ""):
        if match.group() not in found:
            found.append(match.group())
    return found


def _first(text: str, options: list):
    """按文本出现位置取最先命中的选项（支持新槽位覆盖历史槽位）。"""
    haystack = (text or "").lower()
    matches = [(haystack.find(option.lower()), option)
               for option in options if option.lower() in haystack]
    return min(matches)[1] if matches else None


def _need(message: str) -> dict:
    return {"status": "input_required", "message": message, "need_input": True}


def _ok(message: str) -> dict:
    return {"status": "success", "message": message, "need_input": False}


async def call_tool(session, name: str, arguments: dict) -> dict:
    """调用 MCP 工具并解析返回结果。"""
    arguments = {key: value for key, value in arguments.items() if value is not None}
    try:
        result = await session.call_tool(name, arguments)
    except Exception as exc:
        return {"status": "error", "message": f"工具 {name} 调用失败: {exc}"}
    parts = getattr(result, "content", []) or []
    text = "".join(getattr(part, "text", "") for part in parts)
    if getattr(result, "isError", False):
        return {"status": "error", "message": text or "工具调用失败"}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"status": "success", "message": text}


def format_weather(payload: dict) -> str:
    if payload.get("status") != "success":
        return payload.get("message", "未找到天气数据")
    lines = ["天气查询结果："]
    for item in payload.get("data", [])[:10]:
        lines.append(
            f"- {item.get('city')} {item.get('fx_date')}：{item.get('text_day')}，"
            f"{item.get('temp_min')}~{item.get('temp_max')}℃，湿度 {item.get('humidity')}%，"
            f"{item.get('wind_dir_day', '')}{item.get('wind_scale_day', '')}，降水 {item.get('precip', 0)}mm"
        )
    return "\n".join(lines)


def format_tickets(payload: dict, kind: str) -> str:
    if payload.get("status") != "success":
        return payload.get("message", "未找到票务数据")
    label = {"train": "火车票", "flight": "机票", "concert": "演唱会票"}.get(kind, "票务")
    lines = [f"{label}查询结果（共 {len(payload.get('data', []))} 条）："]
    for item in payload.get("data", [])[:8]:
        number = item.get("train_number") or item.get("flight_number") or item.get("artist") or ""
        seat = item.get("seat_type") or item.get("cabin_type") or item.get("ticket_type") or ""
        start = item.get("departure_time") or item.get("start_time") or ""
        lines.append(
            f"- {number} {seat}，{start}，¥{item.get('price')}，"
            f"余票 {item.get('remaining_seats')} 张"
            + (f"，{item.get('venue')}" if item.get("venue") else "")
        )
    return "\n".join(lines)


def format_trip(payload: dict, kind: str) -> str:
    if payload.get("status") != "success":
        return payload.get("message", "未找到行程数据")
    lines = ["行程查询结果："]
    for item in payload.get("data", [])[:8]:
        if kind == "car":
            lines.append(f"- {item.get('company')} {item.get('car_model')}（{item.get('car_type')}），"
                         f"¥{item.get('price_per_day')}/天，可租 {item.get('total_available')} 辆")
        elif kind == "insurance":
            lines.append(f"- {item.get('name')}（{item.get('insurance_type')}），"
                         f"¥{item.get('price')}/份，保障 {item.get('duration_days')} 天，"
                         f"最高赔付 ¥{item.get('max_coverage')}")
        else:
            lines.append(f"- {item.get('tour_name')}：{item.get('city')}出发，"
                         f"{item.get('days')}天，¥{item.get('price')}，"
                         f"剩余 {item.get('remaining_seats')} 名额，"
                         f"语义相似度 {item.get('similarity')}，亮点：{item.get('highlights')}")
    return "\n".join(lines)


async def offline_weather(session, conversation: str) -> dict:
    cities = extract_cities(conversation)
    city = cities[0] if cities else "全国"
    start = extract_date(conversation, default=False)
    if not start:
        start = date.today().isoformat()
    span = 14 if re.search(r"半个月|未来|一周|7天|三天|3天", conversation) else 2
    end = (date.fromisoformat(start) + timedelta(days=span)).isoformat()
    payload = await call_tool(session, "query_weather", {
        "city": city, "start_date": start, "end_date": end,
    })
    return _ok(format_weather(payload))


async def offline_ticket(session, conversation: str) -> dict:
    if re.search(r"演唱会|演出|门票", conversation):
        kind = "concert"
    elif re.search(r"机票|航班|飞机", conversation):
        kind = "flight"
    else:
        kind = "train"

    cities = extract_cities(conversation)
    day = extract_date(conversation)
    if kind == "concert":
        artist = None
        for name in ["刀郎", "张杰", "周杰伦", "五月天", "张学友"]:
            if name in conversation:
                artist = name
                break
        if not (cities and artist and day):
            return _need("请提供演唱会所在城市、艺人名称和演出日期？")
        payload = await call_tool(session, "query_concert", {
            "city": cities[0], "artist": artist, "date": day,
            "ticket_type": _first(conversation, TICKET_TYPES),
        })
    else:
        if len(cities) < 2 or not day:
            return _need("请提供出发城市、到达城市和出发日期？")
        tool = "query_train" if kind == "train" else "query_flight"
        seat_key = "seat_type" if kind == "train" else "cabin_type"
        payload = await call_tool(session, tool, {
            "departure_city": cities[0], "arrival_city": cities[1],
            "date": day, seat_key: _first(conversation, SEAT_TYPES),
        })
    return _ok(format_tickets(payload, kind))


async def offline_trip(session, conversation: str) -> dict:
    cities = extract_cities(conversation)
    if re.search(r"租车|包车|用车", conversation):
        day = extract_date(conversation, default=True)
        if not cities:
            return _need("请提供取车城市和还车城市？")
        payload = await call_tool(session, "query_car_rental", {
            "pickup_city": cities[0],
            "return_city": cities[1] if len(cities) > 1 else cities[0],
            "date": day, "car_type": _first(conversation, CAR_TYPES),
        })
        return _ok(format_trip(payload, "car"))
    if re.search(r"保险|保障", conversation):
        payload = await call_tool(session, "query_insurance", {
            "insurance_type": _first(conversation, INSURANCE_TYPES),
        })
        return _ok(format_trip(payload, "insurance"))
    payload = await call_tool(session, "query_tour_group", {
        "query_text": conversation,
        "city": cities[0] if cities else None,
    })
    return _ok(format_trip(payload, "tour"))
