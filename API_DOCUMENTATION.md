# 微信油价服务器 API 文档

## 基础信息

- **Base URL**: `http://localhost:5001`
- **认证方式**: Bearer Token 或 URL参数 `token`
- **默认Token**: `oil-server-2024`
- **数据格式**: JSON

## 认证方式

所有接口（除健康检查外）都需要Token认证，支持两种方式：

### 方式1：请求头认证
```http
Authorization: Bearer oil-server-2024
```

### 方式2：URL参数认证
```http
?token=oil-server-2024
```

---

## 接口列表

### 1. 油价查询

#### 1.1 按省份查询

**请求**
```http
GET /api/oil?province={省份名称}&token={token}
```

**参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| province | string | 否 | 省份名称，如"北京"、"广东" |
| source | string | 否 | 数据源：all（默认）、eastmoney、abapi |
| token | string | 是 | API认证Token |

**请求示例**
```bash
# 查询北京油价
curl "http://localhost:5001/api/oil?province=北京&token=oil-server-2024"

# 查询广东油价（使用eastmoney数据源）
curl "http://localhost:5001/api/oil?province=广东&source=eastmoney&token=oil-server-2024"
```

**响应示例**
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
                "oil_89": 8.21,
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_98": 10.28,
                "oil_0": 8.46,
                "change_89": 0.14,
                "change_92": 0.15,
                "change_95": 0.16,
                "change_98": 0.17,
                "change_0": 0.14,
                "adjust_date": "2026-07-23"
            }
        ]
    }
}
```

#### 1.2 按经纬度查询

**请求**
```http
GET /api/oil?longitude={经度}&latitude={纬度}&token={token}
```

**参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| longitude | float | 是 | 经度（如：116.405） |
| latitude | float | 是 | 纬度（如：39.905） |
| source | string | 否 | 数据源：all（默认）、eastmoney、abapi |
| token | string | 是 | API认证Token |

**请求示例**
```bash
# 北京天安门坐标
curl "http://localhost:5001/api/oil?longitude=116.405&latitude=39.905&token=oil-server-2024"

# 上海东方明珠坐标
curl "http://localhost:5001/api/oil?longitude=121.473&latitude=31.230&token=oil-server-2024"

# 广州珠江新城坐标
curl "http://localhost:5001/api/oil?longitude=113.322&latitude=23.129&token=oil-server-2024"
```

**响应示例**
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
                "change_98": 0.17,
                "change_0": 0.14,
                "adjust_date": "2026-07-23"
            }
        ]
    }
}
```

#### 1.3 查询全国油价

**请求**
```http
GET /api/oil?token={token}
```

**请求示例**
```bash
curl "http://localhost:5001/api/oil?token=oil-server-2024"
```

**响应示例**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "update_time": "2026-07-23",
        "source": "东方财富网",
        "province": "全国",
        "count": 31,
        "prices": [
            {
                "province": "北京",
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_0": 8.46,
                "change_92": 0.15,
                "change_95": 0.16,
                "change_0": 0.14
            },
            {
                "province": "上海",
                "oil_92": 8.65,
                "oil_95": 9.21,
                "oil_0": 8.39,
                "change_92": 0.15,
                "change_95": 0.16,
                "change_0": 0.14
            }
            // ... 更多省份
        ]
    }
}
```

---

### 2. 按省份路径查询

**请求**
```http
GET /api/oil/province/{省份名称}?token={token}
```

**参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 省份名称（路径参数） |
| token | string | 是 | API认证Token |

**请求示例**
```bash
# 查询北京油价
curl "http://localhost:5001/api/oil/province/北京?token=oil-server-2024"

# 查询广东油价
curl "http://localhost:5001/api/oil/province/广东?token=oil-server-2024"
```

**响应示例**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "update_time": "2026-07-23",
        "source": "东方财富网",
        "province": "北京",
        "prices": [
            {
                "province": "北京",
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_98": 10.28,
                "oil_0": 8.46,
                "change_92": 0.15,
                "change_95": 0.16,
                "change_98": 0.17,
                "change_0": 0.14,
                "adjust_date": "2026-07-23"
            }
        ]
    }
}
```

