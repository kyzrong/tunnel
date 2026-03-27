import logging
import time
import threading
import socket
import select
from typing import Optional, Dict, Any, Tuple
import paramiko

class ParamikoTunnel:
    def __init__(
        self,
        ssh_address_or_host: str,
        ssh_username: str,
        remote_bind_address: Tuple[str, int],
        ssh_password: Optional[str] = None,
        ssh_pkey: Optional[str] = None,
        local_bind_address: Optional[Tuple[str, int]] = None,
        ssh_port: int = 22,
        loglevel: int = logging.INFO,
        forward_type: str = 'L'
    ):
        self.ssh_host = ssh_address_or_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_username
        self.ssh_pass = ssh_password
        self.ssh_pkey = ssh_pkey
        self.remote_bind = remote_bind_address
        self.local_bind = local_bind_address
        self.forward_type = forward_type.upper()
        
        self.tunnel_enable: bool = False 
        self.user_wants_active: bool = False 
        self._last_error = None
        self._monitor_stop_event = threading.Event()
        self._monitor_thread = None
        self._lock = threading.RLock()
        
        self.logger = logging.getLogger(f'paramiko_tunnel_{forward_type}_{ssh_address_or_host}')
        self.logger.setLevel(loglevel)

        self._client = None
        self._transport = None
        self._listener_socket = None
        self._stop_event = threading.Event() # For remote forward handler

    def _is_port_listening(self, host, port) -> bool:
        """检查本地端口是否确实在监听"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return False # Can bind, so it's not listening
            except OSError as e:
                if e.errno == 98 or e.errno == 10048: # Address already in use (Linux 98, Windows 10048)
                    return True
                else:
                    raise
            except: # Catch other potential errors
                return False

    def _check_real_status(self) -> bool:
            """多重校验：物理端口 + SSH 协议心跳"""
            try:
                # 1. 检查 SSH Transport 状态 (L 和 R 都需要)
                if not self._transport or not self._transport.is_active():
                    self.logger.debug(f"SSH transport inactive for {self.local_bind}")
                    return False
                    
                # 2.[关键修复: 强制心跳探测] 
                # 发送 SSH Ignore 空报文，探测底层 TCP 或跳板机链路是否真实存活。
                # 如果级联的上级隧道断开，这里的 send_ignore 会立刻抛出异常。
                try:
                    self._transport.send_ignore()
                except Exception as e:
                    self.logger.debug(f"SSH transport send_ignore failed (Pipe broken): {e}")
                    return False

                # 3. 检查本地物理端口监听状态 (仅限 L 类型隧道)
                if self.forward_type == 'L':
                    if not self._is_port_listening(self.local_bind[0], self.local_bind[1]):
                        self.logger.debug(f"Local port {self.local_bind[1]} is not listening.")
                        return False
                # 对于 R 类型，由于端口绑定在远端服务器上，无法通过本地 socket 检查。
                # 只要上面的心跳探测成功，我们就认为它是 Active 的。
                
                self.logger.debug(f"Tunnel {self.local_bind} seems active.")
                return True
            except Exception as e:
                self.logger.error(f"Error in _check_real_status for {self.local_bind}: {e}")
                return False

    def _monitor_loop(self):
        self.logger.info(f"Monitor thread started for {self.local_bind}")
        while not self._monitor_stop_event.is_set():
            try:
                if self.user_wants_active:
                    if not self._check_real_status():
                        with self._lock:
                            # Re-check after acquiring lock to avoid race conditions
                            if self.user_wants_active and not self._check_real_status():
                                self.logger.warning(f"Health check failed for {self.local_bind}. Attempting restart. Last error: {self._last_error}")
                                try:
                                    self._do_start_internal_logic()
                                    self.logger.info(f"Restart successful for {self.local_bind}")
                                except Exception as e:
                                    self._last_error = f"Restart failed: {str(e)}"
                                    self.logger.error(f"Restart failed for {self.local_bind}: {e}")
                                    self.tunnel_enable = False
                                    # 如果重启失败，清理掉半死不活的资源，等待下次重试
                                    self._do_stop_internal_logic()
                else:
                    # If user wants stopped but port is still listening, cleanup
                    if self._is_port_listening(self.local_bind[0], self.local_bind[1]):
                        with self._lock:
                            if not self.user_wants_active:
                                self.logger.info(f"User wants stopped but port {self.local_bind[1]} is listening. Stopping.")
                                self._do_stop_internal_logic()
            except Exception as e:
                self.logger.error(f"Monitor error for {self.local_bind}: {e}")
            
            time.sleep(2)

    def _do_start_internal_logic(self):
        self._do_stop_internal_logic() # Ensure clean state before starting
        
        try:
            # --- Paramiko SSH Connection ---
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                self.ssh_host, port=self.ssh_port, username=self.ssh_user,
                password=self.ssh_pass, key_filename=self.ssh_pkey, timeout=10,
                banner_timeout=30,allow_agent=False, look_for_keys=False
            )
            self._transport = self._client.get_transport()
            self._transport.set_keepalive(10)

            self._stop_event.clear() # [优化] 确保启动前重置停止事件

            if self.forward_type == 'L':
                if self._is_port_listening(self.local_bind[0], self.local_bind[1]):
                    raise Exception(f"Port {self.local_bind[1]} is already in use by another process.")
                
                # --- Local Port Forwarding (L) ---
                self._listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._listener_socket.bind(self.local_bind)
                self._listener_socket.listen(5)
                self.logger.info(f"Local listener started on {self.local_bind}")

                def local_forward_loop():
                    while not self._stop_event.is_set():
                        try:
                            chan, addr = self._listener_socket.accept()
                            forwarder = threading.Thread(target=self._forward_data, args=(chan, self.remote_bind[0], self.remote_bind[1]))
                            forwarder.daemon = True
                            forwarder.start()
                        except socket.timeout:
                            continue
                        except OSError as e: 
                            # 如果是我们主动停止引发的错误，则安静退出
                            if self._stop_event.is_set():
                                break
                            if e.errno == 9: # Bad file descriptor (socket closed)
                                break
                            self.logger.warning(f"Socket accept error: {e}")
                            self._last_error = f"Runtime accept error: {e}" # [修改] 记录运行时异常
                            break
                        except Exception as e:
                            if self._stop_event.is_set():
                                break
                            self.logger.error(f"Unexpected error in local_forward_loop: {e}")
                            self._last_error = f"Runtime error: {e}" # [修改] 记录运行时异常
                            break

                t = threading.Thread(target=local_forward_loop)
                t.daemon = True
                t.start()

            else: # Remote forward type 'R'
                # --- Remote Port Forwarding (R) ---
                self._transport.request_port_forward(self.local_bind[0], self.local_bind[1])
                self.logger.info(f"Remote forward requested: listen on {self.ssh_host}:{self.local_bind[1]} -> {self.remote_bind}")

                def reverse_loop():
                    while not self._stop_event.is_set():
                        try:
                            chan = self._transport.accept(1)
                            if chan is None: continue
                            thr = threading.Thread(target=self._reverse_handler, args=(chan,))
                            thr.daemon = True
                            thr.start()
                        except Exception as e:
                            if self._stop_event.is_set():
                                break
                            self.logger.debug(f"Reverse loop error: {e}")
                            self._last_error = f"Reverse runtime error: {e}" #[修改] 记录运行时异常
                            break # Exit loop on error or stop event

                t = threading.Thread(target=reverse_loop)
                t.daemon = True
                t.start()
            
            self.tunnel_enable = True
            self._last_error = None
            self.logger.info(f"Successfully started tunnel {self.local_bind}")
        except Exception as e:
            self.logger.error(f"Internal start failed: {e}. Cleaning up...")
            self._do_stop_internal_logic()
            raise e

    def _forward_data(self, client_socket, remote_host, remote_port):
        """真正的 SSH 加密通道转发 (L)"""
        ssh_channel = None
        try:
            try: src_addr = client_socket.getpeername()
            except: src_addr = ('127.0.0.1', 0)
            
            # 使用 direct-tcpip 开启 SSH 内部通道
            ssh_channel = self._transport.open_channel(
                "direct-tcpip", dest_addr=(remote_host, remote_port), src_addr=src_addr, timeout=10.0
            )
            if ssh_channel is None: return

            ssh_channel.settimeout(0.0)
            client_socket.settimeout(0.0)

            while not self._stop_event.is_set():
                r, w, x = select.select([client_socket, ssh_channel], [], [], 1.0)
                if client_socket in r:
                    data = client_socket.recv(4096)
                    if not data: break
                    ssh_channel.sendall(data)
                if ssh_channel in r:
                    data = ssh_channel.recv(4096)
                    if not data: break
                    client_socket.sendall(data)
        except: pass
        finally:
            if client_socket: client_socket.close()
            if ssh_channel: ssh_channel.close()

    def _reverse_handler(self, chan):
        """Handles data forwarding for remote forward (R)"""
        try:
            sock = socket.socket()
            sock.settimeout(5.0)
            sock.connect(self.remote_bind) # Connect to the actual destination
            sock.settimeout(None)
            while True:
                r, w, x = select.select([chan, sock], [],[], 1)
                if chan in r:
                    data = chan.recv(1024)
                    if not data: break
                    sock.send(data)
                if sock in r:
                    data = sock.recv(1024)
                    if not data: break
                    chan.send(data)
        except Exception as e:
            self.logger.debug(f"Reverse handler error: {e}")
        finally:
            chan.close()
            sock.close()

    def _do_stop_internal_logic(self):
        try:
            # 1. [修改] 发送停止信号，通知所有依赖 _stop_event 的转发线程优雅退出
            if hasattr(self, '_stop_event') and self._stop_event:
                self._stop_event.set()
                
            # 2. 清理 L 类型监听 Socket
            if self.forward_type == 'L':
                if self._listener_socket:
                    try: 
                        # [修改] 强行 shutdown 打断正在阻塞的 accept，然后再 close
                        self._listener_socket.shutdown(socket.SHUT_RDWR)
                    except: pass
                    try: self._listener_socket.close()
                    except: pass
                    self._listener_socket = None
            
            # 3. 清理 Transport 和 R 类型的远程转发
            if self._transport:
                if self.forward_type == 'R':
                    try: self._transport.cancel_port_forward(self.local_bind[0], self.local_bind[1])
                    except: pass
                if self._transport.is_active():
                    self._transport.close()
                self._transport = None
            
            # 4. 清理 SSH Client
            if self._client:
                self._client.close()
                self._client = None

        except Exception as e:
            self.logger.debug(f"Cleanup error (ignorable): {e}")
        finally:
            self.tunnel_enable = False
            # [修改] 移除了原有的未知变量 self._backend_obj = None

    def start(self):
        with self._lock:
            self.user_wants_active = True
            self._monitor_stop_event.clear()
            if not self._monitor_thread or not self._monitor_thread.is_alive():
                self._monitor_thread = threading.Thread(target=self._monitor_loop)
                self._monitor_thread.daemon = True
                self._monitor_thread.start()
            
            try:
                self._do_start_internal_logic()
            except Exception as e:
                self._last_error = str(e)
                self.tunnel_enable = False

    def stop(self):
        with self._lock:
            self.user_wants_active = False
            self._monitor_stop_event.set()
            self._do_stop_internal_logic()
        self.logger.info(f"User stopped tunnel {self.local_bind}")

    def get_tunnel_status(self) -> Dict[str, Any]:
        is_active = self._check_real_status()
        return {
            "tunnel_enable": self.tunnel_enable,
            "user_wants_active": self.user_wants_active,
            "is_active": is_active,
            "local_bind_address": self.local_bind if is_active else None,
            "last_error": self._last_error,
            "type": self.forward_type
        }