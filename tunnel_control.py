import logging
import base64
from typing import Dict, Any, List
from models import ModelManager
from tunnel_manager import ParamikoTunnel

class TunnelController:
    # Ensure dictionary only stores ParamikoTunnel instances
    active_tunnels: Dict[str, ParamikoTunnel] = {}

    @staticmethod
    def start_tunnel(tunnel_id: str):
        tunnels = ModelManager.get_tunnels()
        ssh_users = ModelManager.get_ssh_users()
        
        tunnel_data = None
        for t in tunnels:
            if t['id'] == tunnel_id:
                tunnel_data = t
                break
        
        if not tunnel_data:
            return False, "隧道配置不存在。"
        
        user_ref = tunnel_data.get('ssh_user_ref')
        if not user_ref or user_ref not in ssh_users:
            return False, "隧道关联用户不存在。"
        
        user_info = ssh_users[user_ref]
        username = user_info['login_username']
        password = base64.b64decode(user_info['login_password_base64']).decode()
        
        # 1. Clean up old instance if exists
        if tunnel_id in TunnelController.active_tunnels:
            try:
                old_t = TunnelController.active_tunnels[tunnel_id]
                if hasattr(old_t, 'stop'):
                    old_t.stop()
            except Exception as e:
                logging.error(f"Error stopping existing tunnel {tunnel_id}: {e}")
            finally:
                if tunnel_id in TunnelController.active_tunnels:
                    del TunnelController.active_tunnels[tunnel_id]
        
        # 2. Create new instance
        new_t = None
        try:
            new_t = ParamikoTunnel(
                ssh_address_or_host=tunnel_data['ssh_host'],
                ssh_username=username,
                ssh_password=password,
                ssh_pkey=tunnel_data.get('ssh_pkey'),
                remote_bind_address=tuple(tunnel_data['remote_bind']),
                local_bind_address=tuple(tunnel_data['local_bind']),
                ssh_port=int(tunnel_data['ssh_port']),
                forward_type=tunnel_data.get('type', 'L'),
                loglevel=logging.INFO
            )
            # Add to active tunnels for monitoring BEFORE starting
            TunnelController.active_tunnels[tunnel_id] = new_t
            new_t.start() # Asynchronous start
            return True, "隧道启动指令已发送。"
        except Exception as e:
            # Record error but DO NOT delete from active_tunnels yet
            # so the front-end can poll the 'last_error'
            if new_t:
                new_t._last_error = str(e)
                new_t.tunnel_enable = False
                # If it was added to active_tunnels, we keep it there with the error status
                if tunnel_id not in TunnelController.active_tunnels:
                    TunnelController.active_tunnels[tunnel_id] = new_t
            return False, f"启动异常: {str(e)}"

    @staticmethod
    def stop_tunnel(tunnel_id: str):
        if tunnel_id not in TunnelController.active_tunnels:
            return True, "隧道未运行。"

        try:
            target_t = TunnelController.active_tunnels[tunnel_id]
            if hasattr(target_t, 'stop'):
                target_t.stop()
            return True, "隧道停止指令已发送。"
        except Exception as e:
            return False, f"停止操作异常: {str(e)}"
        finally:
            # Ensure removal from active_tunnels regardless of success/failure
            if tunnel_id in TunnelController.active_tunnels:
                del TunnelController.active_tunnels[tunnel_id]

    @staticmethod
    def get_status(tunnel_id: str):
        obj = TunnelController.active_tunnels.get(tunnel_id)
        # Check if object exists and has the required method
        if obj and hasattr(obj, 'get_tunnel_status'):
            return obj.get_tunnel_status()
        # Return default inactive status if tunnel not found or not initialized
        return {"is_active": False, "tunnel_enable": False, "user_wants_active": False}
