# LangGraph A2A Agents

This repository contains two example LangGraph agents that use the Agent-to-Agent (A2A) protocol:

- **Currency Agent**: Provides currency conversion and exchange rate information
- **Element Agent**: Provides information about chemical elements from the periodic table

## Structure

- `0.1/`: Original implementation of the Element Agent
- `0.2/`: Improved implementation with both Currency and Element Agents

## Getting Started

### Prerequisites

- Python 3.10+ (3.13 recommended)
- UV package manager (`pip install uv`)

### Setup

1. Clone this repository and navigate to it
2. Create an environment file with your API key:

   ```bash
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   ```

   Alternatively, you can use a local LLM server and specify its URL in your code.

3. Install dependencies:

   ```bash
   cd 0.2
   uv pip install -e .
   ```

### Running the Agents

We provide convenient scripts to run both agents:

#### Using the helper scripts:

```bash
# Run the Element Agent (default)
./run_agent.sh

# Run the Currency Agent
./run_agent.sh --type currency

# Run on a different port
./run_agent.sh --port 8080
```

#### Directly with UV:

```bash
cd 0.2
uv run . --agent-type element  # For Element Agent
uv run . --agent-type currency  # For Currency Agent
```

### Testing the Agents

You can test the agents using the provided test client:

#### Using the helper script:

```bash
# Test the Element Agent with sample queries
./test_agent.sh

# Test the Currency Agent with sample queries
./test_agent.sh --type currency

# Run a specific query
./test_agent.sh --query "氢元素的信息"

# Use streaming mode
./test_agent.sh --streaming
```

#### Directly with UV:

```bash
cd 0.2
uv run test_client.py --agent-type element
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
