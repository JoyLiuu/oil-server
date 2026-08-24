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
from spider.geocoder import coords_to_province, coords_to_city
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


def _norm_province(name: str) -> str:
    return name.replace("省", "").replace("市", "").replace("壮族", "").replace("回族", "").replace("维吾尔", "").replace("自治区", "").strip()


def _merge_oil_98(eastmoney_prices: List[Dict], abapi_prices: List[Dict]) -> List[Dict]:
    if not abapi_prices:
        return eastmoney_prices

    abapi_map = {_norm_province(p["province"]): p for p in abapi_prices if p.get("province")}

    for item in eastmoney_prices:
        province = _norm_province(item.get("province", ""))
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
    longitude = request.args.get("longitude", "").strip()
    latitude = request.args.get("latitude", "").strip()

    if source not in ("all", "eastmoney", "abapi"):
        return jsonify({
            "code": 400,
            "message": "无效的source参数，可选值: all, eastmoney, abapi",
            "data": None,
        }), 400

    if longitude and latitude:
        try:
            lng = float(longitude)
            lat = float(latitude)
            province = coords_to_province(lng, lat)
            if not province:
                return jsonify({
                    "code": 400,
                    "message": "无法根据经纬度确定省份，请检查坐标是否在中国境内",
                    "data": None,
                }), 400
            logger.info(f"[API] 经纬度 ({lng}, {lat}) 转换为省份: {province}")
        except (ValueError, TypeError):
            return jsonify({
                "code": 400,
                "message": "经纬度参数格式错误，请提供有效的数字",
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
            "province": province if province else "全国",
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


@app.route("/api/geocode", methods=["GET"])
@require_token
def geocode():
    try:
        lng = float(request.args.get("longitude", 0))
        lat = float(request.args.get("latitude", 0))
    except (ValueError, TypeError):
        return jsonify({
            "code": 400,
            "message": "经纬度参数格式错误",
            "data": None,
        }), 400

    if lng == 0 and lat == 0:
        return jsonify({
            "code": 400,
            "message": "请提供有效的经纬度参数",
            "data": None,
        }), 400

    result = coords_to_city(lng, lat)
    if not result:
        return jsonify({
            "code": 404,
            "message": "无法根据经纬度确定位置，请检查坐标是否在中国境内",
            "data": None,
        }), 404

    logger.info(f"[API] 经纬度 ({lng}, {lat}) -> 省份: {result['province']}, 城市: {result['city']}")

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "province": result["province"],
            "city": result["city"],
            "district": result.get("district", ""),
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

    trend = result.get("trend", "")
    trend_map = {
        "up": "预计上调",
        "down": "预计下调",
        "flat": "预计持平",
        "unknown": "待定",
    }
    trend_label = trend_map.get(trend, "待定")

    change_rate = result.get("change_rate")
    if change_rate is not None:
        confidence = round(min(abs(change_rate) * 10, 99), 1)
        if confidence < 5:
            confidence = 5
    else:
        # 无官方口径变化率时（爬取源直接给出调幅），按调幅绝对值给参考置信度
        gas_change = abs(result.get("predict_gasoline_change") or 0)
        confidence = round(min(40 + gas_change / 8, 90))

    status = trend if trend else "unknown"
    forecast = trend_label

    predict_gasoline = result.get("predict_gasoline_change")
    predict_diesel = result.get("predict_diesel_change")

    # 距下次调价天数（next_window_date 形如 "2026-08-14 24:00"）
    days_remaining = None
    next_window_date = result.get("next_window_date", "")
    if next_window_date:
        date_part = str(next_window_date).split(" ")[0]
        try:
            target = datetime.strptime(date_part, "%Y-%m-%d").date()
            days_remaining = max(0, (target - datetime.now().date()).days)
        except ValueError:
            pass

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
            "next_window_date": next_window_date,
            "days_remaining": days_remaining,
            "last_adjust_date": result.get("last_adjust_date", ""),
            "last_gasoline_price": result.get("last_gasoline_price"),
            "last_diesel_price": result.get("last_diesel_price"),
            "last_gasoline_change": result.get("last_gasoline_change"),
            "last_diesel_change": result.get("last_diesel_change"),
            "predict_gasoline_change": predict_gasoline,
            "predict_diesel_change": predict_diesel,
            "predict_price_change": result.get("predict_price_change"),
            "history": result.get("history", []),
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
