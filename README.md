# Jenkins MCP Server

基于 **FastMCP** + **SSE (HTTP)** 协议的 Jenkins CI MCP 服务器。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量
export JENKINS_URL=http://your-jenkins:8080
export JENKINS_USER=your-username
export JENKINS_PASSWORD=your-api-token

# 3. 启动服务
python jenkins.py
```

服务运行在 **`http://0.0.0.0:8080`**，使用 SSE 传输协议。

## 工具列表

| 工具 | 说明 | 参数 |
|------|------|------|
| `trigger_build` | 触发构建（支持参数） | `jobname`, `params` (JSON) |
| `stop_build` | 停止运行中的构建 | `jobname`, `build_number` |
| `get_job` | 获取 Job 详情 | `jobname` |
| `get_jobs` | 获取所有 Job 列表 | *(无)* |
| `get_build` | 获取构建元数据（参数、SCM 信息、状态） | `jobname`, `build_number?` |
| `get_build_logs` | 获取构建日志（支持 tail） | `jobname`, `build_number?`, `tail_lines?` |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JENKINS_URL` | `http://localhost:8080` | Jenkins 服务器地址 |
| `JENKINS_USER` | *(空)* | Jenkins 用户名 |
| `JENKINS_PASSWORD` | *(空)* | Jenkins API Token 或密码 |
| `JENKINS_CA_BUNDLE` | *(空)* | 自定义 CA 证书路径 (TLS) |
