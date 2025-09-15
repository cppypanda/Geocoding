import math

def gcj02_to_wgs84(lng, lat):
    """
    GCJ02(火星坐标系)转GPS84
    """
    PI = 3.1415926535897932384626
    ee = 0.00669342162296594323
    a = 6378245.0
    
    if out_of_china(lng, lat):
        return [lng, lat]
        
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return [lng * 2 - mglng, lat * 2 - mglat]

def bd09_to_wgs84(lng, lat):
    """
    百度坐标系(BD-09)转WGS84
    """
    x_pi = 3.14159265358979324 * 3000.0 / 180.0
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    gg_lng = z * math.cos(theta)
    gg_lat = z * math.sin(theta)
    # GCJ02 to WGS84
    return gcj02_to_wgs84(gg_lng, gg_lat)

def out_of_china(lng, lat):
    """
    判断是否在国内，不在国内不做偏移
    """
    return not (lng > 73.66 and lng < 135.05 and lat > 3.86 and lat < 53.55)

def transform_lat(lng, lat):
    """
    GCJ02 纬度转换
    """
    PI = 3.1415926535897932384626
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + \
          0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * \
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 * \
            math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * \
            math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(lng, lat):
    """
    GCJ02 经度转换
    """
    PI = 3.1415926535897932384626
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + \
          0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * \
            math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 * \
            math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 * \
            math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    """
    WGS84转GCJ02(火星坐标系)
    """
    PI = 3.1415926535897932384626
    ee = 0.00669342162296594323
    a = 6378245.0
    
    if out_of_china(lng, lat):
        return [lng, lat]
        
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return [mglng, mglat]

def wgs84_to_bd09(lng, lat):
    """
    WGS84转百度坐标系(BD-09)
    """
    gcj02 = wgs84_to_gcj02(lng, lat)
    x = gcj02[0]
    y = gcj02[1]
    z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * math.pi)
    theta = math.atan2(y, x) + 0.000003 * math.cos(x * math.pi)
    bd_lng = z * math.cos(theta) + 0.0065
    bd_lat = z * math.sin(theta) + 0.006
    return [bd_lng, bd_lat]

def gcj02_to_bd09(lng, lat):
    """
    火星坐标系(GCJ-02)转百度坐标系(BD-09)
    """
    x_pi = 3.14159265358979324 * 3000.0 / 180.0
    x = lng
    y = lat
    z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) + 0.000003 * math.cos(x * x_pi)
    bd_lng = z * math.cos(theta) + 0.0065
    bd_lat = z * math.sin(theta) + 0.006
    return [bd_lng, bd_lat]

def coordinate_transform(lng, lat, from_sys, to_sys):
    """坐标系统转换
    支持的坐标系统：
    - WGS84: 世界大地测量系统
    - GCJ02: 国测局坐标系
    - BD09: 百度坐标系
    """
    if from_sys == to_sys:
        return lng, lat
        
    if from_sys == 'WGS84' and to_sys == 'GCJ02':
        return wgs84_to_gcj02(lng, lat)
    elif from_sys == 'GCJ02' and to_sys == 'WGS84':
        return gcj02_to_wgs84(lng, lat)
    elif from_sys == 'GCJ02' and to_sys == 'BD09':
        return gcj02_to_bd09(lng, lat)
    elif from_sys == 'BD09' and to_sys == 'GCJ02':
        # 百度转GCJ02，先转WGS84再转GCJ02
        wgs84 = bd09_to_wgs84(lng, lat)
        return wgs84_to_gcj02(wgs84[0], wgs84[1])
    elif from_sys == 'WGS84' and to_sys == 'BD09':
        gcj02 = wgs84_to_gcj02(lng, lat)
        return gcj02_to_bd09(*gcj02)
    elif from_sys == 'BD09' and to_sys == 'WGS84':
        # BD09转GCJ02
        x_pi = 3.14159265358979324 * 3000.0 / 180.0
        x = lng - 0.0065
        y = lat - 0.006
        z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
        theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
        gcj02_lng = z * math.cos(theta)
        gcj02_lat = z * math.sin(theta)
        # GCJ02转WGS84
        return gcj02_to_wgs84(gcj02_lng, gcj02_lat)
    else:
        raise ValueError(f'不支持的坐标系统转换: {from_sys} -> {to_sys}') 