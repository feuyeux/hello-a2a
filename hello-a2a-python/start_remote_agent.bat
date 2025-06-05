@echo off
REM 启动远程代理的脚本 - 专为前端A2A协议交互优化 (Windows Batch版本)
REM 用法: start_remote_agent.bat <agent_type> [--host HOST] [--port PORT] [additional_args]
REM 例如: start_remote_agent.bat google_adk --host localhost --port 10000

setlocal enabledelayedexpansion

REM 获取脚本所在目录的绝对路径
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"

REM 默认配置
set "DEFAULT_HOST=localhost"
set "AGENT_TYPE="
set "HOST=%DEFAULT_HOST%"
set "PORT="
set "EXTRA_ARGS="

REM 显示帮助信息
if "%1"=="" goto :show_help
if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help

REM 解析参数
set "AGENT_TYPE=%1"
shift

:parse_args
if "%1"=="" goto :args_done
if "%1"=="--host" (
    set "HOST=%2"
    shift
    shift
    goto :parse_args
)
if "%1"=="--port" (
    set "PORT=%2"
    shift
    shift
    goto :parse_args
)
if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help

REM 添加到额外参数
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto :parse_args

:args_done

REM 设置默认端口
if "%PORT%"=="" (
    if "%AGENT_TYPE%"=="google_adk" set "PORT=10000"
    if "%AGENT_TYPE%"=="ag2" set "PORT=10001"
    if "%AGENT_TYPE%"=="langgraph" set "PORT=10002"
    if "%AGENT_TYPE%"=="semantickernel" set "PORT=10003"
    if "%AGENT_TYPE%"=="llama_index_file_chat" set "PORT=10004"
    if "%PORT%"=="" set "PORT=8000"
)

REM 验证代理类型
if not exist "%PROJECT_ROOT%\remotes\%AGENT_TYPE%" (
    echo ❌ 错误: 代理类型 '%AGENT_TYPE%' 不存在
    echo.
    echo 可用的代理目录:
    for /d %%d in ("%PROJECT_ROOT%\remotes\*") do echo   %%~nxd
    echo.
    echo 运行 '%0 --help' 查看使用说明
    exit /b 1
)

REM 检查虚拟环境
if not exist "%PROJECT_ROOT%\venv" (
    echo ❌ 错误: 虚拟环境不存在，请先运行：
    echo    python -m venv venv
    echo    venv\Scripts\activate.bat
    echo    pip install -r requirements.txt
    exit /b 1
)

REM 激活虚拟环境
if exist "%PROJECT_ROOT%\venv\Scripts\activate.bat" (
    echo 🔧 激活虚拟环境...
    call "%PROJECT_ROOT%\venv\Scripts\activate.bat"
) else (
    echo ⚠️  警告: 未找到虚拟环境激活脚本，使用系统Python
)

REM 设置PYTHONPATH
set "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"

echo 🚀 启动 A2A 远程代理
echo ┌─────────────────────────────────────────┐
echo │ 代理类型: %AGENT_TYPE%
echo │ 监听地址: %HOST%:%PORT%
echo │ A2A 接口: http://%HOST%:%PORT%
echo │ 项目根目录: %PROJECT_ROOT%
echo └─────────────────────────────────────────┘

REM 切换到项目根目录
cd /d "%PROJECT_ROOT%"

REM 清理端口占用的进程
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% "') do (
    if not "%%p"=="0" (
        taskkill /PID %%p /F >nul 2>&1
    )
)

REM 构建启动命令
set "CMD_ARGS=--host %HOST% --port %PORT%%EXTRA_ARGS%"

echo 🔧 执行命令: python -m remotes.%AGENT_TYPE% %CMD_ARGS%
echo ⏰ %date% %time% - 代理启动中...
echo ─────────────────────────────────────────

REM 启动代理
python -m remotes.%AGENT_TYPE% %CMD_ARGS%
goto :eof

:show_help
echo 🚀 A2A 远程代理启动器
echo.
echo 用法: %0 ^<agent_type^> [options] [additional_args]
echo.
echo 可用的代理类型:
echo   google_adk         - Google ADK 代理 (默认端口: 10000)
echo   ag2                - AG2 代理 (默认端口: 10001)
echo   langgraph          - LangGraph 代理 (默认端口: 10002)
echo   semantickernel     - Semantic Kernel 代理 (默认端口: 10003)
echo   llama_index_file_chat - LlamaIndex 文件聊天代理 (默认端口: 10004)
echo.
echo 选项:
echo   --host HOST        指定主机地址 (默认: localhost)
echo   --port PORT        指定端口号 (如未指定，使用默认端口)
echo   --help, -h         显示此帮助信息
echo.
echo 示例:
echo   %0 google_adk                           # 使用默认配置启动
echo   %0 ag2 --port 10011                    # 使用自定义端口
echo   %0 semantickernel --host 0.0.0.0       # 绑定所有接口
echo.
echo 注意:
echo   - 代理启动后，前端可通过 http://HOST:PORT 访问A2A接口
echo   - 在前端Agent页面中添加代理地址进行注册
exit /b 0
