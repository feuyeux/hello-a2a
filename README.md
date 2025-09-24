# Hello Agent2Agent (A2A) Protocol v0.3.0 with Ollama Integration

> **A modernized implementation of Google's Agent2Agent (A2A) Protocol v0.3.0 using Ollama qwen3:8b model**

This repository contains refactored A2A protocol implementations in multiple programming languages, all updated to support the latest A2A v0.3.0 specification and configured to use local Ollama instead of remote AI services.

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

- **A2A v0.3.0 Compliance**: Full compliance with the latest A2A specification including `message/send`, `message/list`, and `message/stream` methods
- **Modernized Architecture**: Streamlined client implementations with reduced code duplication
- **Local AI Processing**: All implementations use local Ollama instead of cloud services
- **Unified Model**: All languages use the same qwen3:8b model for consistency
- **Backwards Compatibility**: Legacy method names still supported for smooth migration
- **Multi-Language Support**: Choose your preferred programming language

## Resources

- 🔗 [A2A Protocol v0.3.0 Specification](https://a2a-protocol.org/latest/)
- 🔗 [Official A2A SDK Documentation](https://a2a-protocol.org/latest/sdk/)
- 🔗 [A2A Java SDK (io.github.a2asdk)](https://github.com/a2a-protocol/a2a-java-sdk)
- 🔗 [A2A Protocol Examples and Samples](https://github.com/a2a-protocol/samples)