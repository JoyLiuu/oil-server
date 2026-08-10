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
from spider.poi import search_nearby_gas_stations
from spider.utils import haversine
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

    change_rate = result.get("change_rate") or 0
    confidence = min(abs(change_rate) * 10, 99)
    if confidence < 5:
        confidence = 5

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
            "history": result.get("history", []),
        },
    })


ALL_STATIONS = [
    {"id": 1, "name": "中国石化加油站（朝阳站）", "brand": "中石化", "address": "北京市朝阳区建国路88号", "province": "北京", "city": "北京市", "district": "朝阳区", "longitude": 116.461, "latitude": 39.908, "tel": "010-88886666", "oil_92": 8.72, "oil_95": 9.28, "oil_0": 8.46},
    {"id": 2, "name": "中国石油加油站（海淀站）", "brand": "中石油", "address": "北京市海淀区中关村大街1号", "province": "北京", "city": "北京市", "district": "海淀区", "longitude": 116.310, "latitude": 39.984, "tel": "010-66668888", "oil_92": 8.72, "oil_95": 9.28, "oil_0": 8.46},
    {"id": 3, "name": "中国石化加油站（浦东站）", "brand": "中石化", "address": "上海市浦东新区陆家嘴环路1000号", "province": "上海", "city": "上海市", "district": "浦东新区", "longitude": 121.505, "latitude": 31.240, "tel": "021-58880000", "oil_92": 8.65, "oil_95": 9.21, "oil_0": 8.39},
    {"id": 4, "name": "中国石油加油站（黄浦站）", "brand": "中石油", "address": "上海市黄浦区南京东路100号", "province": "上海", "city": "上海市", "district": "黄浦区", "longitude": 121.474, "latitude": 31.232, "tel": "021-63220000", "oil_92": 8.65, "oil_95": 9.21, "oil_0": 8.39},
    {"id": 5, "name": "中国石化加油站（天河站）", "brand": "中石化", "address": "广州市天河区天河路200号", "province": "广东", "city": "广州市", "district": "天河区", "longitude": 113.322, "latitude": 23.129, "tel": "020-85550000", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
    {"id": 6, "name": "中国石油加油站（越秀站）", "brand": "中石油", "address": "广州市越秀区中山三路50号", "province": "广东", "city": "广州市", "district": "越秀区", "longitude": 113.269, "latitude": 23.128, "tel": "020-87770000", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
    {"id": 7, "name": "中国石化加油站（福田站）", "brand": "中石化", "address": "深圳市福田区深南大道100号", "province": "广东", "city": "深圳市", "district": "福田区", "longitude": 114.054, "latitude": 22.541, "tel": "0755-82800000", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
    {"id": 8, "name": "中国石油加油站（南山站）", "brand": "中石油", "address": "深圳市南山区南海大道200号", "province": "广东", "city": "深圳市", "district": "南山区", "longitude": 113.920, "latitude": 22.536, "tel": "0755-26660000", "oil_92": 8.78, "oil_95": 9.52, "oil_0": 8.48},
    {"id": 9, "name": "中国石化加油站（西湖站）", "brand": "中石化", "address": "杭州市西湖区文三路100号", "province": "浙江", "city": "杭州市", "district": "西湖区", "longitude": 120.128, "latitude": 30.274, "tel": "0571-88880000", "oil_92": 8.66, "oil_95": 9.22, "oil_0": 8.38},
    {"id": 10, "name": "中国石油加油站（上城站）", "brand": "中石油", "address": "杭州市上城区解放路50号", "province": "浙江", "city": "杭州市", "district": "上城区", "longitude": 120.172, "latitude": 30.250, "tel": "0571-87780000", "oil_92": 8.66, "oil_95": 9.22, "oil_0": 8.38},
    {"id": 11, "name": "中国石化加油站（鼓楼站）", "brand": "中石化", "address": "南京市鼓楼区中山北路100号", "province": "江苏", "city": "南京市", "district": "鼓楼区", "longitude": 118.785, "latitude": 32.076, "tel": "025-83300000", "oil_92": 8.68, "oil_95": 9.24, "oil_0": 8.40},
    {"id": 12, "name": "中国石油加油站（玄武站）", "brand": "中石油", "address": "南京市玄武区珠江路200号", "province": "江苏", "city": "南京市", "district": "玄武区", "longitude": 118.792, "latitude": 32.052, "tel": "025-86800000", "oil_92": 8.68, "oil_95": 9.24, "oil_0": 8.40},
    {"id": 13, "name": "中国石化加油站（锦江站）", "brand": "中石化", "address": "成都市锦江区人民南路100号", "province": "四川", "city": "成都市", "district": "锦江区", "longitude": 104.081, "latitude": 30.656, "tel": "028-86660000", "oil_92": 8.80, "oil_95": 9.42, "oil_0": 8.45},
    {"id": 14, "name": "中国石油加油站（武侯站）", "brand": "中石油", "address": "成都市武侯区一环路200号", "province": "四川", "city": "成都市", "district": "武侯区", "longitude": 104.055, "latitude": 30.637, "tel": "028-85500000", "oil_92": 8.80, "oil_95": 9.42, "oil_0": 8.45},
    {"id": 15, "name": "中国石化加油站（江汉站）", "brand": "中石化", "address": "武汉市江汉区解放大道100号", "province": "湖北", "city": "武汉市", "district": "江汉区", "longitude": 114.278, "latitude": 30.595, "tel": "027-85780000", "oil_92": 8.70, "oil_95": 9.32, "oil_0": 8.42},
    {"id": 16, "name": "中国石油加油站（武昌站）", "brand": "中石油", "address": "武汉市武昌区中南路200号", "province": "湖北", "city": "武汉市", "district": "武昌区", "longitude": 114.330, "latitude": 30.543, "tel": "027-87270000", "oil_92": 8.70, "oil_95": 9.32, "oil_0": 8.42},
    {"id": 17, "name": "中国石化加油站（雁塔站）", "brand": "中石化", "address": "西安市雁塔区长安南路100号", "province": "陕西", "city": "西安市", "district": "雁塔区", "longitude": 108.942, "latitude": 34.219, "tel": "029-85250000", "oil_92": 8.62, "oil_95": 9.12, "oil_0": 8.35},
    {"id": 18, "name": "中国石油加油站（碑林站）", "brand": "中石油", "address": "西安市碑林区东大街200号", "province": "陕西", "city": "西安市", "district": "碑林区", "longitude": 108.960, "latitude": 34.257, "tel": "029-87280000", "oil_92": 8.62, "oil_95": 9.12, "oil_0": 8.35},
    {"id": 19, "name": "中国石化加油站（和平站）", "brand": "中石化", "address": "天津市和平区南京路100号", "province": "天津", "city": "天津市", "district": "和平区", "longitude": 117.205, "latitude": 39.117, "tel": "022-23300000", "oil_92": 8.71, "oil_95": 9.20, "oil_0": 8.39},
    {"id": 20, "name": "中国石油加油站（河西站）", "brand": "中石油", "address": "天津市河西区友谊路200号", "province": "天津", "city": "天津市", "district": "河西区", "longitude": 117.212, "latitude": 39.107, "tel": "022-28350000", "oil_92": 8.71, "oil_95": 9.20, "oil_0": 8.39},
]


@app.route("/api/station/nearby", methods=["GET"])
@require_token
def get_nearby_stations():
    province = request.args.get("province", "").strip()
    city = request.args.get("city", "").strip()
    district = request.args.get("district", "").strip()

    try:
        user_lng = float(request.args.get("longitude", 0))
        user_lat = float(request.args.get("latitude", 0))
    except (ValueError, TypeError):
        user_lng, user_lat = 0, 0

    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(100, int(request.args.get("limit", 20))))
    except (ValueError, TypeError):
        page, limit = 1, 20

    radius = request.args.get("radius")
    if radius:
        try:
            radius = int(radius)
        except (ValueError, TypeError):
            radius = None

    # 未传位置名称时，用坐标反查省份/城市，保证前端能展示具体城市
    if (not province and not city and user_lng and user_lat):
        geo = coords_to_city(user_lng, user_lat)
        if geo:
            province = geo.get("province", "") or province
            city = geo.get("city", "") or city
            district = geo.get("district", "") or district

    # 优先使用真实 POI 数据源（需配置 TENCENT_MAP_KEY）
    if user_lng and user_lat:
        poi_result = search_nearby_gas_stations(
            user_lng, user_lat, radius=radius, page=page, limit=limit
        )
        if poi_result is not None:
            return jsonify({
                "code": 0,
                "message": "success",
                "data": {
                    "province": province,
                    "city": city,
                    "district": district,
                    "total": poi_result["total"],
                    "stations": poi_result["stations"],
                    "source": "tencent",
                },
            })
        logger.warning("[API] POI 数据源不可用，回退到内置静态数据")

    result = []
    for station in ALL_STATIONS:
        match = True
        if province and province not in station["province"]:
            match = False
        if city and city not in station["city"]:
            match = False
        if district and district not in station["district"]:
            match = False
        if match:
            s = dict(station)
            if user_lng and user_lat:
                s["distance"] = round(haversine(user_lng, user_lat, s["longitude"], s["latitude"]))
            else:
                s["distance"] = 0
            result.append(s)

    result.sort(key=lambda s: s["distance"])
    total = len(result)
    start = (page - 1) * limit
    paged = result[start:start + limit]

    return jsonify({
        "code": 0,
        "message": "success",
        "data": {
            "province": province,
            "city": city,
            "district": district,
            "total": total,
            "stations": paged,
            "source": "static",
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
