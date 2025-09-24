# A2A Java Example with Ollama Integration (v0.3.0 Compliant)

This project demonstrates the A2A (Agent2Agent) protocol implementation in Java, refactored to support A2A v0.3.0 specification and modified to use local Ollama qwen3:8b model instead of remote OpenAI services.

## Architecture

- **Model**: Data models for A2A protocol messages and types (A2A v0.3.0 compliant)
- **Client**: Consolidated A2A client implementation with both new and legacy method support
  - Core client: `A2AClient.java`
  - Utilities: Moved to `client/util/` package
  - Examples: Moved to `examples/` directory
- **Server**: A2A server implementation using Spring Boot with local Ollama integration

## Key Changes

The original implementation has been modernized and refactored to:

1. **A2A v0.3.0 Compliance**: Updated to use latest A2A protocol methods (`message/send`, `message/list`, `message/stream`)
2. **Official A2A Java SDK Integration**: 
   - Server: Uses `io.github.a2asdk:a2a-java-sdk-reference-jsonrpc:0.3.0.Beta1`
   - Client: Uses `io.github.a2asdk:a2a-java-sdk-client:0.3.0.Beta1`
   - Specification: Uses `io.github.a2asdk:a2a-java-sdk-spec:0.3.0.Beta1`
3. **Direct HTTP calls to Ollama**: Replaced Spring AI ChatModel with direct HTTP client calls to local Ollama API
4. **Local qwen3:8b model**: Uses the qwen3:8b model running on Ollama
5. **Consolidated Client Architecture**: Single main client class with utilities and examples properly organized
6. **Backwards Compatibility**: Legacy method names maintained for smooth migration
7. **Updated Dependencies**: Jackson updated to latest version, official A2A SDK dependencies
8. **Proper Agent Card Endpoint**: Uses `.well-known/agent-card` as per A2A v0.3.0 specification

## Prerequisites

1. Java 21 or higher
2. Maven 3.6 or higher
3. Ollama installed and running locally
4. qwen3:8b model pulled in Ollama

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
# Compile the project
mvn clean compile

# Run the server
mvn spring-boot:run -pl server
```

The server will start on `http://localhost:8080`

### Test the Translation Service

```bash
# Compile and run the test client
cd /Users/han/coding/a2a_google/hello-a2a-examples/hello-a2a-java
javac -cp "client/target/classes:model/target/classes" TestOllamaTranslation.java
java -cp ".:client/target/classes:model/target/classes:client/target/dependency/*" TestOllamaTranslation
```

### Use the A2A Client

```bash
# Run the example client (moved to examples directory)
mvn exec:java -Dexec.mainClass="com.google.a2a.examples.A2AClientExample" -pl examples
```

### Use Host Agent Cli

```bash
cd hello-a2a-java
mvn exec:java -Dexec.mainClass="com.google.a2a.examples.HostAgentCli" -Dexec.args="--auto-start" -pl examples
```

## API Endpoints

- `GET /.well-known/agent-card` - Get agent information (A2A v0.3.0 compliant)
- `POST /a2a` - Send A2A messages using `message/send` method
- `POST /a2a/stream` - Send A2A messages with streaming response using `message/stream`

### Client Methods

**New A2A v0.3.0 Methods:**
- `sendMessage(MessageSendParams)` - Send messages using latest protocol
- `listMessages(TaskQueryParams)` - List messages
- `sendMessageStreaming(MessageSendParams, StreamingEventListener)` - Streaming message sending

**Legacy Methods (backwards compatibility):**
- `sendTask(TaskSendParams)` - Mapped to `sendMessage`
- `getTask(TaskQueryParams)` - Mapped to `listMessages`
- `sendTaskStreaming(TaskSendParams, StreamingEventListener)` - Mapped to `sendMessageStreaming`

## Implementation Details

The server now uses:

- **HttpClient**: Java's built-in HTTP client for Ollama API calls
- **Ollama API**: Direct calls to `http://localhost:11434/api/generate`
- **qwen3:8b model**: Specified in the API request payload

### Key Configuration Changes

1. **A2AServerConfiguration.java**:

   - Removed Spring AI dependencies
   - Added direct Ollama HTTP client implementation
   - Modified TaskHandler to use Ollama API

2. **pom.xml**:

   - Removed Spring AI BOM and starter dependencies
   - Kept core Spring Boot Web functionality

3. **application.properties**:
   - Removed OpenAI configuration properties
   - Kept basic Spring Boot settings

## Error Handling

The implementation includes proper error handling for:

- Ollama service connectivity issues
- Invalid API responses
- Model generation timeouts
- JSON parsing errors

## Performance Considerations

- HTTP client with configurable timeouts (30s connect, 2min request)
- Non-streaming API calls for simplicity
- Concurrent task handling via Spring Boot's embedded server

## Testing

Run the test suite:

```bash
mvn test
```

The test client (`TestOllamaTranslation.java`) demonstrates basic translation functionality.

----

- https://github.com/a2aproject/A2A
- https://a2a-protocol.org/latest