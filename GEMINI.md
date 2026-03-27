# 项目概览

本项目是一个基于 Python Flask 框架开发的 Web 应用，旨在提供一个 Web 界面的 SSH 隧道管理解决方案。它允许用户通过浏览器添加、修改、启动、停止和删除 SSH 隧道，并管理 SSH 用户凭据。核心功能利用 `paramiko` 库实现 SSH 隧道连接，支持本地（Local）和远程（Remote）端口转发。

**主要技术栈:**

*   **后端框架:** Flask
*   **SSH 隧道库:** Paramiko
*   **数据持久化:** JSON 文件 (`user.json`, `tunnel_info.json`)
*   **前端:** HTML, CSS, JavaScript (内联)
*   **Web 模板:** Jinja2 (`templates/` 目录)
*   **开发语言:** Python 3.12
*   **打包:** PyInstaller (用于生成单个可执行文件)

**项目结构与核心组件:**

*   **`app.py`**: Flask 应用的主入口。负责处理 Web 请求，定义 RESTful API 端点，管理用户会话（尽管当前实现中自动登录），并协调 `TunnelController` 和 `ModelManager` 的操作。
*   **`tunnel_manager.py`**: 实现了 `ParamikoTunnel` 类，这是建立和管理 SSH 隧道的底层核心。它封装了 Paramiko 的连接、端口转发逻辑，并包含隧道健康监控和自动重连机制。
*   **`tunnel_control.py`**: 作为应用逻辑层，它管理 `ParamikoTunnel` 实例的生命周期。负责根据 `ModelManager` 获取的配置创建、启动、停止隧道，并提供状态查询接口。
*   **`models.py`**: 数据管理模块。负责读写 `user.json` (用于管理员和 SSH 用户凭据) 和 `tunnel_info.json` (用于隧道配置)。实现了用户添加、删除、密码修改以及隧道信息的增删改查和排序功能。
*   **`user.json`**: 存储管理员认证信息（`auth`）和 SSH 用户凭据（`user`）。密码以 Base64 编码存储。
*   **`tunnel_info.json`**: 存储所有 SSH 隧道的配置信息，包括连接详情、绑定地址、类型（L/R）等。
*   **`templates/manage.html`**: 主要的 Web 界面，用于管理用户、添加/编辑/删除/排序隧道，并显示隧道状态。包含内联 CSS 和 JavaScript 实现界面交互。
*   **`templates/login.html`**: 基础的登录页面，用于管理员登录。
*   **`run_test.sh`**: 自动化脚本，用于启动 Flask 服务器，然后运行测试用例 (`test_case_d_l.py`)，最后清理资源。
*   **`build_binary.sh`**: 使用 PyInstaller 将应用打包成一个独立的（--onefile）可执行文件，包含所有依赖项（如 `paramiko`）和资源（如 `templates/` 目录）。
*   **`cert.pem`, `key.pem`**: SSL 证书文件，表明项目计划支持 HTTPS 连接。

**核心功能亮点:**

*   **SSH 隧道管理:** 支持本地 (`-L`) 和远程 (`-R`) 端口转发，通过 Paramiko 实现。
*   **隧道健康监控:** `ParamikoTunnel` 包含自动监控和重连机制，以保持隧道活跃。
*   **Web 界面:** 提供用户友好的界面来配置和管理隧道及用户。
*   **数据持久化:** 所有配置和凭据（密码 Base64 编码）均保存到 JSON 文件。
*   **用户管理:** 支持添加、删除 SSH 用户，并检查关联性。管理员密码修改功能也已实现。
*   **打包为可执行文件:** `build_binary.sh` 提供了将应用打包为独立可执行文件的能力。

**构建与运行:**

*   **运行 Web 服务器:**
    ```bash
    python3 app.py
    ```
    服务器默认监听在 `0.0.0.0:8443`。
*   **运行自动化测试:**
    ```bash
    ./run_test.sh
    ```
    此脚本会启动服务器，执行测试，然后关闭服务器。
*   **构建独立可执行文件:**
    ```bash
    ./build_binary.sh
    ```
    成功后，将在 `dist/` 目录下生成 `ssh-tunnel` 可执行文件。

**开发与代码规范（推测）:**

*   **Python:** 遵循 PEP 8 规范（推测）。
*   **前端:** 使用基础 HTML, CSS, JavaScript，注重布局和响应式设计。
*   **并发:** 使用 Python 的 `threading` 模块处理并发的隧道操作。
*   **日志:** 使用 Python 内置 `logging` 模块。
*   **错误处理:** 通过 try-except 块、日志记录和 API 返回的错误信息进行处理。
*   **安全:** 密码使用 Base64 编码存储，HTTPS 支持（通过证书文件）。

**项目目标:**

提供一个稳定、易于使用的 SSH 隧道管理工具，通过 Web 界面简化复杂网络连接的配置和维护，并能打包成独立可执行文件方便部署。
