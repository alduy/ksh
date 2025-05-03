"""
贵阳市交通拥堵监测系统 - 主应用
"""
# 确保在文件顶部正确导入

import os
import json
import time
from datetime import datetime, timedelta
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # Add this import
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import pandas as pd
import numpy as np

# 导入自定义模块
from utils.data_generator import TrafficDataGenerator
from utils.data_processor import TrafficDataProcessor
from models.predictor import TrafficPredictor
import config

import logging

# 创建Flask应用
# 在文件顶部添加（约第21行）
def create_app():
    app = Flask(__name__)
    app.config.from_object(config)
    
    # 初始化组件
    with app.app_context():
        global data_generator, data_processor, predictor
        data_generator = TrafficDataGenerator(num_road_segments=config.NUM_ROAD_SEGMENTS)
        data_processor = TrafficDataProcessor()
        predictor = TrafficPredictor()
    
    return app

# 初始化应用
app = create_app()
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局变量
data_generator = None
data_processor = None
predictor = None
current_traffic_data = pd.DataFrame()
last_update_time = datetime.now()
data_lock = threading.Lock()

# 用于安全序列化JSON数据的辅助函数
def safe_json_dumps(data, ensure_ascii=True, **kwargs):
    """安全的JSON序列化方法，使用data_processor的方法或回退到基本方法"""
    if data_processor and hasattr(data_processor, 'safe_json_dumps'):
        return data_processor.safe_json_dumps(data, ensure_ascii=ensure_ascii, **kwargs)
    try:
        return json.dumps(data, ensure_ascii=ensure_ascii, **kwargs)
    except (TypeError, OverflowError) as e:
        print(f"JSON序列化警告: {e}")
        # 基本转换（针对简单类型）
        if isinstance(data, datetime):
            return json.dumps(data.strftime('%Y-%m-%d %H:%M:%S'), ensure_ascii=ensure_ascii, **kwargs)
        return json.dumps(str(data), ensure_ascii=ensure_ascii, **kwargs)

# 初始化全局变量
def init_data():
    """初始化数据"""
    global current_traffic_data, data_generator, data_processor, predictor, last_update_time
    
    # 如果全局变量未初始化，则初始化它们
    if data_generator is None:
        data_generator = TrafficDataGenerator(num_road_segments=config.NUM_ROAD_SEGMENTS)
    
    if data_processor is None:
        data_processor = TrafficDataProcessor()
    
    if predictor is None:
        predictor = TrafficPredictor()
    
    # 生成初始数据
    if current_traffic_data.empty:
        with data_lock:
            current_traffic_data = data_generator.get_real_time_data()
            last_update_time = datetime.now()

# 确保应用启动前数据已初始化
init_data()

# 添加全局错误处理
@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_message="服务器内部错误", error_detail=str(e)), 500

@app.route('/')
def dashboard():
    """实时监控仪表板页面"""
    # 获取当前实时数据
    global current_traffic_data
    if current_traffic_data.empty:
        current_traffic_data = data_generator.get_real_time_data()
        print(f"初始化数据: 获取了 {len(current_traffic_data)} 条路段数据")
    
    # 确保数据具有必要的字段 - 修复road_id字段相关问题
    if 'segment_id' in current_traffic_data.columns and 'road_id' not in current_traffic_data.columns:
        # 添加road_id字段，确保与前端兼容
        current_traffic_data['road_id'] = current_traffic_data['segment_id']
    
    # 准备地图数据
    map_data = data_processor.prepare_map_data(current_traffic_data)
    # 检查是否为空或有效的JSON
    try:
        map_data_json = json.loads(map_data)
        road_count = 0
        if isinstance(map_data_json, list):
            road_count = len(map_data_json)
        elif isinstance(map_data_json, dict) and 'features' in map_data_json:
            road_count = len(map_data_json['features'])
        print(f"地图数据准备完成: {road_count} 条路段")
    except Exception as e:
        print(f"地图数据解析错误: {str(e)}")
        map_data = '[]'  # 默认空数组
    
    # 准备拥堵路段列表 - 确保生成有效的JSON数据
    try:
        # 尝试直接使用JSON字符串
        congestion_list_str = data_processor.prepare_congestion_list(current_traffic_data)
        # 解析并处理确保每个路段都有id字段
        congestion_list_data = json.loads(congestion_list_str)
        
        # 确保每个路段都有road_id和id字段
        if isinstance(congestion_list_data, list):
            for item in congestion_list_data:
                # 确保id字段存在
                if 'id' not in item:
                    if 'road_id' in item:
                        item['id'] = item['road_id']
                    elif 'segment_id' in item:
                        item['id'] = item['segment_id']
                # 确保road_id字段存在
                if 'road_id' not in item and 'segment_id' in item:
                    item['road_id'] = item['segment_id']
        
        # 重新序列化为JSON字符串
        congestion_list = json.dumps(congestion_list_data)
        print(f"拥堵路段列表准备完成，共{len(congestion_list_data)}条数据")
    except Exception as e:
        print(f"拥堵路段列表准备失败: {str(e)}")
        congestion_list = '[]'  # 默认空数组
    
    # 准备警报数据
    try:
        alerts = json.loads(data_processor.prepare_alert_data(current_traffic_data))
    except Exception as e:
        print(f"警报数据准备失败: {str(e)}")
        alerts = []
    
    # 准备趋势数据 - 确保变量已初始化
    try:
        trend_data = data_processor.prepare_trend_data([]) if hasattr(data_processor, 'prepare_trend_data') else safe_json_dumps({'labels': [], 'datasets': []})
    except Exception as e:
        print(f"趋势数据准备失败: {str(e)}")
        trend_data = safe_json_dumps({'labels': [], 'datasets': []})
    
    # 准备统计数据 - 确保变量已初始化
    try:
        stats_json = data_processor.prepare_statistics(current_traffic_data)
        stats = json.loads(stats_json)
        print(f"统计数据: 路段数={len(current_traffic_data)}, 拥堵指数={stats.get('avg_congestion', 0)}, 车速={stats.get('avg_speed', 0)}")
    except Exception as e:
        print(f"统计数据准备失败: {str(e)}")
        stats = {'avg_congestion': 0, 'avg_speed': 0}

    return render_template('dashboard.html',
                        active_page='dashboard',
                        map_data=map_data,  # 直接传递原始JSON字符串
                        congested_roads=congestion_list,
                        alerts=alerts if alerts else [],  # 确保传递空列表而不是None
                        trend_data=trend_data,  # 已确保初始化
                        current_time=last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                        avg_congestion=round(stats.get('avg_congestion', 0), 2),
                        avg_speed=round(stats.get('avg_speed', 0), 1),
                        road_count=len(current_traffic_data),
                        heavy_congestion_count=len(alerts),
                        center_lat=config.GUIYANG_CENTER[0],
                        center_lng=config.GUIYANG_CENTER[1],
                        zoom=config.DEFAULT_ZOOM,
                        config=config)  # 传递配置到模板

