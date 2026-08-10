# 微信油价服务器 (wx-oil-server)

一个基于Python的油价信息API服务，提供全国油价查询、油价预测和加油站定位功能。

## 功能特性

- **油价查询**: 支持按省份、城市查询油价
- **经纬度查询**: 通过经纬度自动定位所在省份并返回油价
- **油价预测**: 提供油价趋势预测和调整窗口信息
- **加油站定位**: 基于地理位置查找附近加油站
- **多数据源**: 支持东方财富、abapi等多个数据源

## API接口

### 1. 油价查询

#### 按省份查询
```http
GET /api/oil?province=北京
```

#### 按经纬度查询
```http
GET /api/oil?longitude=116.405&latitude=39.905
```

**参数说明**:
- `longitude`: 经度（如：116.405）
- `latitude`: 纬度（如：39.905）
- `province`: 省份名称（与经纬度二选一）
- `source`: 数据源（可选：all, eastmoney, abapi）

**响应示例**:
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "update_time": "2026-07-23",
        "source": "东方财富网",
        "province": "北京",
        "count": 1,
        "prices": [
            {
                "province": "北京",
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_98": 10.28,
                "oil_0": 8.46,
                "change_92": 0.15,
                "change_95": 0.16,
                "change_0": 0.14
            }
        ]
    }
}
```

### 2. 按省份路径查询
```http
GET /api/oil/province/广东
```

### 3. 油价预测
```http
GET /api/oil/prediction
```

### 4. 附近加油站
```http
GET /api/station/nearby?longitude=116.405&latitude=39.905
```

### 5. 健康检查
```http
GET /api/health
```

## 部署

### 本地开发
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python api.py
```

### Docker部署
```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 环境变量
- `API_TOKEN`: API访问令牌（默认：oil-server-2024）
- `TENCENT_MAP_KEY`: 腾讯地图 WebService API Key（可选）。配置后附近加油站返回真实 POI 数据，未配置则使用内置静态数据

## 数据源

1. **东方财富网**: 主要数据源，提供全国各省份油价
2. **abapi**: 补充数据源，提供98号汽油数据

## 技术栈

- **后端**: Python + Flask
- **数据采集**: requests + BeautifulSoup
- **地理编码**: 内置坐标映射（完全免费，无外部依赖）
- **部署**: Docker + Nginx

## 许可证

MIT License
