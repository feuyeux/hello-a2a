# A2A Go Example with Ollama Integration (v0.3.0 Compliant)

This project demonstrates the A2A (Agent2Agent) protocol implementation in Go, updated to support A2A v0.3.0 specification and integrated with local Ollama qwen3:8b model for translation services.

## Architecture

- **models/**: Data models for A2A protocol messages and types (a2a.go, jsonrpc.go, task.go)
- **client/**: A2A client implementation for sending requests to A2A servers
- **server/**: A2A server framework implementation
- **cmd/server/**: Main server application with Ollama integration
- **cmd/client/**: Demo client with translation test cases

## Key Features

This implementation provides:

1. **A2A v0.3.0 Protocol Support**: Complete JSON-RPC over HTTP implementation with latest method names
2. **Local Ollama Integration**: Direct HTTP calls to local Ollama API (qwen3:8b model)
3. **Translation Service**: Multi-language translation capabilities
4. **Streaming Support**: Both regular and streaming response modes
5. **Agent Discovery**: Standard `.well-known/agent-card` endpoint
6. **Backwards Compatibility**: Legacy method names maintained for smooth migration
7. **Improved Error Handling**: Enhanced error recovery and timeout management

## Prerequisites

1. Go 1.21 or higher
2. Ollama installed and running locally
3. qwen3:8b model pulled in Ollama

### Setup Ollama

```bash
# Install Ollama (if not already installed)
# See https://ollama.com for installation instructions

# Pull the qwen3:8b model
ollama pull qwen3:8b

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

## Running the Application

### Start the A2A Server

```bash
# Install dependencies
go mod tidy

# Run the server
go run cmd/server/main.go
```

The server will start on `http://localhost:8080` and provide:

- Translation services via A2A protocol
- Agent discovery endpoint
- Both regular and streaming response modes

### Test with Demo Client

```bash
# Run the demo client with translation test cases
go run cmd/client/main.go
```

This will test translations from Chinese, French, Spanish, Japanese, and Korean to English.

### Use the A2A Client Library

```bash
# Example using the client library directly
go run -c "
package main
import (
    \"fmt\"
    \"github.com/example/hello-a2a-go/client\"
)
func main() {
    c := client.NewA2AClient(\"http://localhost:8080\")
    // Use client methods here
    fmt.Println(c.GetAgentCard())
}"
```

## API Endpoints

- `GET /.well-known/agent-card` - Get agent information and capabilities (A2A v0.3.0 compliant)
- `POST /a2a` - Send A2A messages using `message/send` method (JSON-RPC format)
- `POST /a2a/stream` - Send A2A messages with streaming response using `message/stream`

### Legacy Support
The following methods are also supported for backwards compatibility:
- `tasks/send` - Mapped to `message/send`
- `tasks/get` - Mapped to `message/list`
- `tasks/cancel` - Mapped to `message/pending`

## Example Translation Results

The demo client successfully tests these translations:

```
Chinese: "你好世界" → "Hello world"
French: "Bonjour le monde" → "Hello world"
Spanish: "Hola mundo" → "Hello world"
Japanese: "こんにちは世界" → "Hello world"
Korean: "안녕하세요 세계" → "Hello world"
```

Response times: ~5-10 seconds per translation using qwen3:8b model.

## Implementation Details

The project structure includes:

- **cmd/server/main.go**: Main server application with Ollama integration
- **cmd/client/main.go**: Demo client with translation test cases
- **server/server.go**: A2A server framework (332 lines)
- **client/client.go**: A2A client library (205 lines)
- **models/**: Protocol definitions (a2a.go, jsonrpc.go, task.go, etc.)

### Technical Implementation

- **JSON-RPC over HTTP**: Full A2A protocol compliance with proper request IDs
- **Ollama Integration**: Direct HTTP calls to `http://localhost:11434/api/generate`
- **qwen3:8b Model**: Specified in API request payload for translation tasks
- **Error Handling**: Comprehensive error recovery and timeout management
- **Streaming Support**: Both regular and streaming response modes

### Key Configuration

1. **cmd/server/main.go**:

   - Ollama API integration with translation prompt engineering
   - A2A server setup with agent card configuration
   - HTTP endpoints for protocol compliance

2. **client/client.go**:
   - Fixed JSON-RPC request ID issues
   - Proper task status handling
   - Both regular and streaming request support

## Error Handling

The implementation includes proper error handling for:

- Ollama service connectivity issues
- Invalid API responses
- Model generation timeouts
- JSON parsing errors

## Performance Considerations

- HTTP client with configurable timeouts (30s connect, 2min request)
- Non-streaming API calls for simplicity
- Concurrent request handling via Gin framework

## Testing

### Demo Client Testing

```bash
# Run the comprehensive demo client
go run cmd/client/main.go
```

This tests:

- 5 different language translations to English
- Both regular and streaming response modes
- Error handling and recovery
- Agent card discovery

### Manual Testing

```bash
# Test agent card endpoint
curl http://localhost:8080/.well-known/agent-card

# Test translation via A2A protocol
curl -X POST http://localhost:8080/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "sendTask",
    "params": {
      "task": {
        "id": "test-123",
        "status": "pending"
      },
      "instructions": "Translate to English: Bonjour le monde"
    },
    "id": "req-123"
  }'
```

### Unit Tests

```bash
# Run unit tests (if available)
go test ./...
```

MIT License
