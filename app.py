"""
贵阳市交通拥堵监测系统 - 主应用
"""
# 确保在文件顶部正确导入

import os
import json
import time
from datetime import datetime
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # Add this import
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import pandas as pd

# 导入自定义模块
from utils.data_generator import TrafficDataGenerator
from utils.data_processor import TrafficDataProcessor
from models.predictor import TrafficPredictor
import config

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

# 替换原有app初始化（约第26行）
app = create_app()
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['DEBUG'] = config.DEBUG

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# 初始化数据生成器和处理器
data_generator = TrafficDataGenerator(num_road_segments=config.NUM_ROAD_SEGMENTS)
data_processor = TrafficDataProcessor()

# 初始化预测器（如果有保存的模型就加载，否则后续会使用新数据训练）
predictor = TrafficPredictor()
if not predictor.is_trained:
    try:
        # 使用历史数据训练模型
        historical_data = data_generator.historical_data
        if not historical_data.empty:
            predictor.train(historical_data)
            print("模型训练完成")
        else:
            print("没有足够的历史数据用于训练模型")
    except Exception as e:
        print(f"模型训练失败: {e}")

# 全局数据存储
current_traffic_data = pd.DataFrame()
last_update_time = datetime.now()

# 添加线程锁（约第50行）
import threading
data_lock = threading.Lock()

# 添加全局错误处理 - 移到全局作用域
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
    
    # 准备地图数据
    map_data = json.loads(data_processor.prepare_map_data(current_traffic_data))
    
    # 准备拥堵路段列表
    # 确保congestion_list包含完整的road对象
    congestion_list = json.loads(data_processor.prepare_congestion_list(current_traffic_data))
    
    # 准备警报数据
    try:
        alerts = json.loads(data_processor.prepare_alert_data(current_traffic_data))
    except Exception as e:
        print(f"警报数据准备失败: {str(e)}")
        alerts = []
    
    # 准备趋势数据 - 确保变量已初始化
    try:
        trend_data = data_processor.prepare_trend_data([])  # 初始化为空列表
    except Exception as e:
        print(f"趋势数据准备失败: {str(e)}")
        trend_data = json.dumps({'labels': [], 'datasets': []})
    
    # 准备统计数据 - 确保变量已初始化
    try:
        stats_json = data_processor.prepare_statistics(current_traffic_data)
        stats = json.loads(stats_json)
    except Exception as e:
        print(f"统计数据准备失败: {str(e)}")
        stats = {'avg_congestion': 0, 'avg_speed': 0}

    return render_template('dashboard.html',
                        active_page='dashboard',
                        map_data=json.dumps(map_data),
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
    return render_template('analysis.html', active_page='analysis')

# 在预测页面路由处理函数中（约第120行）
@app.route('/prediction')
def prediction():
    """拥堵预测页面"""
    global current_traffic_data
    future_predictions = []
    
    if predictor.is_trained and not current_traffic_data.empty:
        try:
            # 添加缺失的预测数据生成
            prediction_df = predictor.predict_future(current_traffic_data, hours_ahead=3)
            
            # 修复缩进问题（原123行附近）
            grouped = prediction_df.groupby(pd.Grouper(key='timestamp', freq='H'))
            
            for group_time, group_data in grouped:  # 确保正确缩进
                hour_data = {
                    'timestamp': group_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'avg_congestion': group_data['congestion_index'].mean(),
                    'congested_count': group_data.loc[group_data['congestion_index'] >= 0.6].shape[0],
                    'status_counts': group_data['status'].value_counts(dropna=False).to_dict()
                }
                future_predictions.append(hour_data)
                
        except Exception as e:
            print(f"预测数据生成失败: {e}")

    # 添加返回语句
    return render_template('prediction.html', 
                        active_page='prediction',
                        predictions=future_predictions)

# 修改数据更新逻辑
def update_traffic_data():
    """正确的后台数据更新函数"""
    global current_traffic_data, last_update_time
    
    while True:
        try:
            # 获取实时数据
            with data_lock:
                df = data_generator.get_real_time_data()
                if not df.empty:
                    # 更新历史数据
                    data_generator.historical_data = pd.concat(
                        [data_generator.historical_data, df], 
                        ignore_index=True
                    )
                    current_traffic_data = df
                    last_update_time = datetime.now()
                    
                    # 准备前端所需的各种数据
                    try:
                        update_data = {
                            'timestamp': last_update_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'map_data': json.loads(data_processor.prepare_map_data(current_traffic_data)),
                            'congestion_list': json.loads(data_processor.prepare_congestion_list(current_traffic_data)),
                            'alerts': json.loads(data_processor.prepare_alert_data(current_traffic_data)),
                            'stats': json.loads(data_processor.prepare_statistics(current_traffic_data))
                        }
                        
                        socketio.emit('traffic_update', update_data)
                        print(f"数据已更新: {last_update_time}")
                    except Exception as e:
                        print(f"数据处理或发送错误: {e}")
                        
        except Exception as e:
            print(f"数据更新主循环错误: {e}")
        
        # 使用time.sleep而不是socketio.sleep，因为这个函数在单独的线程中运行
        time.sleep(config.SIMULATION_INTERVAL)

@app.route('/about')
def about():
    """关于系统页面"""
    return render_template('about.html', active_page='about')

# 新增后台更新线程
# 修复 background_thread 函数缩进
def background_thread():
    """SocketIO专用的后台线程，用于轻量级的实时数据推送"""
    while True:
        try:
            # 获取当前数据
            with data_lock:
                if not current_traffic_data.empty:
                    # 准备数据
                    update_data = {
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'map_data': json.loads(data_processor.prepare_map_data(current_traffic_data)),
                        'congestion_list': json.loads(data_processor.prepare_congestion_list(current_traffic_data)),
                        'alerts': json.loads(data_processor.prepare_alert_data(current_traffic_data)),
                        'stats': json.loads(data_processor.prepare_statistics(current_traffic_data))
                    }
                    
                    # 发送更新
                    socketio.emit('traffic_update', update_data)
                    print(f"SocketIO实时更新已发送: {datetime.now()}")
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
    historical_trend = data_generator.get_historical_trend()
    trend_data = json.loads(data_processor.prepare_trend_data(historical_trend))
    socketio.emit('trend_data', trend_data)

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
                data_generator.refresh_data()
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

if __name__ == '__main__':
    # 启动数据更新后台线程
    update_thread = threading.Thread(target=update_traffic_data)
    update_thread.daemon = True
    update_thread.start()
    
    # 启动Flask应用
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=config.DEBUG)