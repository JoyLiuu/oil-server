import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from spider.eastmoney import EastMoneySpider
from spider.abapi import AbapiSpider
from spider.amap import search_nearby_stations, search_stations_by_address, geocode
from spider.prediction import fetch_prediction
from config import AMAP_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

_cache_lock = threading.Lock()
_cache: Dict = {
    "data": None,
    "update_time": None,
    "source": None,
    "fetched_at": None,
}
CACHE_TTL = timedelta(hours=2)

SPIDERS = [
    EastMoneySpider,
    AbapiSpider,
]

_PRICE_FIELDS = [
    "oil_89", "oil_92", "oil_95", "oil_98", "oil_0",
    "change_89", "change_92", "change_95", "change_98", "change_0",
]


def _normalize_prices(prices: List[Dict]) -> List[Dict]:
    result = []
    for item in prices:
        new_item = {}
        for k, v in item.items():
            if k in _PRICE_FIELDS and v is not None:
                try:
                    new_item[k] = round(float(v), 2)
                except (ValueError, TypeError):
                    new_item[k] = v
            else:
                new_item[k] = v
        result.append(new_item)
    return result


def _merge_oil_98(eastmoney_prices: List[Dict], abapi_prices: List[Dict]) -> List[Dict]:
    if not abapi_prices:
        return eastmoney_prices

    abapi_map = {p["province"]: p for p in abapi_prices if p.get("province")}

    for item in eastmoney_prices:
        province = item.get("province", "")
        ab_item = abapi_map.get(province)
        if ab_item:
            if "oil_98" in ab_item and ab_item["oil_98"] is not None:
                item["oil_98"] = ab_item["oil_98"]
            if "change_98" in ab_item and ab_item["change_98"] is not None:
                item["change_98"] = ab_item["change_98"]

    return eastmoney_prices


def _fetch_from_spiders(source: str = "all") -> Optional[List[Dict]]:
    if source == "all":
        spider_classes = SPIDERS
    elif source == "eastmoney":
        spider_classes = [EastMoneySpider]
    elif source == "abapi":
        spider_classes = [AbapiSpider]
    else:
        return None

    for spider_cls in spider_classes:
        spider = spider_cls()
        logger.info(f"[API] 正在从 [{spider.name}] 获取油价数据...")
        result = spider.fetch_oil_prices()
        if result:
            prices = result
            source_name = spider.name

            if spider_cls == EastMoneySpider:
                logger.info("[API] 尝试从 abapi 补充 98# 汽油数据...")
                ab_spider = AbapiSpider()
                ab_result = ab_spider.fetch_oil_prices()
                if ab_result:
                    prices = _merge_oil_98(prices, ab_result)
                    logger.info("[API] 98# 数据补充完成")

            return {
                "prices": prices,
                "update_time": spider.get_update_time(),
                "source": source_name,
            }
        logger.warning(f"[API] [{spider.name}] 获取失败，尝试下一个数据源...")

    return None


def _get_cached_prices(source: str = "all") -> Dict:
    with _cache_lock:
        now = datetime.now()
        if (
            _cache["data"] is not None
            and _cache["fetched_at"] is not None
            and now - _cache["fetched_at"] < CACHE_TTL
        ):
            logger.info("[API] 使用缓存数据")
            return {
                "prices": _cache["data"],
                "update_time": _cache["update_time"],
                "source": _cache["source"],
            }

    result = _fetch_from_spiders(source)
    if result is None:
        with _cache_lock:
            if _cache["data"] is not None:
                logger.warning("[API] 实时获取失败，返回缓存数据")
                return {
                    "prices": _cache["data"],
                    "update_time": _cache["update_time"],
                    "source": _cache["source"],
                }
        return None

    with _cache_lock:
        _cache["data"] = _normalize_prices(result["prices"])
        _cache["update_time"] = result["update_time"]
        _cache["source"] = result["source"]
        _cache["fetched_at"] = datetime.now()

    return result


@app.route("/api/oil", methods=["GET"])
def get_oil_prices():
    province = request.args.get("province", "").strip()
    source = request.args.get("source", "all").strip()

    if source not in ("all", "eastmoney", "abapi"):
        return jsonify({
            "code": 400,
            "message": "无效的source参数，可选值: all, eastmoney, abapi",
            "data": None,
        }), 400

    result = _get_cached_prices(source)
    if result is None:
        return jsonify({
            "code": 500,
            "message": "获取油价数据失败，请稍后重试",
            "data": None,
        }), 500

    prices = result["prices"]

    if province:
        from urllib.parse import unquote
        province = unquote(province)
        prices = [p for p in prices if province in p.get("province", "")]
        if not prices:
            return jsonify({
                "code": 404,
                "message": f"未找到 [{province}] 的油价数据",
                "data": None,
            }), 404

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "update_time": result["update_time"],
            "source": result["source"],
            "count": len(prices),
            "prices": prices,
        },
    })