---

### 3. 油价预测

**请求**
```http
GET /api/oil/prediction?token={token}
```

**参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | API认证Token |

**请求示例**
```bash
curl "http://localhost:5001/api/oil/prediction?token=oil-server-2024"
```

**响应示例**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "status": "up",
        "forecast": "预计上调",
        "trend": "up",
        "trend_label": "预计上调",
        "confidence": 75,
        "change_rate": 7.5,
        "prediction_text": "预计下次调价窗口将上调油价",
        "next_window_date": "2026-08-05",
        "last_adjust_date": "2026-07-23",
        "last_gasoline_price": 8.72,
        "last_diesel_price": 8.46,
        "last_gasoline_change": 0.15,
        "last_diesel_change": 0.14,
        "predict_gasoline_change": 0.20,
        "predict_diesel_change": 0.18,
        "history": [
            {
                "date": "2026-07-23",
                "gasoline_price": 8.72,
                "diesel_price": 8.46,
                "gasoline_change": 0.15,
                "diesel_change": 0.14
            }
        ]
    }
}
```

**响应字段说明**
| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 预测状态：up（上调）、down（下调）、flat（持平）、unknown（待定） |
| forecast | string | 中文预测描述 |
| confidence | int | 置信度（0-100） |
| change_rate | float | 预测变化率 |
| next_window_date | string | 下次调价窗口日期 |
| predict_gasoline_change | float | 预测汽油变化金额 |
| predict_diesel_change | float | 预测柴油变化金额 |

---

### 4. 附近加油站查询

**请求**
```http
GET /api/station/nearby?longitude={经度}&latitude={纬度}&token={token}
```

**说明**
- 服务器配置了 `TENCENT_MAP_KEY` 时，返回腾讯地图**真实加油站 POI**（按距离排序，`data.source` 为 `tencent`）
- 未配置 Key 或 POI 请求失败时，自动回退到内置静态数据（`data.source` 为 `static`）
- POI 结果有 30 分钟缓存，且按坐标聚合，可降低地图配额消耗

**参数**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| longitude | float | 否 | 用户经度 |
| latitude | float | 否 | 用户纬度 |
| radius | int | 否 | 搜索半径（米，默认：5000，仅真实 POI 生效） |
| province | string | 否 | 省份筛选（仅静态数据生效） |
| city | string | 否 | 城市筛选（仅静态数据生效） |
| district | string | 否 | 区县筛选（仅静态数据生效） |
| page | int | 否 | 页码（默认：1） |
| limit | int | 否 | 每页数量（默认：20，最大：100） |
| token | string | 是 | API认证Token |

**请求示例**
```bash
# 查询北京朝阳区附近加油站
curl "http://localhost:5001/api/station/nearby?longitude=116.461&latitude=39.908&province=北京&token=oil-server-2024"

# 查询上海所有加油站
curl "http://localhost:5001/api/station/nearby?city=上海市&token=oil-server-2024"

# 分页查询
curl "http://localhost:5001/api/station/nearby?longitude=116.405&latitude=39.905&page=1&limit=10&token=oil-server-2024"
```

**响应示例**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "province": "北京",
        "city": "",
        "district": "",
        "total": 2,
        "stations": [
            {
                "id": 1,
                "name": "中国石化加油站（朝阳站）",
                "brand": "中石化",
                "address": "北京市朝阳区建国路88号",
                "province": "北京",
                "city": "北京市",
                "district": "朝阳区",
                "longitude": 116.461,
                "latitude": 39.908,
                "tel": "010-88886666",
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_0": 8.46,
                "distance": 1234
            },
            {
                "id": 2,
                "name": "中国石油加油站（海淀站）",
                "brand": "中石油",
                "address": "北京市海淀区中关村大街1号",
                "province": "北京",
                "city": "北京市",
                "district": "海淀区",
                "longitude": 116.310,
                "latitude": 39.984,
                "tel": "010-66668888",
                "oil_92": 8.72,
                "oil_95": 9.28,
                "oil_0": 8.46,
                "distance": 5678
            }
        ]
    }
}
```

