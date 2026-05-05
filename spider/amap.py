import logging
from typing import List, Dict, Optional

import requests

from config import (
    AMAP_KEY,
    AMAP_AROUND_URL,
    AMAP_GEO_URL,
    AMAP_GAS_STATION_TYPE,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


def _check_key() -> bool:
    if not AMAP_KEY:
        logger.error("[高德地图] 未配置AMAP_KEY，请设置环境变量 AMAP_KEY")
        return False
    return True


def geocode(address: str, city: str = "") -> Optional[str]:
    if not _check_key():
        return None

    params = {
        "key": AMAP_KEY,
        "address": address,
        "output": "JSON",
    }
    if city:
        params["city"] = city

    try:
        resp = requests.get(AMAP_GEO_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            logger.warning(f"[高德地图] 地理编码失败: {data.get('info')}")
            return None

        geocodes = data.get("geocodes", [])
        if not geocodes:
            logger.warning(f"[高德地图] 未找到地址 [{address}] 的坐标")
            return None

        location = geocodes[0].get("location", "")
        logger.info(f"[高德地图] 地址 [{address}] -> 坐标 [{location}]")
        return location

    except requests.RequestException as e:
        logger.error(f"[高德地图] 地理编码请求失败: {e}")
        return None


def search_nearby_stations(
    location: str,
    radius: int = 3000,
    keywords: str = "加油站",
    offset: int = 25,
) -> Optional[List[Dict]]:
    if not _check_key():
        return None

    all_pois = []
    page = 1
    max_page = 5

    while page <= max_page:
        params = {
            "key": AMAP_KEY,
            "location": location,
            "radius": radius,
            "keywords": keywords,
            "types": AMAP_GAS_STATION_TYPE,
            "offset": offset,
            "page": page,
            "output": "JSON",
        }

        try:
            resp = requests.get(
                AMAP_AROUND_URL, params=params, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "1":
                logger.warning(f"[高德地图] 周边搜索失败: {data.get('info')}")
                break

            pois = data.get("pois", [])
            if not pois:
                break

            for poi in pois:
                loc = poi.get("location", "").split(",")
                lng = float(loc[0]) if len(loc) == 2 else None
                lat = float(loc[1]) if len(loc) == 2 else None

                distance = poi.get("distance", "")
                try:
                    distance = int(distance)
                except (ValueError, TypeError):
                    distance = None

                item = {
                    "name": poi.get("name", ""),
                    "address": poi.get("address", "") or poi.get("pname", "") + poi.get("cityname", "") + poi.get("adname", ""),
                    "longitude": lng,
                    "latitude": lat,
                    "distance": distance,
                    "tel": poi.get("tel", ""),
                    "province": poi.get("pname", ""),
                    "city": poi.get("cityname", ""),
                    "district": poi.get("adname", ""),
                    "type": poi.get("type", ""),
                    "poi_id": poi.get("id", ""),
                }
                all_pois.append(item)

            count = int(data.get("count", 0))
            if len(all_pois) >= count or len(pois) < offset:
                break

            page += 1

        except requests.RequestException as e:
            logger.error(f"[高德地图] 周边搜索请求失败: {e}")
            break

    all_pois.sort(key=lambda x: x.get("distance") or 999999)
    logger.info(f"[高德地图] 找到 {len(all_pois)} 个附近加油站")
    return all_pois


def search_stations_by_address(
    address: str,
    city: str = "",
    radius: int = 3000,
) -> Optional[Dict]:
    location = geocode(address, city)
    if not location:
        return None

    stations = search_nearby_stations(location, radius)
    if stations is None:
        return None

    loc_parts = location.split(",")
    return {
        "center": {
            "address": address,
            "longitude": float(loc_parts[0]),
            "latitude": float(loc_parts[1]),
        },
        "radius": radius,
        "count": len(stations),
        "stations": stations,
    }
