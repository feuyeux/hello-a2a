# LangGraph A2A Agents

This project contains two example LangGraph agents that can be run using the A2A protocol:

1. **Currency Agent**: Helps with currency conversion and exchange rates
2. **Element Agent**: Provides information about chemical elements from the periodic table

## Getting started

### Prerequisites

- Python 3.10+ (3.13 recommended)
- UV package manager (`pip install uv`)

### Setup

1. Create an environment file with your API key:

   ```bash
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   ```

   Alternatively, you can use a local LLM server and specify its URL in your code or environment.

2. Install dependencies:

   ```bash
   uv pip install -e .
   ```

### Running the Server

You can run either the Currency Agent or the Element Agent:

#### Currency Agent

```bash
uv run . --agent-type currency
```

#### Element Agent (default)

```bash
uv run .
```

Or explicitly specify:

```bash





> 在两个终端，依次执行 `uv run . --agent-type element` 和 `uv run test_client.py`，启动过程如果遇到问题，先停下来解决问题。
> 执行过程如果遇到问题，立即解决。

```

### Additional Options

You can customize the host and port for the server:ada

```bash
uv run . --host 0.0.0.0 --port 8080 --agent-type currency
```

### Testing the Agent

Run the test client to interact with the running agent:

```bash
uv run test_client.py
```

## Agent Capabilities

### Currency Agent

The Currency Agent can provide exchange rates between different currencies using a public API.

Example queries:

- "What is the exchange rate from USD to EUR?"
- "Convert 100 JPY to GBP"

### Element Agent

The Element Agent provides information about chemical elements from the periodic table.

Example queries:

- "Tell me about hydrogen"
- "What are the properties of carbon?"
- "Information about Fe and Cu"
- "氢元素的信息" (Information about hydrogen element)
