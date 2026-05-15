import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS

from spider.eastmoney import EastMoneySpider
from spider.abapi import AbapiSpider
from spider.prediction import fetch_prediction
from config import API_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.url_map.strict_slashes = False
CORS(app, resources={r"/api/*": {"origins": "*"}})


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = ""

        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        elif auth_header:
            token = auth_header

        if not token:
            token = request.args.get("token", "")

        if token != API_TOKEN:
            return jsonify({
                "code": 401,
                "message": "无效的Token，请在请求头中添加 Authorization: Bearer <token> 或在URL中添加 token 参数",
                "data": None,
            }), 401
        return f(*args, **kwargs)
    return decorated


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
@require_token
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


@app.route("/api/oil/province/", methods=["GET"])
@app.route("/api/oil/province/<name>", methods=["GET"])
@require_token
def get_oil_by_province(name: str = ""):
    result = _get_cached_prices("all")
    if result is None:
        return jsonify({
            "code": 500,
            "message": "获取油价数据失败，请稍后重试",
            "data": None,
        }), 500

    if not name:
        return jsonify({
            "code": 400,
            "message": "请提供省份名称，如 /api/oil/province/北京",
            "data": None,
        }), 400

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


@app.route("/api/oil/prediction", methods=["GET"])
@require_token
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


@app.route("/api/station/nearby", methods=["GET"])
@require_token
def get_nearby_stations():
    province = request.args.get("province", "").strip()
    city = request.args.get("city", "").strip()
    district = request.args.get("district", "").strip()

    if not province and not city:
        return jsonify({
            "code": 400,
            "message": "必须提供province(省份)或city(城市)参数",
            "data": None,
        }), 400

    stations = _get_mock_stations(province, city, district)

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "province": province,
            "city": city,
            "district": district,
            "count": len(stations),
            "stations": stations,
        },
    })


def _get_mock_stations(province: str, city: str, district: str) -> List[Dict]:
    all_stations = [
        {"name": "中国石化加油站", "brand": "中石化", "address": "北京市朝阳区建国路88号", "province": "北京", "city": "北京市", "district": "朝阳区", "oil_92": 8.72, "oil_95": 9.28, "oil_0": 8.46},
        {"name": "中国石油加油站", "brand": "中石油", "address": "北京市海淀区中关村大街1号", "province": "北京", "city": "北京市", "district": "海淀区", "oil_92": 8.72, "oil_95": 9.28, "oil_0": 8.46},
        {"name": "中国石化加油站", "brand": "中石化", "address": "上海市浦东新区陆家嘴环路1000号", "province": "上海", "city": "上海市", "district": "浦东新区", "oil_92": 8.65, "oil_95": 9.21, "oil_0": 8.39},
        {"name": "中国石油加油站", "brand": "中石油", "address": "上海市黄浦区南京东路100号", "province": "上海", "city": "上海市", "district": "黄浦区", "oil_92": 8.65, "oil_95": 9.21, "oil_0": 8.39},
        {"name": "中国石化加油站", "brand": "中石化", "address": "广州市天河区天河路200号", "province": "广东", "city": "广州市", "district": "天河区", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
        {"name": "中国石油加油站", "brand": "中石油", "address": "广州市越秀区中山三路50号", "province": "广东", "city": "广州市", "district": "越秀区", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
        {"name": "中国石化加油站", "brand": "中石化", "address": "深圳市福田区深南大道100号", "province": "广东", "city": "深圳市", "district": "福田区", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
        {"name": "中国石油加油站", "brand": "中石油", "address": "深圳市南山区南海大道200号", "province": "广东", "city": "深圳市", "district": "南山区", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
        {"name": "中国石化加油站", "brand": "中石化", "address": "杭州市西湖区文三路100号", "province": "浙江", "city": "杭州市", "district": "西湖区", "oil_92": 8.66, "oil_95": 9.22, "oil_0": 8.38},
        {"name": "中国石油加油站", "brand": "中石油", "address": "杭州市上城区解放路50号", "province": "浙江", "city": "杭州市", "district": "上城区", "oil_92": 8.66, "oil_95": 9.22, "oil_0": 8.38},
        {"name": "中国石化加油站", "brand": "中石化", "address": "南京市鼓楼区中山北路100号", "province": "江苏", "city": "南京市", "district": "鼓楼区", "oil_92": 8.68, "oil_95": 9.24, "oil_0": 8.40},
        {"name": "中国石油加油站", "brand": "中石油", "address": "南京市玄武区珠江路200号", "province": "江苏", "city": "南京市", "district": "玄武区", "oil_92": 8.68, "oil_95": 9.24, "oil_0": 8.40},
        {"name": "中国石化加油站", "brand": "中石化", "address": "成都市锦江区人民南路100号", "province": "四川", "city": "成都市", "district": "锦江区", "oil_92": 8.80, "oil_95": 9.42, "oil_0": 8.45},
        {"name": "中国石油加油站", "brand": "中石油", "address": "成都市武侯区一环路200号", "province": "四川", "city": "成都市", "district": "武侯区", "oil_92": 8.80, "oil_95": 9.42, "oil_0": 8.45},
        {"name": "中国石化加油站", "brand": "中石化", "address": "武汉市江汉区解放大道100号", "province": "湖北", "city": "武汉市", "district": "江汉区", "oil_92": 8.70, "oil_95": 9.32, "oil_0": 8.42},
        {"name": "中国石油加油站", "brand": "中石油", "address": "武汉市武昌区中南路200号", "province": "湖北", "city": "武汉市", "district": "武昌区", "oil_92": 8.70, "oil_95": 9.32, "oil_0": 8.42},
        {"name": "中国石化加油站", "brand": "中石化", "address": "西安市雁塔区长安南路100号", "province": "陕西", "city": "西安市", "district": "雁塔区", "oil_92": 8.62, "oil_95": 9.12, "oil_0": 8.35},
        {"name": "中国石油加油站", "brand": "中石油", "address": "西安市碑林区东大街200号", "province": "陕西", "city": "西安市", "district": "碑林区", "oil_92": 8.62, "oil_95": 9.12, "oil_0": 8.35},
        {"name": "中国石化加油站", "brand": "中石化", "address": "天津市和平区南京路100号", "province": "天津", "city": "天津市", "district": "和平区", "oil_92": 8.71, "oil_95": 9.20, "oil_0": 8.39},
        {"name": "中国石油加油站", "brand": "中石油", "address": "天津市河西区友谊路200号", "province": "天津", "city": "天津市", "district": "河西区", "oil_92": 8.71, "oil_95": 9.20, "oil_0": 8.39},
    ]

    result = []
    for station in all_stations:
        match = True
        if province and province not in station["province"]:
            match = False
        if city and city not in station["city"]:
            match = False
        if district and district not in station["district"]:
            match = False
        if match:
            result.append(station)

    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