**响应字段说明**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 加油站 ID |
| name | string | 加油站名称 |
| address | string | 加油站地址 |
| tel | string | 联系电话（可能为空） |
| longitude / latitude | float | 坐标（GCJ-02） |
| distance | int | 与用户位置的距离（米） |
| source | string | 数据来源（tencent / static） |

> 真实 POI 响应不包含油价字段（油价以 `/api/oil` 为准）；品牌信息可由前端根据名称匹配。

---

### 5. 健康检查

**请求**
```http
GET /api/health
```

**说明**
- 无需认证
- 用于监控服务状态

**请求示例**
```bash
curl "http://localhost:5001/api/health"
```

**响应示例**
```json
{
    "code": 0,
    "message": "ok",
    "timestamp": "2026-07-23 14:30:00"
}
```

---

## 错误响应

所有错误响应格式：
```json
{
    "code": 错误码,
    "message": "错误描述",
    "data": null
}
```

### 错误码说明

| 错误码 | HTTP状态码 | 说明 |
|--------|------------|------|
| 400 | 400 | 参数错误 |
| 401 | 401 | Token无效或缺失 |
| 404 | 404 | 数据不存在 |
| 500 | 500 | 服务器内部错误 |

### 常见错误示例

**Token无效**
```json
{
    "code": 401,
    "message": "无效的Token，请在请求头中添加 Authorization: Bearer <token> 或在URL中添加 token 参数",
    "data": null
}
```

**省份不存在**
```json
{
    "code": 404,
    "message": "未找到 [xxx] 的油价数据",
    "data": null
}
```

**经纬度无效**
```json
{
    "code": 400,
    "message": "无法根据经纬度确定省份，请检查坐标是否在中国境内",
    "data": null
}
```

---

## 数据源说明

| 数据源 | 说明 | 特点 |
|--------|------|------|
| all | 默认，依次尝试所有数据源 | 最全面 |
| eastmoney | 东方财富网 | 主要数据源 |
| abapi | abapi.cn | 补充98号汽油数据 |

---

## 缓存机制

- 油价数据缓存时间：2小时
- 缓存过期后自动重新获取
- 获取失败时返回缓存数据（如有）

---

## 调用频率限制

- 无明确限制，但建议：
  - 油价查询：每天10次以内（数据更新频率低）
  - 预测查询：每天5次以内
  - 加油站查询：按需调用

---

## 前端集成示例

### JavaScript (Fetch API)
```javascript
// 查询北京油价
const response = await fetch(
    'http://localhost:5001/api/oil?province=北京&token=oil-server-2024'
);
const data = await response.json();

if (data.code === 0) {
    console.log('油价数据:', data.data.prices);
} else {
    console.error('查询失败:', data.message);
}
```

### 通过GPS坐标查询
```javascript
// 获取用户位置
navigator.geolocation.getCurrentPosition(async (position) => {
    const { longitude, latitude } = position.coords;
    
    const response = await fetch(
        `http://localhost:5001/api/oil?longitude=${longitude}&latitude=${latitude}&token=oil-server-2024`
    );
    const data = await response.json();
    
    if (data.code === 0) {
        console.log(`您所在地区(${data.data.province})的油价:`, data.data.prices);
    }
});
```

### 微信小程序
```javascript
wx.getLocation({
    type: 'gcj02',
    success: async (res) => {
        const { longitude, latitude } = res;
        
        const response = await new Promise((resolve, reject) => {
            wx.request({
                url: 'http://localhost:5001/api/oil',
                data: {
                    longitude,
                    latitude,
                    token: 'oil-server-2024'
                },
                success: resolve,
                fail: reject
            });
        });
        
        if (response.data.code === 0) {
            console.log('当前省份:', response.data.data.province);
            console.log('油价:', response.data.data.prices);
        }
    }
});
```

---

## 部署配置

### 环境变量
```bash
# .env文件
API_TOKEN=your_custom_token_here
```

### Docker部署
```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f oil-server
```

### Nginx配置
```nginx
server {
    listen 80;
    server_name api.example.com;

    location /api/ {
        proxy_pass http://oil-server:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
