"""
交通数据处理工具
用于处理交通数据并为可视化和分析做准备
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

class TrafficDataProcessor:
    """交通数据处理类"""
    
    def __init__(self):
        """初始化数据处理器"""
        pass
    
    def prepare_map_data(self, df):
        """准备地图展示数据（GeoJSON格式）"""
        try:
            if df.empty:
                print("WARNING: 用于地图准备的数据为空")
                return json.dumps({'type': 'FeatureCollection', 'features': []})
            
            # 创建GeoJSON特征列表
            features = []
            
            for _, row in df.iterrows():
                try:
                    # 确保经纬度值有效
                    latitude = float(row.get('latitude', 0))
                    longitude = float(row.get('longitude', 0))
                    
                    if not latitude or not longitude or abs(latitude) > 90 or abs(longitude) > 180:
                        print(f"WARNING: 无效的地理坐标 lat={latitude}, lon={longitude}")
                        # 使用贵阳市中心坐标作为备用
                        latitude = 26.598194
                        longitude = 106.707410
                    
                    # 获取状态对应的颜色
                    status_color = '#28a745'  # 默认绿色
                    if 'status' in row:
                        if '严重' in row['status']:
                            status_color = '#dc3545'  # 红色
                        elif '中度' in row['status']:
                            status_color = '#ffc107'  # 黄色
                        elif '轻度' in row['status']:
                            status_color = '#17a2b8'  # 青色
                    
                    # 构建弹窗内容
                    popup_content = f"""
                    <div style='min-width: 180px;'>
                        <h6 style='margin-bottom: 5px; font-weight: bold;'>{row.get('road_name', 'N/A')}</h6>
                        <div style='font-size: 12px; color: #666;'>{row.get('district', 'N/A')}</div>
                        <hr style='margin: 5px 0;'>
                        <div style='display: flex; justify-content: space-between; margin-bottom: 5px;'>
                            <span>拥堵指数:</span>
                            <span style='font-weight: bold; color: {status_color};'>{row.get('congestion_index', 0):.2f}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between; margin-bottom: 5px;'>
                            <span>状态:</span>
                            <span style='font-weight: bold; color: {status_color};'>{row.get('status', 'N/A')}</span>
                        </div>
                        <div style='display: flex; justify-content: space-between;'>
                            <span>平均车速:</span>
                            <span>{row.get('average_speed', 0)} km/h</span>
                        </div>
                        <div style='margin-top: 8px;'>
                            <a href='/road/{row.get('segment_id', 0)}' 
                               style='display: block; text-align: center; padding: 4px; 
                                     background-color: #007bff; color: white; 
                                     text-decoration: none; border-radius: 4px;'>
                                查看详情
                            </a>
                        </div>
                    </div>
                    """
                    
                    # 构建特征
                    feature = {
                        'type': 'Feature',
                        'geometry': {
                            'type': 'Point',
                            'coordinates': [longitude, latitude]
                        },
                        'properties': {
                            'id': int(row.get('segment_id', 0)),
                            'road_name': row.get('road_name', 'N/A'),
                            'district': row.get('district', 'N/A'),
                            'congestion_index': float(row.get('congestion_index', 0)),
                            'status': row.get('status', 'N/A'),
                            'average_speed': float(row.get('average_speed', 0)),
                            'popupContent': popup_content
                        }
                    }
                    features.append(feature)
                except Exception as e:
                    print(f"处理地图特征时出错: {e}, 行数据: {row}")
                    continue
            
            # 构建GeoJSON
            geojson = {
                'type': 'FeatureCollection',
                'features': features
            }
            
            # 验证生成的GeoJSON
            if not features:
                print("WARNING: 未生成任何地图特征")
            else:
                print(f"INFO: 成功生成 {len(features)} 个地图特征")
            
            return json.dumps(geojson)
            
        except Exception as e:
            print(f"地图数据准备失败: {e}")
            # 返回空的GeoJSON
            return json.dumps({'type': 'FeatureCollection', 'features': []})
    
    def _get_color(self, congestion):
        """统一颜色分类逻辑"""
        if congestion < 0.4:
            return '#4CAF50'  # 绿色
        elif congestion < 0.6:
            return '#FFC107'  # 橙色
        else:
            return '#F44336'  # 红色
    
    def prepare_congestion_list(self, traffic_data, limit=10):
        """
        为拥堵路段列表准备数据
        
        参数:
            traffic_data: 包含交通数据的DataFrame
            limit: 返回的路段数量限制
            
        返回:
            拥堵路段列表的JSON格式数据
        """
        if traffic_data.empty:
            return json.dumps([])
        
        # 按拥堵指数排序
        sorted_data = traffic_data.sort_values('congestion_index', ascending=False)
        
        # 提取前N个拥堵路段
        top_congested = sorted_data.head(limit)
        
        congestion_list = []
        for _, row in top_congested.iterrows():
            # 获取路段ID，优先使用segment_id，如果没有则使用id
            road_id = row.get('segment_id', None) or row.get('id', None)
            
            congestion_list.append({
                'id': road_id,  # 确保包含ID信息
                'road_name': row['road_name'],
                'district': row['district'],
                'latitude': float(row['latitude']),
                'longitude': float(row['longitude']),
                'status': row['status'],
                'congestion_index': float(row['congestion_index']),
                'average_speed': float(row['average_speed']),
                'timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return json.dumps(congestion_list)
    
    def prepare_trend_data(self, historical_trend):
        """修复趋势数据格式"""
        # 确保输入数据是字典列表格式
        if not isinstance(historical_trend, list) or len(historical_trend) == 0:
            return json.dumps({'labels': [], 'datasets': []})
        
        # 转换时间格式
        processed_data = []
        for entry in historical_trend:
            if isinstance(entry, dict):  # 确保是字典类型
                processed_data.append({
                    'hour': entry.get('timestamp', '00:00').split(' ')[-1][:5],
                    'avg_congestion': float(entry.get('avg_congestion', 0))
                })
        
        return json.dumps({
            'labels': [t['hour'] for t in processed_data],
            'datasets': [{
                'label': '历史拥堵指数',
                'data': [t['avg_congestion'] for t in processed_data],
                'borderColor': '#4CAF50',
                'tension': 0.4
            }]
        })
        """
        为历史趋势折线图准备数据
        
        参数:
            historical_data: 包含历史数据的DataFrame
            
        返回:
            历史趋势的JSON格式数据
        """
        if historical_data.empty:
            return json.dumps({})
        
        # 确保数据按时间排序
        historical_data = historical_data.sort_values('hour_group')
        
        # 准备时间标签
        time_labels = [dt.strftime('%m-%d %H:00') for dt in historical_data['hour_group']]
        
        # 准备趋势数据
        trend_data = {
            'time_labels': time_labels,
            'congestion_index': historical_data['congestion_index'].tolist(),
            'traffic_flow': historical_data['traffic_flow'].tolist(),
            'average_speed': historical_data['average_speed'].tolist()
        }
        
        return json.dumps(trend_data)
    
    def prepare_statistics(self, traffic_data):
        """
        计算并准备交通统计数据
        
        参数:
            traffic_data: 包含交通数据的DataFrame
            
        返回:
            统计信息的JSON格式数据
        """
        if traffic_data.empty:
            # 返回默认值避免NaN
            return json.dumps({
                'status_counts': {'畅通': 0, '轻度拥堵': 0, '中度拥堵': 0, '严重拥堵': 0},
                'avg_congestion': 0.3,
                'avg_speed': 40.0,
                'district_stats': {},
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # 删除NaN值以避免计算问题
        clean_data = traffic_data.dropna(subset=['congestion_index', 'average_speed', 'status'])
        
        if clean_data.empty:
            # 如果清理后没有数据，返回默认值
            return json.dumps({
                'status_counts': {'畅通': 0, '轻度拥堵': 0, '中度拥堵': 0, '严重拥堵': 0},
                'avg_congestion': 0.3,
                'avg_speed': 40.0,
                'district_stats': {},
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # 计算各种交通状态的数量
        status_counts = clean_data['status'].value_counts().to_dict()
        
        # 计算平均拥堵指数，确保是有效值
        avg_congestion = clean_data['congestion_index'].mean()
        if pd.isna(avg_congestion):
            avg_congestion = 0.3  # 默认值
        
        # 计算平均车速，确保是有效值
        avg_speed = clean_data['average_speed'].mean()
        if pd.isna(avg_speed):
            avg_speed = 40.0  # 默认值
        
        # 按区域分组统计
        district_stats = {}
        try:
            district_group = clean_data.groupby('district')['congestion_index'].mean()
            district_stats = {k: float(v) if not pd.isna(v) else 0.3 for k, v in district_group.to_dict().items()}
            
            # 添加区域的详细统计信息
            district_detailed_stats = {}
            for district, group in clean_data.groupby('district'):
                severe_count = group[group['congestion_index'] >= 0.7].shape[0]
                moderate_count = group[(group['congestion_index'] >= 0.4) & (group['congestion_index'] < 0.7)].shape[0]
                free_count = group[group['congestion_index'] < 0.4].shape[0]
                
                avg_speed_district = group['average_speed'].mean()
                if pd.isna(avg_speed_district):
                    avg_speed_district = 35.0  # 默认值
                
                district_detailed_stats[district] = {
                    'avg_congestion': float(district_stats.get(district, 0.3)),
                    'avg_speed': float(avg_speed_district),
                    'road_count': group.shape[0],
                    'severe_count': severe_count,
                    'moderate_count': moderate_count,
                    'free_count': free_count,
                    'status_distribution': {
                        '畅通': int(group[group['status'] == '畅通'].shape[0]),
                        '轻度拥堵': int(group[group['status'] == '轻度拥堵'].shape[0]),
                        '中度拥堵': int(group[group['status'] == '中度拥堵'].shape[0]),
                        '严重拥堵': int(group[group['status'] == '严重拥堵'].shape[0])
                    }
                }
            
            # 将详细统计信息添加到district_stats
            district_stats = {
                'avg_by_district': district_stats,
                'detailed': district_detailed_stats
            }
            
        except Exception as e:
            print(f"区域统计计算错误: {e}")
        
        # 统计总体信息
        statistics = {
            'status_counts': status_counts,
            'avg_congestion': float(avg_congestion),
            'avg_speed': float(avg_speed),
            'district_stats': district_stats,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return json.dumps(statistics)
    
    def prepare_alert_data(self, traffic_data, threshold=0.8):
        """
        准备需要发送警报的交通数据
        
        参数:
            traffic_data: 包含交通数据的DataFrame
            threshold: 触发警报的拥堵指数阈值
            
        返回:
            警报数据的JSON格式
        """
        if traffic_data.empty:
            return json.dumps([])
        
        # 筛选出需要警报的路段
        alert_data = traffic_data[traffic_data['congestion_index'] >= threshold]
        
        alerts = []
        for _, row in alert_data.iterrows():
            alerts.append({
                'road_name': row['road_name'],
                'district': row['district'],
                'congestion_index': float(row['congestion_index']),
                'status': row['status'],
                'timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                'message': f"严重拥堵警报: {row['district']} {row['road_name']} 当前拥堵指数 {row['congestion_index']:.2f}",
                'level': 'danger' if row['congestion_index'] >= 0.9 else 'warning'
            })
        
        return json.dumps(alerts)

    def prepare_district_analysis(self, traffic_data, district_name=None):
        """
        生成特定区域的交通分析数据
        
        参数:
            traffic_data: 包含交通数据的DataFrame
            district_name: 区域名称，如果为None则分析所有区域
            
        返回:
            区域分析的JSON格式数据
        """
        if traffic_data.empty:
            return json.dumps({
                'district_name': district_name or '全市',
                'avg_congestion': 0.3,
                'avg_speed': 40.0,
                'road_count': 0,
                'congested_roads': [],
                'hourly_pattern': [],
                'top_congested_roads': []
            })
        
        # 筛选特定区域的数据，如果district_name为None则使用所有数据
        if district_name:
            district_data = traffic_data[traffic_data['district'] == district_name]
            if district_data.empty:
                return json.dumps({
                    'district_name': district_name,
                    'avg_congestion': 0.3,
                    'avg_speed': 40.0,
                    'road_count': 0,
                    'congested_roads': [],
                    'hourly_pattern': [],
                    'top_congested_roads': []
                })
        else:
            district_data = traffic_data
        
        # 计算基本统计数据
        avg_congestion = district_data['congestion_index'].mean()
        avg_speed = district_data['average_speed'].mean()
        road_count = district_data.shape[0]
        
        # 筛选拥堵路段
        congested_roads = district_data[district_data['congestion_index'] >= 0.6]
        
        # 生成模拟的小时模式数据（实际应用中可从历史数据获取）
        current_hour = datetime.now().hour
        hourly_pattern = []
        for hour in range(24):
            if 7 <= hour <= 9:  # 早高峰
                base_congestion = 0.7
            elif 17 <= hour <= 19:  # 晚高峰
                base_congestion = 0.8
            elif 10 <= hour <= 16:  # 工作时间
                base_congestion = 0.5
            else:  # 夜间和凌晨
                base_congestion = 0.3
            
            # 添加时间点数据，当前小时数据使用实际平均值
            if hour == current_hour:
                hourly_pattern.append({
                    'hour': f"{hour}:00",
                    'congestion': float(avg_congestion),
                    'is_current': True
                })
            else:
                # 为非当前小时添加随机波动
                congestion_with_noise = base_congestion + (np.random.random() * 0.2 - 0.1)
                hourly_pattern.append({
                    'hour': f"{hour}:00",
                    'congestion': float(min(0.95, max(0.1, congestion_with_noise))),
                    'is_current': False
                })
        
        # 获取拥堵最严重的前10条道路
        top_congested = district_data.sort_values('congestion_index', ascending=False).head(10)
        top_congested_list = []
        
        for _, road in top_congested.iterrows():
            road_id = road.get('segment_id') or road.get('id')
            top_congested_list.append({
                'id': int(road_id) if road_id is not None else 0,
                'road_name': road['road_name'],
                'congestion_index': float(road['congestion_index']),
                'status': road['status'],
                'average_speed': float(road['average_speed']),
                'latitude': float(road['latitude']),
                'longitude': float(road['longitude'])
            })
        
        # 准备响应数据
        district_analysis = {
            'district_name': district_name or '全市',
            'avg_congestion': float(avg_congestion),
            'avg_speed': float(avg_speed),
            'road_count': int(road_count),
            'congested_count': int(congested_roads.shape[0]),
            'congestion_percent': float(congested_roads.shape[0] / max(1, road_count)),
            'status_distribution': {
                '畅通': int(district_data[district_data['status'] == '畅通'].shape[0]),
                '轻度拥堵': int(district_data[district_data['status'] == '轻度拥堵'].shape[0]),
                '中度拥堵': int(district_data[district_data['status'] == '中度拥堵'].shape[0]),
                '严重拥堵': int(district_data[district_data['status'] == '严重拥堵'].shape[0])
            },
            'hourly_pattern': hourly_pattern,
            'top_congested_roads': top_congested_list
        }
        
        return json.dumps(district_analysis)

# 测试代码
if __name__ == "__main__":
    # 创建一些模拟数据进行测试
    from data_generator import TrafficDataGenerator
    
    generator = TrafficDataGenerator(num_road_segments=10)
    processor = TrafficDataProcessor()
    
    # 获取实时数据
    real_time_data = generator.get_real_time_data()
    
    # 测试地图数据处理
    map_data = processor.prepare_map_data(real_time_data)
    print("地图数据示例:")
    print(map_data[:200] + "...")  # 只显示前200个字符
    
    # 测试拥堵列表处理
    congestion_list = processor.prepare_congestion_list(real_time_data)
    print("\n拥堵列表示例:")
    print(congestion_list[:200] + "...")
    
    # 测试历史趋势数据处理
    historical_data = generator.get_historical_trend()
    trend_data = processor.prepare_trend_data(historical_data)
    print("\n趋势数据示例:")
    print(trend_data[:200] + "...")