@app.route("/api/oil/province/<name>", methods=["GET"])
def get_oil_by_province(name: str):
    result = _get_cached_prices("all")
    if result is None:
        return jsonify({
            "code": 500,
            "message": "获取油价数据失败，请稍后重试",
            "data": None,
        }), 500

    prices = [p for p in result["prices"] if name in p.get("province", "")]
    if not prices:
        return jsonify({
            "code": 404,
            "message": f"未找到 [{name}] 的油价数据",
            "data": None,
        }), 404

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "update_time": result["update_time"],
            "source": result["source"],
            "province": name,
            "prices": prices,
        },
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "code": 0,
        "message": "ok",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/station/nearby", methods=["GET"])
def get_nearby_stations():
    if not AMAP_KEY:
        return jsonify({
            "code": 503,
            "message": "服务未配置高德地图API Key，请联系管理员设置环境变量 AMAP_KEY",
            "data": None,
        }), 503

    location = request.args.get("location", "").strip()
    address = request.args.get("address", "").strip()
    city = request.args.get("city", "").strip()
    radius = request.args.get("radius", "3000").strip()

    try:
        radius = int(radius)
        if radius < 100 or radius > 50000:
            return jsonify({
                "code": 400,
                "message": "radius范围应在100-50000米之间",
                "data": None,
            }), 400
    except ValueError:
        return jsonify({
            "code": 400,
            "message": "radius必须为整数",
            "data": None,
        }), 400

    if not location and not address:
        return jsonify({
            "code": 400,
            "message": "必须提供location(经纬度)或address(地址)参数",
            "data": None,
        }), 400

    if address and not location:
        result = search_stations_by_address(address, city, radius)
        if result is None:
            return jsonify({
                "code": 500,
                "message": "地址解析或搜索失败，请检查地址是否正确",
                "data": None,
            }), 500
        return jsonify({
            "code": 0,
            "message": "success",
            "data": result,
        })

    if location:
        try:
            parts = location.split(",")
            if len(parts) != 2:
                raise ValueError
            float(parts[0])
            float(parts[1])
        except (ValueError, IndexError):
            return jsonify({
                "code": 400,
                "message": "location格式错误，应为 经度,纬度（如 116.397428,39.90923）",
                "data": None,
            }), 400

        stations = search_nearby_stations(location, radius)
        if stations is None:
            return jsonify({
                "code": 500,
                "message": "搜索附近加油站失败，请稍后重试",
                "data": None,
            }), 500

        loc_parts = location.split(",")
        return jsonify({
            "code": 0,
            "message": "success",
            "data": {
                "center": {
                    "longitude": float(loc_parts[0]),
                    "latitude": float(loc_parts[1]),
                },
                "radius": radius,
                "count": len(stations),
                "stations": stations,
            },
        })


@app.route("/api/station/geocode", methods=["GET"])
def get_geocode():
    if not AMAP_KEY:
        return jsonify({
            "code": 503,
            "message": "服务未配置高德地图API Key",
            "data": None,
        }), 503

    address = request.args.get("address", "").strip()
    city = request.args.get("city", "").strip()

    if not address:
        return jsonify({
            "code": 400,
            "message": "必须提供address参数",
            "data": None,
        }), 400

    location = geocode(address, city)
    if not location:
        return jsonify({
            "code": 404,
            "message": f"未找到 [{address}] 的坐标",
            "data": None,
        }), 404

    parts = location.split(",")
    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "address": address,
            "city": city,
            "longitude": float(parts[0]),
            "latitude": float(parts[1]),
        },
    })


@app.route("/api/oil/prediction", methods=["GET"])
def get_oil_prediction():
    result = fetch_prediction()
    if result is None:
        return jsonify({
            "code": 500,
            "message": "获取油价预测数据失败",
            "data": None,
        }), 500

    trend = result.get("trend", "")
    trend_map = {
        "up": "预计上调",
        "down": "预计下调",
        "flat": "预计持平",
        "unknown": "待定",
    }
    trend_label = trend_map.get(trend, "待定")

    change_rate = result.get("change_rate")
    confidence = None
    if change_rate is not None:
        confidence = min(abs(change_rate) * 10, 99)
        if confidence < 5:
            confidence = 5

    status = trend if trend else "unknown"
    forecast = trend_label

    predict_gasoline = result.get("predict_gasoline_change")
    predict_diesel = result.get("predict_diesel_change")

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "status": status,
            "forecast": forecast,
            "trend": trend,
            "trend_label": trend_label,
            "confidence": confidence,
            "change_rate": change_rate,
            "prediction_text": result.get("prediction_text", ""),
            "next_window_date": result.get("next_window_date", ""),
            "last_adjust_date": result.get("last_adjust_date", ""),
            "last_gasoline_price": result.get("last_gasoline_price"),
            "last_diesel_price": result.get("last_diesel_price"),
            "last_gasoline_change": result.get("last_gasoline_change"),
            "last_diesel_change": result.get("last_diesel_change"),
            "predict_gasoline_change": predict_gasoline,
            "predict_diesel_change": predict_diesel,
            "history": result.get("history", []),
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
