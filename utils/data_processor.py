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
    
    def prepare_map_data(self, traffic_data):
        """
        为地图可视化准备数据
        
        参数:
            traffic_data: 包含交通数据的DataFrame
            
        返回:
            用于地图可视化的JSON格式数据
        """
        """修复地图数据生成逻辑"""
        if traffic_data.empty:
            return json.dumps({'type': 'FeatureCollection', 'features': []})
        
        features = []
        for _, row in traffic_data.iterrows():
            # 确保坐标顺序为 [经度, 纬度]
            # 获取路段ID
            road_id = row.get('segment_id') or row.get('id')
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [row['longitude'], row['latitude']]
                },
                'properties': {
                    'id': road_id,
                    'road_name': row['road_name'],
                    'district': row['district'],
                    'status': row['status'],
                    'congestion_index': float(row['congestion_index']),
                    'average_speed': float(row['average_speed']),
                    'color': self._get_color(row['congestion_index']),
                    'popupContent': f"""
                        <div class="road-popup">
                            <h5>{row['road_name']}</h5>
                            <p>区域: {row['district']}</p>
                            <p>拥堵指数: {row['congestion_index']:.2f}</p>
                            <p>状态: {row['status']}</p>
                            <p>平均车速: {row['average_speed']} km/h</p>
                            <a href="/road/{road_id}" class="btn btn-sm btn-primary mt-2">查看详情</a>
                        </div>
                    """
                }
            }
            features.append(feature)
        
        return json.dumps({'type': 'FeatureCollection', 'features': features})
    
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
            return json.dumps({})
        
        # 计算各种交通状态的数量
        status_counts = traffic_data['status'].value_counts().to_dict()
        
        # 计算平均拥堵指数
        avg_congestion = traffic_data['congestion_index'].mean()
        
        # 计算平均车速
        avg_speed = traffic_data['average_speed'].mean()
        
        # 按区域分组统计
        district_stats = traffic_data.groupby('district')['congestion_index'].mean().to_dict()
        
        # 统计总体信息
        statistics = {
            'status_counts': status_counts,
            'avg_congestion': float(avg_congestion),
            'avg_speed': float(avg_speed),
            'district_stats': {k: float(v) for k, v in district_stats.items()},
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