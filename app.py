from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from models import ModelManager
from tunnel_control import TunnelController
import base64
import time
import uuid
import logging
import ssl
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s| %(levelname)-7s | %(message)s',
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)
# 禁用 Werkzeug 默认的访问日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR) # 只显示错误，不显示正常的 INFO (GET/POST)

app.secret_key = 'super_secret_ssh_tunnel_key'

# Global state
login_attempts = {} # {username: {'count': int, 'last_fail': float}}
active_sessions = {} # {username: session_id}

@app.before_request
def check_session():
    # 验证测试阶段：直接注入 admin Session
    session['username'] = 'admin'
    session['last_activity'] = time.time()
    return

@app.route('/')
def index():
    return redirect(url_for('manage'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # 既然已自动登录，访问 /login 直接去 /manage
    return redirect(url_for('manage'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('manage'))

@app.route('/manage')
def manage():
    return render_template('manage.html')

# API Endpoints
@app.route('/api/auth/change_password', methods=['POST'])
def change_password():
    data = request.json
    success, message = ModelManager.update_auth_password('admin', data['old_password'], data['new_password'])
    return jsonify({"success": success, "message": message})

@app.route('/api/ssh_users', methods=['GET'])
def get_ssh_users():
    users = ModelManager.get_ssh_users()
    return jsonify([{"name": k, "login_username": v['login_username']} for k, v in users.items()])

@app.route('/api/ssh_users/add', methods=['POST'])
def add_ssh_user():
    data = request.json
    success, message = ModelManager.add_ssh_user(data['name'], data['login_username'], data['login_password'])
    return jsonify({"success": success, "message": message})

@app.route('/api/ssh_users/delete', methods=['POST'])
def delete_ssh_user():
    data = request.json
    success, message = ModelManager.delete_ssh_user(data['name'])
    return jsonify({"success": success, "message": message})

@app.route('/api/tunnels', methods=['GET'])
def get_tunnels():
    tunnels = ModelManager.get_tunnels()
    for t in tunnels:
        status = TunnelController.get_status(t['id'])
        t.update(status)
    return jsonify(tunnels)

@app.route('/api/tunnels/add', methods=['POST'])
def add_tunnel():
    data = request.json
    data['id'] = str(uuid.uuid4())
    success, message = ModelManager.add_tunnel(data)
    return jsonify({"success": success, "message": message})

@app.route('/api/tunnels/edit', methods=['POST'])
def edit_tunnel():
    data = request.json
    tunnel_id = data.get('id')
    status = TunnelController.get_status(tunnel_id)
    if status.get('user_wants_active'):
        return jsonify({"success": False, "message": "隧道正在运行或正在尝试恢复，请先停止再修改。"})
    ModelManager.update_tunnel(data)
    return jsonify({"success": True})

@app.route('/api/tunnels/delete', methods=['POST'])
def delete_tunnel():
    data = request.json
    TunnelController.stop_tunnel(data['id'])
    ModelManager.delete_tunnel(data['id'])
    return jsonify({"success": True})

@app.route('/api/tunnels/start', methods=['POST'])
def start_tunnel():
    data = request.json
    success, message = TunnelController.start_tunnel(data['id'])
    return jsonify({"success": success, "message": message})

@app.route('/api/tunnels/stop', methods=['POST'])
def stop_tunnel():
    data = request.json
    success, message = TunnelController.stop_tunnel(data['id'])
    return jsonify({"success": success, "message": message})

@app.route('/api/tunnels/sort', methods=['POST'])
def sort_tunnel():
    data = request.json
    success = ModelManager.sort_tunnel(data['id'], data['direction'])
    return jsonify({"success": success})

def _auto_start_tunnels():
    logging.info("开始检查并自动启动后台隧道...")
    time.sleep(2)  # 等待 Flask 启动后执行，防止过早争夺资源
    tunnels = ModelManager.get_tunnels()
    started_count = 0
    for t in tunnels:
        if t.get('auto_start') == True:
            logging.info(f"正在自动启动隧道: {t.get('name', 'Unknown')}")
            success, msg = TunnelController.start_tunnel(t['id'])
            if success:
                started_count += 1
                logging.info(f"隧道 '{t.get('name', 'Unknown')}' 启动指令发送成功: {msg}")
            else:
                logging.error(f"隧道 '{t.get('name', 'Unknown')}' 自动启动失败: {msg}")
    
    if started_count > 0:
        logging.info(f"后台隧道自动启动处理完成，已发出 {started_count} 个隧道的启动指令。")
    else:
        logging.info("没有需要自动启动的隧道。")

if __name__ == '__main__':
    import argparse
    listen_addr = "0.0.0.0"
    listen_port = 8443

    p = argparse.ArgumentParser(description="")

    p.add_argument("-i", "--ip", help="set remove ip,default 0.0.0.0", default='0.0.0.0')
    p.add_argument("-p", "--port", help="set port,xxx or xxx-yyy,default 8443", default=8443)
    args = p.parse_args()
    if args.ip:
        listen_addr = args.ip
    if args.port:
        listen_port = args.port

    print(f"Listening on: {listen_addr}:{listen_port}")
    threading.Thread(target=_auto_start_tunnels, daemon=True).start()
    app.run(host=listen_addr, port=listen_port)