@app.route('/analysis')
def analysis():
    """数据分析页面"""
    # 获取趋势数据和区域统计数据
    trend_data = data_processor.get_trend_data()
    district_stats = data_processor.get_district_stats()
    
    return render_template('analysis.html',
                         active_page='analysis',
                         trend_labels=[t['time'] for t in trend_data],
                         trend_data=[t['value'] for t in trend_data],
                         district_names=[d['name'] for d in district_stats],
                         district_values=[d['value'] for d in district_stats])

@app.route('/district_analysis')
def district_analysis():
    """区域分析页面"""
    global current_traffic_data
    
    # 添加空数据保护
    if current_traffic_data.empty:
        with data_lock:
            current_traffic_data = data_generator.get_real_time_data()
            # 确保数据具有必要的字段
            if 'segment_id' in current_traffic_data.columns and 'road_id' not in current_traffic_data.columns:
                # 添加road_id字段，确保与前端兼容
                current_traffic_data['road_id'] = current_traffic_data['segment_id']
            
    # 提取各区域的数据
    district_overviews = []
    districts = current_traffic_data['district'].unique()
    
    for district in districts:
        district_data = current_traffic_data[current_traffic_data['district'] == district]
        
        # 计算区域统计数据
        if not district_data.empty:
            avg_congestion = district_data['congestion_index'].mean()
            avg_speed = district_data['average_speed'].mean()
            road_count = district_data.shape[0]
            
            # 统计不同拥堵状态的道路数量
            status_counts = district_data['status'].value_counts()
            severe_count = status_counts.get('严重拥堵', 0)
            moderate_count = status_counts.get('中度拥堵', 0) + status_counts.get('轻度拥堵', 0)
            free_count = status_counts.get('畅通', 0)
            
            # 获取区域内拥堵最严重的前5条道路
            top_roads = district_data.sort_values('congestion_index', ascending=False).head(5).to_dict('records')
            
            # 确保每条路段记录都有id和road_id字段
            for road in top_roads:
                if 'segment_id' in road and 'road_id' not in road:
                    road['road_id'] = road['segment_id']
                elif 'road_id' in road and 'segment_id' not in road:
                    road['segment_id'] = road['road_id']
                
                # 如果两个ID都不存在，创建一个默认ID
                if 'road_id' not in road and 'segment_id' not in road:
                    road['road_id'] = f"road_{top_roads.index(road)}"
                
                # 确保前端使用的id字段存在
                if 'id' not in road:
                    road['id'] = road.get('road_id', road.get('segment_id', f"road_{top_roads.index(road)}"))
            
            # 获取区域小时拥堵趋势
            hourly_pattern = []
            current_hour = datetime.now().hour
            for hour in range(24):
                is_current = (hour == current_hour)
                congestion_val = avg_congestion
                
                # 模拟不同时间段的拥堵趋势
                if 7 <= hour <= 9:  # 早高峰
                    congestion_val = min(0.95, avg_congestion * (1.2 + 0.1 * np.random.random()))
                elif 17 <= hour <= 19:  # 晚高峰
                    congestion_val = min(0.95, avg_congestion * (1.3 + 0.1 * np.random.random()))
                elif 11 <= hour <= 14:  # 中午
                    congestion_val = avg_congestion * (1 + 0.05 * np.random.random())
                elif 22 <= hour or hour <= 5:  # 夜间
                    congestion_val = max(0.1, avg_congestion * (0.7 - 0.1 * np.random.random()))
                else:  # 其他时段
                    congestion_val = avg_congestion
                
                hourly_pattern.append({
                    'hour': f"{hour:02d}:00",
                    'congestion': float(congestion_val),
                    'is_current': is_current
                })
        else:
            # 默认空数据
            avg_congestion = 0.3
            avg_speed = 30.0
            road_count = 0
            severe_count = 0
            moderate_count = 0
            free_count = 0
            top_roads = []
            hourly_pattern = []
        
        # 计算每种状态的百分比
        status_percent = {}
        total_roads = severe_count + moderate_count + free_count
        for status, count in [('严重拥堵', severe_count), ('中度拥堵', moderate_count), ('畅通', free_count)]:
            status_percent[status] = round(count / max(1, total_roads) * 100, 1)
            
        district_overviews.append({
                'name': district,
                'avg_congestion': round(avg_congestion, 2),
                'avg_speed': round(avg_speed, 1),
                'road_count': road_count,
                'severe_count': severe_count,
                'moderate_count': moderate_count,
                'free_count': free_count,
                'status_percent': status_percent,
                'top_roads': top_roads,  # 添加拥堵最严重的道路列表
                'hourly_pattern': hourly_pattern  # 添加小时拥堵趋势
            })
    
    # 按拥堵程度排序
    district_overviews.sort(key=lambda x: x['avg_congestion'], reverse=True)
    
    # 空数据保护（添加默认数据）
    if not district_overviews:
        district_overviews.append({
            'name': '数据加载中',
            'avg_congestion': 0.3,
            'status_percent': {'畅通': 100},
            'top_roads': [],
            'hourly_pattern': []
        })

    # 计算未来预测数据（如果预测模型已训练）
    future_predictions = []
    if hasattr(predictor, 'is_trained') and predictor.is_trained and not current_traffic_data.empty:
        try:
            # 生成未来预测数据
            prediction_df = predictor.predict_future(current_traffic_data, hours_ahead=3)
            
            # 按小时分组
            grouped = prediction_df.groupby(pd.Grouper(key='timestamp', freq='H'))
            
            for group_time, group_data in grouped:
                hour_data = {
                    'timestamp': group_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'avg_congestion': group_data['congestion_index'].mean(),
                    'congested_count': group_data.loc[group_data['congestion_index'] >= 0.6].shape[0],
                    'status_counts': group_data['status'].value_counts(dropna=False).to_dict()
                }
                future_predictions.append(hour_data)
                
        except Exception as e:
            print(f"预测数据生成失败: {e}")
            
    return render_template(
        'district_analysis.html',
        active_page='district_analysis',
        districts=district_overviews,
        predictions=future_predictions,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/district/<district_name>')
def district_detail(district_name):
    """显示特定区域的详细信息页面"""
    global current_traffic_data
    
    # 添加空数据保护
    if current_traffic_data.empty:
        with data_lock:
            current_traffic_data = data_generator.get_real_time_data()
            # 确保数据具有必要的字段
            if 'segment_id' in current_traffic_data.columns and 'road_id' not in current_traffic_data.columns:
                # 添加road_id字段，确保与前端兼容
                current_traffic_data['road_id'] = current_traffic_data['segment_id']
    
    # 确保数据处理器已初始化
    if not hasattr(data_processor, 'prepare_district_analysis'):
        data_processor.prepare_district_analysis = lambda df, name: safe_json_dumps({})  # 临时空数据
    
    # 如果没有数据，生成一些数据
    if current_traffic_data.empty:
        with data_lock:
            data_generator.generate_data()
            current_traffic_data = data_generator.get_real_time_data()
            # 确保数据具有必要的字段
            if 'segment_id' in current_traffic_data.columns and 'road_id' not in current_traffic_data.columns:
                # 添加road_id字段，确保与前端兼容
                current_traffic_data['road_id'] = current_traffic_data['segment_id']
    
    # 获取特定区域的详细分析
    district_analysis_json = data_processor.prepare_district_analysis(current_traffic_data, district_name)
    district_data = json.loads(district_analysis_json)
    
    # 将区域内的交通数据筛选出来，防止数据为空
    district_traffic = current_traffic_data[current_traffic_data['district'] == district_name]
    
    # 确保district_data包含必要的字段，如果为空则初始化
    if 'avg_congestion' not in district_data or district_data['avg_congestion'] == 0:
        # 计算并设置平均拥堵指数
        avg_congestion = district_traffic['congestion_index'].mean() if not district_traffic.empty else 0.3
        district_data['avg_congestion'] = float(avg_congestion) if not pd.isna(avg_congestion) else 0.3
    
    if 'avg_speed' not in district_data or district_data['avg_speed'] == 0:
        # 计算并设置平均车速
        avg_speed = district_traffic['average_speed'].mean() if not district_traffic.empty else 30.0
        district_data['avg_speed'] = float(avg_speed) if not pd.isna(avg_speed) else 30.0
    
    if 'road_count' not in district_data or district_data['road_count'] == 0:
        # 设置道路总数
        district_data['road_count'] = len(district_traffic) if not district_traffic.empty else 0
    
    if 'congested_count' not in district_data:
        # 计算拥堵路段数量
        congested_count = len(district_traffic[district_traffic['congestion_index'] >= 0.4]) if not district_traffic.empty else 0
        district_data['congested_count'] = congested_count
    
    if 'congestion_percent' not in district_data:
        # 计算拥堵率
        congestion_percent = congested_count / max(1, len(district_traffic)) if not district_traffic.empty else 0
        district_data['congestion_percent'] = congestion_percent
    
    if 'status_distribution' not in district_data:
        # 计算状态分布
        status_counts = district_traffic['status'].value_counts().to_dict() if not district_traffic.empty else {}
        district_data['status_distribution'] = status_counts
    
    if 'top_congested_roads' not in district_data or not district_data['top_congested_roads']:
        # 获取拥堵最严重的路段
        top_roads = district_traffic.sort_values('congestion_index', ascending=False).head(5).to_dict('records') if not district_traffic.empty else []
        district_data['top_congested_roads'] = top_roads
    
    # 设置区域状态颜色和描述
    if 'status_color' not in district_data:
        avg_congestion = district_data['avg_congestion']
        if avg_congestion >= 0.7:
            district_data['status_color'] = '#dc3545'  # 红色
            district_data['status'] = '严重拥堵'
            district_data['status_description'] = '该区域当前交通状况非常拥堵，建议避开'
        elif avg_congestion >= 0.4:
            district_data['status_color'] = '#ffc107'  # 黄色
            district_data['status'] = '中度拥堵'
            district_data['status_description'] = '该区域当前交通状况较为拥堵，谨慎前往'
        else:
            district_data['status_color'] = '#28a745'  # 绿色
            district_data['status'] = '交通畅通'
            district_data['status_description'] = '该区域当前交通状况良好，可以正常出行'
    
    # 准备地图数据
    map_data_json = data_processor.prepare_map_data(district_traffic)
    
    # 将地图数据添加到 district_data 字典中（先解析为Python对象）
    district_data['map_data'] = json.loads(map_data_json)
    
    # 添加地图中心点和缩放级别
    district_data['center_lat'] = district_traffic['latitude'].mean() if not district_traffic.empty else 26.598194
    district_data['center_lng'] = district_traffic['longitude'].mean() if not district_traffic.empty else 106.707410
    district_data['zoom_level'] = 13
    
    # 确保district_name字段存在
    district_data['district_name'] = district_name
    
    # 调试输出
    print(f"区域详情数据: {district_name}, 拥堵指数={district_data.get('avg_congestion', 0)}, 道路数={district_data.get('road_count', 0)}")
    
    return render_template(
        'district_detail.html',
        active_page='district_analysis',
        district=district_data,
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/api/district/<district_name>')
def api_district_data(district_name):
    """获取特定区域的交通数据API"""
    try:
        # 获取实时交通数据
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，则生成新数据
        if current_data.empty:
            data_generator.generate_data()
            current_data = data_generator.get_real_time_data()
        
        # 根据区域名称筛选数据并生成区域分析数据
        district_data = json.loads(data_processor.prepare_district_analysis(current_data, district_name))
        
        return jsonify(district_data)
    except Exception as e:
        print(f"获取区域数据出错: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/district/<district_name>/prediction')
def api_district_prediction(district_name):
    """获取指定区域的预测数据API"""
    try:
        # 查找指定区域的数据
        district_data = current_traffic_data[current_traffic_data['district'] == district_name]
        
        if district_data.empty:
            return jsonify({
                'error': '未找到指定区域的数据',
                'predictions': []
            })
        
        # 获取当前平均拥堵指数
        current_congestion = district_data['congestion_index'].mean()
        if pd.isna(current_congestion):
            current_congestion = 0.3  # 默认值
        
        # 模拟路段数据用于生成建议
        congested_segments = district_data[district_data['congestion_index'] >= 0.6]
        worst_segments = congested_segments.sort_values('congestion_index', ascending=False).head(3)
        
        # 生成预测数据
        now = datetime.now()
        time_points = []
        predictions = []
        
        # 当前时间点
        time_points.append(now.strftime('%H:%M'))
        predictions.append(current_congestion)
        
        # 未来几个小时
        for i in range(1, 6):
            future_time = now + timedelta(hours=i)
            hour = future_time.hour
            
            # 基于时间段调整预测值
            if 7 <= hour <= 9:  # 早高峰
                future_value = min(0.9, current_congestion * 1.2)
            elif 17 <= hour <= 19:  # 晚高峰
                future_value = min(0.9, current_congestion * 1.3)
            elif 22 <= hour or hour <= 5:  # 夜间
                future_value = max(0.1, current_congestion * 0.7)
            else:  # 其他时段
                future_value = current_congestion
            
            # 添加随机波动
            np.random.seed(int(now.timestamp()) + i)
            future_value = max(0.1, min(0.95, future_value + (np.random.random() * 0.1 - 0.05)))
            
            time_points.append(future_time.strftime('%H:%M'))
            predictions.append(float(future_value))
        
        # 生成建议
        advice = generate_travel_advice(district_name, current_congestion, predictions, district_data)
        
        return jsonify({
            'district': district_name,
            'current_congestion': float(current_congestion),
            'time_points': time_points,
            'predictions': predictions,
            'advice': advice,
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    except Exception as e:
        print(f"区域预测API错误: {str(e)}")
        return jsonify({
            'error': str(e),
            'predictions': []
        })

@app.route('/api/prediction')
def api_prediction():
    """获取全局预测数据的API端点"""
    try:
        # 获取实时交通数据作为基础
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，则生成新数据
        if current_data.empty:
            data_generator.generate_data()
            current_data = data_generator.get_real_time_data()
        
        # 准备未来3小时的预测数据
        now = datetime.now()
        predictions = []
        
        # 计算当前平均拥堵指数作为基准
        current_avg_congestion = current_data['congestion_index'].mean()
        if pd.isna(current_avg_congestion) or current_avg_congestion <= 0:
            current_avg_congestion = 0.4  # 使用默认值
        
        # 对未来3小时进行预测
        for i in range(3):
            future_time = now + timedelta(hours=i+1)
            hour = future_time.hour
            
            # 基于时间段调整预测值
            if 7 <= hour <= 9:  # 早高峰
                prediction_value = min(0.95, current_avg_congestion * 1.2)
            elif 17 <= hour <= 19:  # 晚高峰
                prediction_value = min(0.95, current_avg_congestion * 1.3)
            elif 22 <= hour or hour <= 5:  # 夜间
                prediction_value = max(0.1, current_avg_congestion * 0.7)
            else:  # 其他时段
                prediction_value = current_avg_congestion
            
            # 增加一些随机变化
            np.random.seed(int(now.timestamp()) + i)
            prediction_value = max(0.1, min(0.95, prediction_value + (np.random.random() * 0.1 - 0.05)))
            
            # 根据拥堵指数确定状态
            if prediction_value < 0.4:
                status = '畅通'
            elif prediction_value < 0.6:
                status = '轻度拥堵'
            elif prediction_value < 0.8:
                status = '中度拥堵'
            else:
                status = '严重拥堵'
            
            # 计算路段状态分布 - 基于当前分布并稍做调整
            status_counts = {'畅通': 0, '轻度拥堵': 0, '中度拥堵': 0, '严重拥堵': 0}
            
            # 计算当前路段状态分布
            current_status_counts = current_data['status'].value_counts().to_dict()
            
            # 根据预测拥堵指数调整分布
            for status_name, count in current_status_counts.items():
                factor = 1.0
                if prediction_value < 0.4:  # 畅通时期
                    if status_name == '畅通':
                        factor = 1.2
                    else:
                        factor = 0.8
                elif prediction_value >= 0.7:  # 拥堵时期
                    if status_name == '严重拥堵' or status_name == '中度拥堵':
                        factor = 1.2
                    else:
                        factor = 0.8
                
                # 确保key存在于status_counts中
                if status_name in status_counts:
                    status_counts[status_name] = int(count * factor)
                else:
                    # 如果遇到其他状态名称，映射到最接近的标准状态
                    if '畅通' in status_name or '流畅' in status_name:
                        status_counts['畅通'] += int(count * factor)
                    elif '轻' in status_name:
                        status_counts['轻度拥堵'] += int(count * factor)
                    elif '中' in status_name:
                        status_counts['中度拥堵'] += int(count * factor)
                    elif '严' in status_name or '重' in status_name:
                        status_counts['严重拥堵'] += int(count * factor)
                    else:
                        # 默认分配
                        status_counts['轻度拥堵'] += int(count * factor)
            
            # 确保至少有一些路段在每个状态
            min_count = 1
            for key in status_counts:
                status_counts[key] = max(min_count, status_counts[key])
            
            # 计算拥堵路段数（非畅通的路段）
            congested_count = sum(count for status_name, count in status_counts.items() if status_name != '畅通')
            
            # 构建预测数据项
            prediction = {
                'timestamp': future_time.strftime('%Y-%m-%d %H:%M'),
                'hour': future_time.hour,
                'avg_congestion': float(prediction_value),
                'status': status,
                'congested_count': congested_count,
                'status_counts': status_counts
            }
            
            predictions.append(prediction)
        
        # 返回JSON格式的预测数据
        return jsonify({
            'current_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'predictions': predictions,
            'avg_congestion': float(current_avg_congestion)
        })
        
    except Exception as e:
        print(f"预测数据API错误: {str(e)}")
        return jsonify({
            'error': str(e),
            'predictions': []
        })

def get_congestion_status(congestion_value):
    """根据拥堵指数获取状态描述"""
    if congestion_value >= 0.7:
        return {
            "status": "严重拥堵",
            "color": "#dc3545",
            "description": "该区域当前交通状况非常拥堵，建议避开"
        }
    elif congestion_value >= 0.4:
        return {
            "status": "中度拥堵",
            "color": "#ffc107",
            "description": "该区域当前交通状况较为拥堵，谨慎前往"
        }
    else:
        return {
            "status": "交通畅通",
            "color": "#28a745",
            "description": "该区域当前交通状况良好，可以正常出行"
        }

def generate_travel_advice(district_name, current_congestion, predictions, district_data):
    """根据预测结果生成出行建议"""
    now = datetime.now()
    hour = now.hour
    
    # 确定最佳出行时间
    if hour < 7 or hour > 19:
        best_time = "今日 10:00 - 16:00"
    elif hour >= 7 and hour < 10:
        best_time = "今日 14:00 - 16:00"
    elif hour >= 16 and hour < 19:
        best_time = "今日 20:00 后或明日 10:00 - 16:00"
    else:
        best_time = "当前时段或今日 10:00 - 16:00"
    
    # 获取最拥堵的道路
    worst_roads = []
    try:
        # 验证district_data是否为DataFrame
        if isinstance(district_data, pd.DataFrame) and not district_data.empty:
            # 检查必要列是否存在
            required_columns = ['road_name', 'congestion_index']
            if all(col in district_data.columns for col in required_columns):
                # 如果district_data是DataFrame，计算最拥堵的路段
                top_congested = district_data.sort_values('congestion_index', ascending=False).head(3)
                for _, road in top_congested.iterrows():
                    worst_roads.append({
                        "road_name": road['road_name'],
                        "congestion_index": float(road['congestion_index']) if not pd.isna(road['congestion_index']) else 0.0,
                        "status": road.get('status', '未知')
                    })
            else:
                print(f"警告: district_data缺少必要的列: {required_columns}")
        else:
            print(f"警告: district_data不是有效的DataFrame或为空")
    except Exception as e:
        print(f"生成拥堵路段列表时出错: {e}")
    
    # 如果district_data不是DataFrame或获取失败，从预定义的路段中选择
    if not worst_roads:
        try:
            # 从预定义的道路数据中选择
            district_roads = {
                '南明区': ['解放路', '太慈路', '沙冲路'],
                '云岩区': ['中华北路', '省府路', '北京路'],
                '观山湖区': ['长岭北路', '金朱路', '金阳南路'],
                '白云区': ['白云大道', '云环路', '同城大道'],
                '花溪区': ['孟关大道', '花溪大道', '贵黄路'],
                '乌当区': ['新添大道', '东风路', '高新路'],
                '全市': ['金阳大道', '中华路', '延安路']
            }
            
            # 选择与区域匹配的道路，最多选择两条
            roads = district_roads.get(district_name, ['未知道路'])[:2]
            for road_name in roads:
                worst_roads.append({
                    "road_name": road_name,
                    "congestion_index": float(current_congestion),
                    "status": "预估拥堵"
                })
        except Exception as e:
            print(f"生成默认拥堵路段时出错: {e}")
            worst_roads = [{"road_name": "数据加载中...", "congestion_index": 0.5, "status": "未知"}]
    
    # 如果还是没有获取到道路，添加默认值
    if not worst_roads:
        worst_roads = [{"road_name": f"{district_name}主干道", "congestion_index": 0.5, "status": "数据不足"}]
    
    # 生成替代路线建议
    alternative_routes = []
    
    # 根据区域生成替代路线建议
    district_alt_routes = {
        '云岩区': [{"from": "林城西路", "to": "省府路"}, {"from": "中华北路", "to": "太平路"}],
        '南明区': [{"from": "解放路", "to": "太慈路"}, {"from": "沙冲路", "to": "市南路"}],
        '观山湖区': [{"from": "金朱路", "to": "长岭北路"}, {"from": "观山东路", "to": "石林东路"}],
        '白云区': [{"from": "白云大道", "to": "云环路"}, {"from": "同城大道", "to": "白金大道"}],
        '花溪区': [{"from": "孟关大道", "to": "花溪大道"}, {"from": "贵黄路", "to": "黄河路"}],
        '乌当区': [{"from": "新添大道", "to": "东风路"}, {"from": "高新路", "to": "创新路"}],
        '全市': [{"from": "环城高速", "to": "市区道路"}, {"from": "金阳大道", "to": "观山大道"}]
    }
    
    # 获取与区域匹配的替代路线
    alternative_routes = district_alt_routes.get(district_name, [{"from": "环城高速", "to": "市区道路"}])
    
    # 确保替代路线不为空
    if not alternative_routes:
        alternative_routes = [{"from": f"{district_name}主路", "to": f"{district_name}辅路"}]
    
    # 生成特别提醒
    special_notice = ""
    
    # 验证predictions数据
    valid_predictions = []
    for p in predictions:
        try:
            if isinstance(p, (int, float)) and not pd.isna(p):
                valid_predictions.append(float(p))
            else:
                valid_predictions.append(None)
        except:
            valid_predictions.append(None)
    
    if len(valid_predictions) >= 3 and valid_predictions[0] is not None and valid_predictions[1] is not None and valid_predictions[2] is not None:
        # 获取预测的第二个值(未来1小时)和第三个值(未来2小时)
        future_1h = valid_predictions[1]
        future_2h = valid_predictions[2]
        
        if hour < 7:
            special_notice = f"今日7:00-9:00为早高峰，该区域拥堵指数预计将达到{future_1h:.2f}，建议错峰出行。"
        elif hour >= 7 and hour < 10:
            special_notice = "当前处于早高峰时段，拥堵指数较高，建议选择公共交通工具出行。"
        elif hour >= 10 and hour < 16:
            special_notice = f"今日17:00-19:00为晚高峰，该区域拥堵指数预计将升高至{future_2h:.2f}，建议提前安排行程。"
        elif hour >= 16 and hour < 20:
            special_notice = "当前处于晚高峰时段，拥堵指数较高，建议选择公共交通工具出行。"
        else:
            special_notice = f"明日7:00-9:00为早高峰，该区域拥堵指数预计将达到0.80，建议早做准备。"
    else:
        # 如果预测数据不足，生成通用提示
        special_notice = f"由于数据量较少，预测结果仅供参考。请关注实时交通状况。"
    
    # 根据天气添加相关建议（模拟数据）
    # 使用固定的随机种子确保一致性
    np.random.seed(now.day + now.hour)
    if np.random.random() > 0.5:
        special_notice += " 此外，近期预计有雨，降雨天气可能会加剧道路拥堵情况，请提前规划行程。"
    
    # 确保返回一个完整的结构
    return {
        "best_time": best_time,
        "worst_roads": worst_roads[:3],  # 最多返回3条拥堵路段
        "alternative_routes": alternative_routes[:2],  # 最多返回2条替代路线
        "special_notice": special_notice
    }

# 新增后台更新线程
# 修复 background_thread 函数缩进
def background_thread():
    """SocketIO专用的后台线程，用于轻量级的实时数据推送"""
    while True:
        try:
            # 获取当前数据
            with data_lock:
                if not current_traffic_data.empty:
                    # 确保数据具有必要的字段
                    df_copy = current_traffic_data.copy()
                    if 'segment_id' in df_copy.columns and 'road_id' not in df_copy.columns:
                        # 添加road_id字段，确保与前端兼容
                        df_copy['road_id'] = df_copy['segment_id']
                    
                    # 准备数据并检查格式
                    try:
                        # 使用修改过的data_processor方法准备数据
                        map_data = data_processor.prepare_map_data(df_copy)
                        congestion_list = data_processor.prepare_congestion_list(df_copy)
                        alert_data = data_processor.prepare_alert_data(df_copy)
                        stats_data = data_processor.prepare_statistics(df_copy)
                        
                        # 解析JSON数据
                        try:
                            map_data_json = json.loads(map_data)
                            congestion_list_json = json.loads(congestion_list)
                            alerts_json = json.loads(alert_data)
                            stats_json = json.loads(stats_data)
                            
                            # 数据检查和调试输出
                            road_count = 0
                            if isinstance(map_data_json, list):
                                road_count = len(map_data_json)
                            elif isinstance(map_data_json, dict) and 'features' in map_data_json:
                                road_count = len(map_data_json['features'])
                            
                            print(f"WebSocket更新: 发送 {road_count} 条路段数据, " +
                                f"{len(congestion_list_json)} 条拥堵路段, " +
                                f"{len(alerts_json)} 条警报")
                            
                            # 发送更新
                            update_data = {
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'map_data': map_data_json,
                                'congestion_list': congestion_list_json,
                                'alerts': alerts_json,
                                'stats': stats_json
                            }
                            socketio.emit('traffic_update', update_data)
                            print(f"SocketIO实时更新已发送: {datetime.now()}")
                        except json.JSONDecodeError as je:
                            print(f"JSON解析错误: {je}")
                    except Exception as e:
                        print(f"准备WebSocket数据时发生错误: {str(e)}")
        except Exception as e:
            print(f"SocketIO后台线程错误: {e}")
            
        # 使用socketio.sleep而不是time.sleep，因为这是socketio的后台任务
        socketio.sleep(30)  # 每30秒推送一次轻量级更新

# 修复 handle_connect 函数缩进
@socketio.on('connect')
def handle_connect():
    socketio.start_background_task(background_thread)
    print('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    print('客户端已断开连接')

@socketio.on('get_trend_data')
def handle_get_trend_data():
    """发送历史趋势数据"""
    try:
        historical_trend = data_generator.get_historical_trend()
        trend_data = json.loads(data_processor.prepare_trend_data(historical_trend))
        socketio.emit('trend_data', trend_data)
    except Exception as e:
        print(f"准备趋势数据时出错: {e}")
        # 发送基本的空数据以避免前端错误
        empty_data = {
            "times": [(datetime.now() - timedelta(hours=i)).strftime('%H:%M') for i in range(24, -1, -1)],
            "congestion_indices": [0.3 for _ in range(25)]
        }
        socketio.emit('trend_data', empty_data)

def create_scheduler():
    # 检查变量定义是否完整
    jobstores = {
        'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
    }
    executors = {
        'default': {'type': 'threadpool', 'max_workers': 3}
    }
    
    # 检查参数是否正确
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        timezone='Asia/Shanghai'
    )
    
    try:
        scheduler.add_job(
            func=lambda: socketio.emit('auto_update', {'time': datetime.now().strftime("%H:%M:%S")}),
            trigger='interval',
            seconds=60,
            id='auto_update_job'
        )
        scheduler.start()
    except Exception as e:
        print(f"调度器启动失败: {e}")
    
    return scheduler

# 初始化调度器
scheduler = create_scheduler()

# 添加关闭钩子
@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    if scheduler.running:
        scheduler.shutdown(wait=False)

@app.route('/road/<int:road_id>')
def road_detail(road_id):
    """显示特定路段的详细信息页面"""
    try:
        # 获取当前交通数据
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，使用数据生成器获取一些数据
        if current_data.empty:
            data_lock.acquire()
            try:
                current_data = data_generator.get_real_time_data()
            finally:
                data_lock.release()
        
        # 查找特定的路段数据
        road_data = current_data[current_data['segment_id'] == road_id]
        
        # 如果找不到指定的路段，创建一个模拟路段数据
        if road_data.empty:
            app.logger.warning(f"路段ID {road_id} 未找到，使用模拟数据")
            # 创建一个模拟数据
            road_data = pd.DataFrame([{
                'segment_id': road_id,
                'road_id': road_id,
                'road_name': f"路段 #{road_id}",
                'district': "未知区域",
                'timestamp': datetime.now(),
                'congestion_index': 0.3,
                'status': "畅通",
                'average_speed': 40,
                'traffic_flow': 200,
                'latitude': 26.598194,
                'longitude': 106.707410
            }])
        
        # 转换为字典以便在模板中使用
        road = road_data.iloc[0].to_dict()
        
        # 确保road_id键存在（防止命名不一致）
        if 'road_id' not in road and 'segment_id' in road:
            road['road_id'] = road['segment_id']
        
        # 获取历史趋势数据
        try:
            trend_data = data_generator.get_road_historical_trend(road_id)
            # 转换为字典列表
            trend_data_list = trend_data.to_dict('records')
        except Exception as e:
            app.logger.error(f"获取历史趋势数据时出错: {str(e)}")
            trend_data_list = []
        
        # 获取相似路段
        try:
            similar_roads = data_generator.get_similar_roads(road_id)
            # 确保相似路段数据中有road_id键
            similar_roads_list = []
            for _, row in similar_roads.iterrows():
                row_dict = row.to_dict()
                if 'road_id' not in row_dict and 'segment_id' in row_dict:
                    row_dict['road_id'] = row_dict['segment_id']
                similar_roads_list.append(row_dict)
        except Exception as e:
            app.logger.error(f"获取相似路段数据时出错: {str(e)}")
            similar_roads_list = []
        
        return render_template('road_detail.html', 
                              road=road, 
                              trend_data=trend_data_list,
                              similar_roads=similar_roads_list)
    
    except Exception as e:
        app.logger.error(f"显示路段 {road_id} 详情时发生错误: {str(e)}")
        return render_template('error.html', 
                              error_title="路段详情页面错误",
                              error_message=f"无法显示路段 #{road_id} 的详情，错误信息: {str(e)}")

def update_traffic_data():
    """正确的后台数据更新函数"""
    global current_traffic_data, last_update_time
    
    while True:
        try:
            # 获取实时数据
            with data_lock:
                df = data_generator.get_real_time_data()
                if not df.empty:
                    # 确保数据具有必要的字段 - 修复road_id字段
                    if 'segment_id' in df.columns and 'road_id' not in df.columns:
                        # 添加road_id字段，确保与前端兼容
                        df['road_id'] = df['segment_id']
                    
                    # 更新历史数据
                    data_generator.historical_data = pd.concat(
                        [data_generator.historical_data, df], 
                        ignore_index=True
                    )
                    current_traffic_data = df
            last_update_time = datetime.now()
            
            # 准备前端所需的各种数据
            try:
                # 使用修改过的data_processor方法准备数据
                map_data = data_processor.prepare_map_data(current_traffic_data)
                
                # 准备拥堵路段列表 - 使用与dashboard相同的逻辑处理
                try:
                    congestion_list_str = data_processor.prepare_congestion_list(current_traffic_data)
                    # 解析并处理确保每个路段都有id字段
                    congestion_list_data = json.loads(congestion_list_str)
                    
                    # 确保每个路段都有road_id和id字段
                    if isinstance(congestion_list_data, list):
                        for item in congestion_list_data:
                            # 确保id字段存在
                            if 'id' not in item:
                                if 'road_id' in item:
                                    item['id'] = item['road_id']
                                elif 'segment_id' in item:
                                    item['id'] = item['segment_id']
                            # 确保road_id字段存在
                            if 'road_id' not in item and 'segment_id' in item:
                                item['road_id'] = item['segment_id']
                    
                    # 重新序列化为JSON字符串
                    congestion_list = json.dumps(congestion_list_data)
                    print(f"实时更新: 拥堵路段列表准备完成，共{len(congestion_list_data)}条数据")
                except Exception as e:
                    print(f"实时更新: 拥堵路段列表准备失败: {str(e)}")
                    congestion_list = '[]'  # 默认空数组

                alert_data = data_processor.prepare_alert_data(current_traffic_data)
                stats_data = data_processor.prepare_statistics(current_traffic_data)
                
                # 解析JSON数据
                try:
                    map_data_json = json.loads(map_data)
                    congestion_list_json = congestion_list_data if isinstance(congestion_list_data, list) else json.loads(congestion_list)
                    alerts_json = json.loads(alert_data)
                    stats_json = json.loads(stats_data)
                    
                    # 发送更新
                    update_data = {
                        'timestamp': last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'map_data': map_data_json,
                        'congestion_list': congestion_list_json,
                        'alerts': alerts_json,
                        'stats': stats_json
                    }
                    
                    socketio.emit('traffic_update', update_data)
                    print(f"数据已更新: {last_update_time}, 路段数: {len(current_traffic_data)}")
                except json.JSONDecodeError as je:
                    print(f"JSON解析错误: {je}")
            except Exception as e:
                print(f"数据处理或发送错误: {e}")
                
        except Exception as e:
            print(f"数据更新主循环错误: {e}")
        
        time.sleep(config.SIMULATION_INTERVAL)

@app.route('/prediction')
def prediction_page():
    """预测页面视图函数"""
    try:
        # 获取实时交通数据作为基础
        current_data = data_generator.get_real_time_data()
        
        # 如果当前数据为空，则生成新数据
        if current_data.empty:
            data_generator.generate_data()
            current_data = data_generator.get_real_time_data()
        
        # 准备未来3小时的预测数据
        now = datetime.now()
        predictions = []
        
        # 计算当前平均拥堵指数作为基准
        current_avg_congestion = current_data['congestion_index'].mean()
        if pd.isna(current_avg_congestion) or current_avg_congestion <= 0:
            current_avg_congestion = 0.4  # 使用默认值
        
        # 对未来3小时进行预测
        for i in range(3):
            future_time = now + timedelta(hours=i+1)
            hour = future_time.hour
            
            # 基于时间段调整预测值
            if 7 <= hour <= 9:  # 早高峰
                prediction_value = min(0.95, current_avg_congestion * 1.2)
            elif 17 <= hour <= 19:  # 晚高峰
                prediction_value = min(0.95, current_avg_congestion * 1.3)
            elif 22 <= hour or hour <= 5:  # 夜间
                prediction_value = max(0.1, current_avg_congestion * 0.7)
            else:  # 其他时段
                prediction_value = current_avg_congestion
            
            # 增加一些随机变化
            np.random.seed(int(now.timestamp()) + i)
            prediction_value = max(0.1, min(0.95, prediction_value + (np.random.random() * 0.1 - 0.05)))
            
            # 根据拥堵指数确定状态
            if prediction_value < 0.4:
                status = '畅通'
            elif prediction_value < 0.6:
                status = '轻度拥堵'
            elif prediction_value < 0.8:
                status = '中度拥堵'
            else:
                status = '严重拥堵'
            
            # 计算路段状态分布 - 基于当前分布并稍做调整
            status_counts = {'畅通': 0, '轻度拥堵': 0, '中度拥堵': 0, '严重拥堵': 0}
            
            # 计算当前路段状态分布
            current_status_counts = current_data['status'].value_counts().to_dict()
            
            # 根据预测拥堵指数调整分布
            for status_name, count in current_status_counts.items():
                factor = 1.0
                if prediction_value < 0.4:  # 畅通时期
                    if status_name == '畅通':
                        factor = 1.2
                    else:
                        factor = 0.8
                elif prediction_value >= 0.7:  # 拥堵时期
                    if status_name == '严重拥堵' or status_name == '中度拥堵':
                        factor = 1.2
                    else:
                        factor = 0.8
                
                # 确保key存在于status_counts中
                if status_name in status_counts:
                    status_counts[status_name] = int(count * factor)
                else:
                    # 如果遇到其他状态名称，映射到最接近的标准状态
                    if '畅通' in status_name or '流畅' in status_name:
                        status_counts['畅通'] += int(count * factor)
                    elif '轻' in status_name:
                        status_counts['轻度拥堵'] += int(count * factor)
                    elif '中' in status_name:
                        status_counts['中度拥堵'] += int(count * factor)
                    elif '严' in status_name or '重' in status_name:
                        status_counts['严重拥堵'] += int(count * factor)
                    else:
                        # 默认分配
                        status_counts['轻度拥堵'] += int(count * factor)
            
            # 确保至少有一些路段在每个状态
            min_count = 1
            for key in status_counts:
                status_counts[key] = max(min_count, status_counts[key])
            
            # 计算拥堵路段数（非畅通的路段）
            congested_count = sum(count for status_name, count in status_counts.items() if status_name != '畅通')
            
            # 构建预测数据项
            prediction = {
                'timestamp': future_time.strftime('%Y-%m-%d %H:%M'),
                'hour': future_time.hour,
                'avg_congestion': float(prediction_value),
                'status': status,
                'congested_count': congested_count,
                'status_counts': status_counts
            }
            
            predictions.append(prediction)
        
        # 渲染预测页面
        return render_template('prediction.html', predictions=predictions)
        
    except Exception as e:
        print(f"预测页面错误: {str(e)}")
        # 出错时返回空预测列表
        return render_template('prediction.html', predictions=[])

if __name__ == '__main__':
    # 启动数据更新后台线程
    update_thread = threading.Thread(target=update_traffic_data)
    update_thread.daemon = True
    update_thread.start()
    
    # 启动Flask应用
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=config.DEBUG)