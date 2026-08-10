"""
附近加油站 POI 模块

通过腾讯地图 WebService API 查询附近的加油站真实数据。
未配置 TENCENT_MAP_KEY 或请求失败时返回 None，由调用方回退到内置静态数据。
"""

import logging
import threading
import time
from typing import Dict, List, Optional

import requests

from config import (
    TENCENT_MAP_KEY,
    TENCENT_PLACE_API,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
    POI_CACHE_TTL,
    POI_DEFAULT_RADIUS,
)
from spider.utils import haversine

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_cache: Dict[str, Dict] = {}


def _cache_key(lng: float, lat: float) -> str:
    # 按约 0.01 度（约 1km）网格聚合，避免缓存无限膨胀
    return f"{round(lng, 2)},{round(lat, 2)}"


def _request_page(
    lng: float, lat: float, radius: int, page_index: int, page_size: int
) -> Optional[Dict]:
    """请求一页腾讯地图 POI 数据，返回 {total, stations} 或 None"""
    params = {
        "keyword": "加油站",
        "boundary": f"nearby({lat},{lng},{radius})",
        "page_index": str(page_index),
        "page_size": str(page_size),
        "key": TENCENT_MAP_KEY,
    }

    try:
        resp = requests.get(
            TENCENT_PLACE_API,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"[POI] 请求失败: {e}")
        return None
    except ValueError as e:
        logger.error(f"[POI] 响应解析失败: {e}")
        return None

    if data.get("status") != 0:
        logger.warning(f"[POI] 接口返回错误: {data.get('message')} (status={data.get('status')})")
        return None

    rows = data.get("data") or []
    stations = []
    for item in rows:
        station = _normalize(item, lng, lat)
        if station:
            stations.append(station)

    logger.info(f"[POI] 第 {page_index} 页获取 {len(stations)} 个加油站 (共 {data.get('count', 0)})")
    return {
        "total": data.get("count", 0) or len(stations),
        "stations": stations,
    }


def _normalize(item: Dict, lng: float, lat: float) -> Optional[Dict]:
    loc = item.get("location") or {}
    try:
        s_lng = float(loc.get("lng", 0))
        s_lat = float(loc.get("lat", 0))
    except (ValueError, TypeError):
        return None

    if not s_lng or not s_lat:
        return None

    try:
        distance = int(float(item.get("_distance")))
    except (ValueError, TypeError):
        distance = int(haversine(lng, lat, s_lng, s_lat))

    return {
        "id": str(item.get("id", "")),
        "name": item.get("title", ""),
        "address": item.get("address", ""),
        "longitude": s_lng,
        "latitude": s_lat,
        "distance": distance,
        "tel": item.get("tel", ""),
        "brand": "",
        "tags": [],
    }


def _fetch_pages(lng: float, lat: float, radius: int, max_stations: int) -> Optional[Dict]:
    """跨页拉取最多 max_stations 个加油站，按 id 去重"""
    stations: List[Dict] = []
    seen = set()
    total = 0
    page_index = 1

    while len(stations) < max_stations:
        page = _request_page(lng, lat, radius, page_index, 20)
        if not page:
            break
        if page_index == 1:
            total = page["total"]
        for s in page["stations"]:
            if s["id"] not in seen:
                seen.add(s["id"])
                stations.append(s)
        if not page["stations"]:
            break
        page_index += 1
        if page_index > 10:
            break

    if not stations and total == 0:
        return None

    return {
        "total": total or len(stations),
        "stations": stations,
    }


def search_nearby_gas_stations(
    lng: float, lat: float, radius: int = None, page: int = 1, limit: int = 20
) -> Optional[Dict]:
    """
    查询附近加油站，返回 {total, stations}。
    未配置 Key 或全部请求失败时返回 None。
    """
    if not TENCENT_MAP_KEY:
        logger.info("[POI] 未配置 TENCENT_MAP_KEY，使用内置静态数据")
        return None

    if radius is None:
        radius = POI_DEFAULT_RADIUS
    max_stations = min(max(page * limit, limit), 60)

    key = _cache_key(lng, lat)
    now = time.time()

    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["ts"] < POI_CACHE_TTL:
            stations = hit["data"]["stations"]
            total = hit["data"]["total"]
            start = (page - 1) * limit
            return {
                "total": total,
                "stations": stations[start : start + limit],
            }

    result = _fetch_pages(lng, lat, radius, max_stations)
    if result is None:
        return None

    with _cache_lock:
        _cache[key] = {"ts": now, "data": result}

    start = (page - 1) * limit
    return {
        "total": result["total"],
        "stations": result["stations"][start : start + limit],
    }
