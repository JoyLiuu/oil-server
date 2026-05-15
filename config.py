import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

EASTMONEY_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ABAPI_URL = "https://youjia.abapi.cn"

API_TOKEN = os.environ.get("API_TOKEN", "f8a3c9d1e7b24f5a9d8e6c3b1a7f0e2d9c4b6a5f8d1e3c2b7a9f0d4e6c8b3a1")

REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

OIL_TYPES = {
    "92h": "92号汽油",
    "95h": "95号汽油",
    "98h": "98号汽油",
    "0h": "0号柴油",
}
