# A2A Java Example with Ollama Integration

This project demonstrates the A2A (Agent2Agent) protocol implementation in Java, modified to use local Ollama qwen3:8b model instead of remote OpenAI services.

## Architecture

- **Model**: Data models for A2A protocol messages and types
- **Client**: A2A client implementation for sending requests to A2A servers
- **Server**: A2A server implementation using Spring Boot with local Ollama integration

## Key Changes

The original implementation used Spring AI with OpenAI APIs. This has been modified to:

1. **Direct HTTP calls to Ollama**: Replaced Spring AI ChatModel with direct HTTP client calls to local Ollama API
2. **Local qwen3:8b model**: Uses the qwen3:8b model running on Ollama
3. **Removed dependencies**: Eliminated Spring AI dependencies from the project

## Prerequisites

1. Java 17 or higher
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
# Run the example client
mvn exec:java -Dexec.mainClass="com.google.a2a.client.A2AClientExample" -pl client
```

## API Endpoints

- `GET /.well-known/agent-card` - Get agent information
- `POST /a2a` - Send A2A tasks
- `POST /a2a/stream` - Send A2A tasks with streaming response

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
