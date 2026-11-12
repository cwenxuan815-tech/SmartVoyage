"""旅游团 RAG 语义检索：Milvus 向量库优先，本地语义检索兜底。

生产路径: Qwen Embedding API 生成向量 → Milvus COSINE 检索（pymilvus）。
本环境未安装 pymilvus / Milvus 不可达时，自动使用基于中文字符 n-gram 的
本地语义检索（同样支持"想看雪山的地方"这类自然语言描述），保证功能可用。
"""
import math
import re
from collections import Counter

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.db import get_connection

conf = Config()
_MILVUS_AVAILABLE = None

TOUR_FIELDS = (
    "tour_id, tour_name, city, days, price, total_seats, remaining_seats, "
    "agency, rating, departure_dates, highlights, description"
)


def get_embedding(text: str) -> list:
    """调用 Qwen Embedding API 生成文本向量（Milvus 路径使用）。"""
    import requests

    headers = {
        "Authorization": f"Bearer {conf.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": conf.embedding_model,
        "input": [text],
        "dimensions": conf.embedding_dim,
    }
    response = requests.post(conf.embedding_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def search_tour_groups_in_milvus(query_text: str, city: str = None, limit: int = 5) -> list:
    """在 Milvus 中做 COSINE 语义检索，返回旅游团列表。"""
    from pymilvus import Collection, connections

    connections.connect(alias="default", host=conf.milvus_host, port=conf.milvus_port)
    collection = Collection(conf.tour_group_collection)
    collection.load()
    results = collection.search(
        data=[get_embedding(query_text)],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=limit,
        output_fields=["tour_id", "tour_name", "city", "days", "price", "highlights"],
        expr=f'city == "{city}"' if city else None,
    )
    return [
        {
            "tour_id": hit.entity.get("tour_id"),
            "tour_name": hit.entity.get("tour_name"),
            "city": hit.entity.get("city"),
            "days": hit.entity.get("days"),
            "price": hit.entity.get("price"),
            "highlights": hit.entity.get("highlights"),
            "similarity": round(float(hit.distance), 4),
        }
        for hits in results for hit in hits
    ]


def _tokens(text: str) -> Counter:
    """中文按单字 + 相邻二字组合切分，兼顾英文词，构造轻量语义特征。"""
    text = (text or "").lower()
    clean = re.sub(r"[\s，。、！？；：,.!?;:（）()\[\]\"']+", "", text)
    features = Counter()
    for ch in clean:
        if '\u4e00' <= ch <= '\u9fff':
            features[ch] += 1
    for i in range(len(clean) - 1):
        pair = clean[i:i + 2]
        if all('\u4e00' <= c <= '\u9fff' for c in pair):
            features["bi:" + pair] += 2
    for word in re.findall(r"[a-z0-9]+", text):
        features[word] += 2
    return features


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def search_local(query_text: str, city: str = None, limit: int = 5) -> list:
    """本地语义检索：城市过滤下推到 SQL，再对候选做中文 n-gram 余弦打分。"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = f"SELECT {TOUR_FIELDS} FROM tour_groups"
        params = []
        if city:
            sql += " WHERE city = %s"
            params.append(city)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    qvec = _tokens(query_text)
    scored = []
    for row in rows:
        doc = f"{row.get('tour_name', '')} {row.get('highlights', '')} {row.get('description', '')}"
        score = _cosine(qvec, _tokens(doc))
        # 查询短语整体命中时给予加权，提升"想看雪山的地方"类口语化描述
        for phrase in re.split(r"[，。、！？\s]+", query_text or ""):
            if len(phrase) >= 2 and phrase in doc:
                score += 0.08
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)

    return [
        {
            "tour_id": row["tour_id"],
            "tour_name": row["tour_name"],
            "city": row["city"],
            "days": row["days"],
            "price": float(row["price"]) if row["price"] is not None else None,
            "remaining_seats": row["remaining_seats"],
            "agency": row["agency"],
            "rating": float(row["rating"]) if row["rating"] is not None else None,
            "departure_dates": row["departure_dates"],
            "highlights": row["highlights"],
            "similarity": round(min(score, 1.0), 4),
        }
        for score, row in scored[:limit] if score > 0
    ]


def search_tour_groups(query_text: str, city: str = None, limit: int = 5) -> list:
    """统一检索入口：Milvus 可用时走向量库，否则本地语义检索。"""
    global _MILVUS_AVAILABLE
    if _MILVUS_AVAILABLE is None:
        try:
            import pymilvus  # noqa: F401
            _MILVUS_AVAILABLE = True
        except ImportError:
            _MILVUS_AVAILABLE = False
            logger.info("未安装 pymilvus，旅游团 RAG 使用本地语义检索")
    if _MILVUS_AVAILABLE:
        try:
            return search_tour_groups_in_milvus(query_text, city, limit)
        except Exception as exc:
            logger.warning(f"Milvus 检索失败，改用本地语义检索: {exc}")
    return search_local(query_text, city, limit)
