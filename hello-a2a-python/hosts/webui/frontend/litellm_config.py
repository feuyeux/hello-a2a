"""litellm configuration for the A2A demo UI
This file configures the litellm client to use local LLM through Ollama
"""

# Configuration for Ollama-based local LLM
config = {
    "model": "ollama_chat/qwen3:0.6b",
    "api_base": "http://localhost:11434/v1",
    "api_key": "sk-ollama-local",  # placeholder, not required for Ollama
    "format": "chat",
    "additional_kwargs": {
        "force_json": True,
        "message_formatter": "string"  # This ensures content is passed as string
    }
}

# Verify if Ollama service is available
def check_ollama_service() -> bool:
    """Check if Ollama service is available"""
    import httpx
    try:
        response = httpx.get("http://localhost:11434/api/version", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False

if __name__ == "__main__":
    # When running this script directly, verify Ollama service
    if check_ollama_service():
        print("✅ Ollama service is running")
    else:
        print("❌ Ollama service is not available at http://localhost:11434")
        print("Please install and start Ollama: https://ollama.com/download")
