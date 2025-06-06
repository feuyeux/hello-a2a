# Hello Agent2Agent (A2A) Protocol with Ollama Integration

> **A local implementation of Google's Agent2Agent (A2A) Protocol using Ollama qwen3:8b model**

This repository contains A2A protocol implementations in multiple programming languages, all configured to use local Ollama instead of remote AI services.

## Language Implementations

- **[Java](hello-a2a-java/README.md)** - Spring Boot implementation with Ollama integration
- **[Go](hello-a2a-go/README.md)** - Gin framework implementation with Ollama integration
- **[JavaScript](hello-a2a-js/README.md)** - Express.js implementation with Ollama integration
- **[Python](hello-a2a-python/README.md)** - FastAPI implementation with Ollama integration

## Common Prerequisites

1. **Ollama** installed and running locally
2. **qwen3:8b model** pulled in Ollama

### Setup Ollama (Required for all implementations)

```bash
# Install Ollama (if not already installed)
# See https://ollama.com for installation instructions

# Pull the qwen3:8b model
ollama pull qwen3:8b

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

## Key Features

- **Local AI Processing**: All implementations use local Ollama instead of cloud services
- **Unified Model**: All languages use the same qwen3:8b model for consistency
- **A2A Protocol Compliance**: Full compliance with Google's A2A specification
- **Multi-Language Support**: Choose your preferred programming language

## Resources

- 🔗 [A2A Specification and Documentation](https://github.com/google/A2A)
- 🔗 [Agent2Agent (A2A) Samples](https://github.com/google-a2a/a2a-samples)
- 🔗 [A2A Python SDK](https://github.com/google/a2a-python)
