# Startup script for A2A remote agents - Windows PowerShell version
# Usage: .\start_remote_agent.ps1 <agent_type> [-Host HOST] [-Port PORT] [additional_args]
# Example: .\start_remote_agent.ps1 google_adk -Host localhost -Port 10000

param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$AgentType,
    
    [string]$HostAddress = "localhost",
    [int]$Port = 0,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$ExtraArgs = @()
)

# Get script directory absolute path
$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$ProjectRoot = $ScriptDir

# Default port configuration
$DefaultPorts = @{
    "google_adk" = 10000
    "ag2" = 10001
    "langgraph" = 10002
    "semantickernel" = 10003
    "llama_index_file_chat" = 10004
}

# Help information
function Show-Help {
    Write-Host "A2A Remote Agent Launcher" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\start_remote_agent.ps1 <agent_type> [options] [additional_args]"
    Write-Host ""
    Write-Host "Available agent types:" -ForegroundColor Yellow
    Write-Host "  google_adk         - Google ADK Agent (default port: 10000)"
    Write-Host "  ag2                - AG2 Agent (default port: 10001)"
    Write-Host "  langgraph          - LangGraph Agent (default port: 10002)"
    Write-Host "  semantickernel     - Semantic Kernel Agent (default port: 10003)"
    Write-Host "  llama_index_file_chat - LlamaIndex File Chat Agent (default port: 10004)"
    Write-Host ""    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  -HostAddress HOST  Specify host address (default: localhost)"
    Write-Host "  -Port PORT         Specify port number (uses default if not specified)"
    Write-Host "  -Help              Show this help information"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\start_remote_agent.ps1 google_adk                              # Start with default config"
    Write-Host "  .\start_remote_agent.ps1 ag2 -Port 10011                        # Use custom port"
    Write-Host "  .\start_remote_agent.ps1 semantickernel -HostAddress 0.0.0.0    # Bind all interfaces"
    Write-Host ""
    Write-Host "Notes:" -ForegroundColor Magenta
    Write-Host "  - After startup, frontend can access A2A interface via http://HOST:PORT"
    Write-Host "  - Add agent address in frontend Agent page for registration"
}

# Get default port
function Get-DefaultPort {
    param([string]$AgentType)
    
    if ($DefaultPorts.ContainsKey($AgentType)) {
        return $DefaultPorts[$AgentType]
    }
    return 8000 # fallback
}

# Check parameters
if (-not $AgentType -or $Help) {
    Show-Help
    exit 0
}

# If no port specified, use default port
if ($Port -eq 0) {
    $Port = Get-DefaultPort -AgentType $AgentType
}

# Validate agent type
$RemotesDir = Join-Path $ProjectRoot "remotes"
$AgentDir = Join-Path $RemotesDir $AgentType

if (-not (Test-Path $AgentDir -PathType Container)) {
    Write-Host "Error: Agent type '$AgentType' does not exist" -ForegroundColor Red
    Write-Host ""
    Write-Host "Available agent directories:" -ForegroundColor Yellow
    
    if (Test-Path $RemotesDir) {
        Get-ChildItem -Path $RemotesDir -Directory | ForEach-Object {
            Write-Host "  $($_.Name)"
        }
    }
    
    Write-Host ""
    Write-Host "Run '.\start_remote_agent.ps1 -Help' for usage instructions"
    exit 1
}

# Check virtual environment
$VenvDir = Join-Path $ProjectRoot "venv"
$VenvActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"

if (-not (Test-Path $VenvDir -PathType Container)) {
    Write-Host "Error: Virtual environment does not exist. Please run first:" -ForegroundColor Red
    Write-Host "   python -m venv venv" -ForegroundColor Yellow
    Write-Host "   .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "   pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

# Activate virtual environment
if (Test-Path $VenvActivateScript) {
    Write-Host "Activating virtual environment..." -ForegroundColor Blue
    & $VenvActivateScript
} else {
    Write-Host "Warning: Virtual environment activation script not found, using system Python" -ForegroundColor Yellow
}

# Set PYTHONPATH
$env:PYTHONPATH = "$ProjectRoot;$env:PYTHONPATH"

Write-Host "Starting A2A Remote Agent" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray
Write-Host "Agent Type: $AgentType" -ForegroundColor White
Write-Host "Listen Address: $HostAddress`:$Port" -ForegroundColor White
Write-Host "A2A Interface: http://$HostAddress`:$Port" -ForegroundColor White
Write-Host "Project Root: $ProjectRoot" -ForegroundColor White
Write-Host "----------------------------------------" -ForegroundColor Gray

# Change to project root directory
Set-Location $ProjectRoot

# Build startup command arguments
$CmdArgs = @("--host", $HostAddress, "--port", $Port.ToString())
if ($ExtraArgs.Count -gt 0) {
    $CmdArgs += $ExtraArgs
}

# Kill processes occupying the port
try {
    $ProcessesToKill = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | 
                      Select-Object -ExpandProperty OwningProcess | 
                      Sort-Object -Unique
    
    if ($ProcessesToKill) {
        Write-Host "Cleaning up processes on port $Port..." -ForegroundColor Yellow
        $ProcessesToKill | ForEach-Object {
            try {
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            } catch {
                # Ignore errors, process may have already ended
            }
        }
        Start-Sleep -Seconds 1
    }
} catch {
    # Ignore errors, port may not be occupied
}

$ModuleName = "remotes.$AgentType"
$CmdArgsString = $CmdArgs -join " "

Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - Agent starting..." -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Gray

# Start agent - use module approach to support relative imports
try {
    & python -m $ModuleName @CmdArgs
} catch {
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
