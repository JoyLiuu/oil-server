import os

EASTMONEY_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ABAPI_URL = "https://youjia.abapi.cn"

API_TOKEN = os.environ.get("API_TOKEN", "oil-server-2024")

# 腾讯地图 WebService API Key（服务端保留，不暴露给前端）
# 在 https://lbs.qq.com/ 申请，用于附近加油站真实 POI 查询
# 未配置时自动回退到内置静态加油站数据
TENCENT_MAP_KEY = os.environ.get("TENCENT_MAP_KEY", "").strip()
TENCENT_PLACE_API = "https://apis.map.qq.com/ws/place/v1/search"

# 附近加油站 POI 缓存（秒）与默认搜索半径（米）
POI_CACHE_TTL = 30 * 60
POI_DEFAULT_RADIUS = 5000

REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
