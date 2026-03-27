from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from models import ModelManager
from tunnel_control import TunnelController
import base64
import time
import uuid
import logging
import ssl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s| %(levelname)-7s | %(message)s',
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)
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

if __name__ == '__main__':
        # Removed ssl_context to use HTTP
    app.run(host='0.0.0.0', port=8443)
