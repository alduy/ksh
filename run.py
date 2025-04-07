"""
贵阳市交通拥堵监测系统 - 启动脚本
"""
from app import app, socketio, config  # 保持原有导入

if __name__ == '__main__':
    print("=" * 50)
    print("贵阳市交通拥堵监测系统 启动中...")
    print(f"系统将运行在: http://localhost:{config.PORT}")
    print("=" * 50)
    
    socketio.run(app, host='0.0.0.0', port=config.PORT, debug=config.DEBUG)