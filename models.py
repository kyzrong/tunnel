import json
import os
import base64
from typing import Dict, List, Any, Optional

USER_FILE = 'user.json'
TUNNEL_FILE = 'tunnel_info.json'

def init_data():
    if not os.path.exists(USER_FILE):
        with open(USER_FILE, 'w') as f:
            # admin/admin as default auth
            json.dump({
                "auth": {"admin": {"password_base64": base64.b64encode(b"admin").decode()}},
                "user": {}
            }, f)
    else:
        # Migrate or ensure structure
        with open(USER_FILE, 'r') as f:
            data = json.load(f)
        if "auth" not in data or "user" not in data:
             with open(USER_FILE, 'w') as f:
                json.dump({
                    "auth": data if "auth" not in data else data["auth"],
                    "user": {} if "user" not in data else data["user"]
                }, f)

    if not os.path.exists(TUNNEL_FILE):
        with open(TUNNEL_FILE, 'w') as f:
            json.dump([], f)

class ModelManager:
    @staticmethod
    def _get_data() -> Dict[str, Any]:
        with open(USER_FILE, 'r') as f:
            return json.load(f)

    @staticmethod
    def _save_data(data: Dict[str, Any]):
        with open(USER_FILE, 'w') as f:
            json.dump(data, f, indent=4)

    # Auth Methods (Admin users for web login)
    @staticmethod
    def get_auth_users() -> Dict[str, Any]:
        return ModelManager._get_data().get("auth", {})

    @staticmethod
    def update_auth_password(username, old_password, new_password):
        data = ModelManager._get_data()
        auth = data.get("auth", {})
        if username in auth:
            stored_pass = base64.b64decode(auth[username]['password_base64']).decode()
            if stored_pass == old_password:
                auth[username]['password_base64'] = base64.b64encode(new_password.encode()).decode()
                ModelManager._save_data(data)
                return True, "密码已修改。"
            return False, "旧密码错误。"
        return False, "管理员用户不存在。"

    # User Methods (SSH tunnel credentials)
    @staticmethod
    def get_ssh_users() -> Dict[str, Any]:
        return ModelManager._get_data().get("user", {})

    @staticmethod
    def add_ssh_user(name, login_username, login_password):
        data = ModelManager._get_data()
        if name in data["user"]:
            return False, f"用户别名 '{name}' 已存在。"
        data["user"][name] = {
            "login_username": login_username,
            "login_password_base64": base64.b64encode(login_password.encode()).decode()
        }
        ModelManager._save_data(data)
        return True, "用户已添加。"

    @staticmethod
    def delete_ssh_user(name):
        tunnels = ModelManager.get_tunnels()
        for t in tunnels:
            if t.get('ssh_user_ref') == name:
                return False, f"用户名称 '{name}' 与隧道 '{t['name']}' 有关联，不能删除。"
        
        data = ModelManager._get_data()
        if name in data["user"]:
            del data["user"][name]
            ModelManager._save_data(data)
            return True, "用户已删除。"
        return False, "用户不存在。"

    # Tunnel Methods
    @staticmethod
    def get_tunnels() -> List[Dict[str, Any]]:
        with open(TUNNEL_FILE, 'r') as f:
            tunnels = json.load(f)
            for t in tunnels:
                if 'auto_start' not in t:
                    t['auto_start'] = False
            return tunnels

    @staticmethod
    def save_tunnels(tunnels: List[Dict[str, Any]]):
        with open(TUNNEL_FILE, 'w') as f:
            json.dump(tunnels, f, indent=4)

    @staticmethod
    def add_tunnel(tunnel_data: Dict[str, Any]):
        tunnels = ModelManager.get_tunnels()
        # 检查名称唯一性
        for t in tunnels:
            if t['name'] == tunnel_data['name']:
                return False, f"隧道名称 '{t['name']}' 已存在。"
        
        tunnels.append(tunnel_data)
        ModelManager.save_tunnels(tunnels)
        return True, "隧道已添加。"

    @staticmethod
    def update_tunnel(tunnel_data: Dict[str, Any]):
        tunnel_id = tunnel_data.get('id')
        tunnels = ModelManager.get_tunnels()
        for i, t in enumerate(tunnels):
            if t['id'] == tunnel_id:
                tunnels[i] = tunnel_data
                ModelManager.save_tunnels(tunnels)
                return True
        return False

    @staticmethod
    def delete_tunnel(tunnel_id: str):
        tunnels = ModelManager.get_tunnels()
        tunnels = [t for t in tunnels if t['id'] != tunnel_id]
        ModelManager.save_tunnels(tunnels)

    @staticmethod
    def sort_tunnel(tunnel_id: str, direction: str):
        tunnels = ModelManager.get_tunnels()
        index = -1
        for i, t in enumerate(tunnels):
            if t['id'] == tunnel_id:
                index = i
                break
        
        if index == -1: return False
        if direction == 'up' and index > 0:
            tunnels[index], tunnels[index-1] = tunnels[index-1], tunnels[index]
        elif direction == 'down' and index < len(tunnels) - 1:
            tunnels[index], tunnels[index+1] = tunnels[index+1], tunnels[index]
        else: return False
        
        ModelManager.save_tunnels(tunnels)
        return True

init_data()
