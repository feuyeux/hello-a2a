# A2A JavaScript Example with Local Ollama Integration

This project demonstrates the A2A (Agent2Agent) protocol implementation in JavaScript/Node.js, completely migrated from cloud services to use local Ollama AI models. The project now features two specialized agents that operate entirely offline.

## 🏗️ Architecture

- **Client**: A2A client implementation for communicating with agents
- **Server**: Express.js-based A2A servers with local Ollama integration
- **Agents**: Two specialized AI agents powered by local Ollama models
  - **Coder Agent**: Generates code files and programming solutions
  - **Movie Agent**: Provides movie recommendations and discussions

## 📋 Prerequisites

1. **Node.js 18+** and npm package manager
2. **Ollama** installed and running locally
3. **qwen3:8b model** (or any compatible Qwen model)

## 🛠️ Installation & Setup

```bash
# Clone and navigate to the project
cd hello-a2a-js

# Install dependencies
npm install

# Verify Ollama setup
npm run check-ollama
```

## 🎯 Quick Start

### 1. Start the Agents

```bash
# Terminal 1: Start the Coder Agent (port 41242)
npm run coder

# Terminal 2: Start the Movie Agent (port 41241)
npm run movie
```

### 2. Test with Client

```bash
# Test both agents
npm run client both

# Test specific agents
npm run client coder    # Test code generation
npm run client movie    # Test movie recommendations
```

## 🤖 Available Agents

### Coder Agent (Port 41242)

- **Purpose**: Generates code, scripts, and programming solutions
- **Capabilities**:
  - Creates complete code files with documentation
  - Supports multiple programming languages
  - Provides test cases and examples
  - Returns code as downloadable artifacts

**Example Request**: "Write a Python function that calculates fibonacci numbers"

### Movie Agent (Port 41241)

- **Purpose**: Movie discussions and recommendations
- **Capabilities**:
  - Recommends movies by genre, year, or theme
  - Discusses plot, characters, and cinematography
  - Provides detailed movie analysis
  - No external API dependencies

**Example Request**: "Recommend some good sci-fi movies from the last 10 years"

## 📡 API Endpoints

### Coder Agent (`http://localhost:41242`)

- `GET /.well-known/agent.json` - Agent card and capabilities
- `POST /a2a/messages` - Send code generation requests
- `POST /a2a/tasks/{taskId}` - Get task status and results

### Movie Agent (`http://localhost:41241`)

- `GET /.well-known/agent.json` - Agent card and capabilities
- `POST /a2a/messages` - Send movie discussion requests
- `POST /a2a/tasks/{taskId}` - Get task status and results

## 🔧 Available Scripts

| Script                  | Description                           |
| ----------------------- | ------------------------------------- |
| `npm start`             | Start the Coder Agent on port 41242   |
| `npm run coder`         | Start the Coder Agent specifically    |
| `npm run movie`         | Start the Movie Agent on port 41241   |
| `npm run client [test]` | Test client (both/coder/movie)        |
| `npm run check-ollama`  | Verify Ollama installation and models |
| `npm test`              | Run the simple CLI test client        |

## 🏛️ Project Structure

```
src/
├── agents/
│   ├── coder/
│   │   ├── index.ts              # Coder agent server
│   │   ├── ollama-client.ts      # Ollama HTTP client
│   │   └── simple-code-format.ts # Code parsing utilities
│   └── movie-agent/
│       └── simple-index.ts       # Movie agent server
├── client/
│   └── client.ts                 # A2A client implementation
├── server/                       # Shared server utilities
├── schema.ts                     # A2A protocol types
└── simple-cli.ts                 # Test CLI client
```

## 🔧 Technical Implementation

### Local Ollama Integration

- **Direct HTTP calls** to Ollama API (`http://localhost:11434`)
- **No external dependencies** - completely self-contained
- **qwen3:8b model** for natural language processing
- **Health checks** to ensure Ollama connectivity

### Code Generation Features

- **File artifact creation** - generates actual downloadable files
- **Multi-language support** - Python, JavaScript, TypeScript, etc.
- **Documentation generation** - includes comments and docstrings
- **Test case creation** - provides example usage and tests

### Architecture Benefits

- **Zero cloud costs** - runs entirely on local hardware
- **Privacy-first** - no data sent to external services
- **Fast responses** - local model inference
- **Offline capable** - works without internet connection

## 🚨 Troubleshooting

### Common Issues

**Ollama Connection Error**

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if not running
ollama serve
```

**Model Not Found**

```bash
# Pull the required model
ollama pull qwen3:8b

# List available models
ollama list
```

**Port Already in Use**

```bash
# Check what's using the ports
lsof -i :41241
lsof -i :41242

# Kill processes if needed
pkill -f "tsx src/agents"
```

**Dependencies Issues**

```bash
# Clean install
rm -rf node_modules package-lock.json
npm install
```

## 🧪 Example Usage

### Generate Python Code

```bash
# Start coder agent
npm run coder

# In another terminal, test
npm run client coder
# Request: "Write a Python function to sort a list using quicksort"
```

### Get Movie Recommendations

```bash
# Start movie agent
npm run movie

# In another terminal, test
npm run client movie
# Request: "Recommend horror movies from the 2020s"
```

## 🔍 Migration Notes

This project was migrated from cloud-based services to local Ollama:

**Removed:**

- ❌ Google Gemini API integration
- ❌ TMDB API dependencies
- ❌ Environment variable requirements
- ❌ External API rate limits

**Added:**

- ✅ Local Ollama HTTP client
- ✅ Code parsing utilities
- ✅ File artifact generation
- ✅ Health check mechanisms
- ✅ Simplified agent architecture

## 📝 License

This project is part of the A2A protocol examples and is available under the same license terms.
