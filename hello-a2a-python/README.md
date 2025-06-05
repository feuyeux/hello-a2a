# Agent2Agent (A2A) Protocol - Local Implementation

> **A local implementation of Google's Agent2Agent (A2A) Protocol using local LLMs with multi-agent collaboration**

- 🔗 [A2A Specification and Documentation](https://github.com/google/A2A)
- 🔗 [Agent2Agent (A2A) Samples](https://github.com/google-a2a/a2a-samples)
- 🔗 [A2A Python SDK](https://github.com/google/a2a-python)

This project demonstrates a complete A2A ecosystem where different AI frameworks work together:

- **Travel Agent** (Semantic Kernel) orchestrates complex travel planning by calling other agents
- **Currency Agent** (LangGraph) provides real-time currency conversion services
- **YouTube Agent** (AG2+MCP) extracts video content for travel research
- **Reimbursement Agent** (Google ADK) handles expense workflows with forms
- **File Chat Agent** (LlamaIndex) enables document-based conversations with file uploads

🎯 **Key Achievement**: Real cross-agent communication using A2A JSON-RPC protocol with local LLMs!

## Project Structure

```
a2a-examples-local0/
├── requirements.txt          # All dependencies managed via pip
├── hosts/                    # Host applications
│   ├── cli/                 # CLI host (simplified, no push notifications)
│   └── webui/               # Web UI host
│       ├── frontend/        # Frontend application
│       └── backend/         # Web UI backend
└── remotes/                  # Remote agent implementations
    ├── langgraph/           # LangGraph agent
    ├── ag2/                 # AG2 agent
    ├── google_adk/          # Google ADK agent
    ├── semantickernel/      # Semantic Kernel agent
    └── llama_index_file_chat/ # LlamaIndex agent
```

## Prerequisites

1. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

### Local LLM Services

| Service       | Installation                              | Verification                                                     |
| ------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| **Ollama**    | [Download](https://ollama.com/install.sh) | `curl -s http://localhost:11434/api/tags \| jq '.models[].name'` |
| **LM Studio** | [Download](https://lmstudio.ai/)          | `curl -s http://localhost:1234/v1/models \| jq '.data[].id'`     |

## Remote & Host Agent List

| Agent                   | Framework       | Port  | Purpose                              |
| :---------------------- | :-------------- | :---- | :----------------------------------- |
| **Currency Agent**      | LangGraph       | 10000 | Real-time currency conversion        |
| **YouTube Agent**       | AG2 + MCP       | 10010 | Video transcript analysis            |
| **Reimbursement Agent** | Google ADK      | 10020 | Expense processing with forms        |
| **Travel Agent**        | Semantic Kernel | 10030 | Trip planning with currency          |
| **File Chat Agent**     | LlamaIndex      | 10040 | Document parsing & Q&A               |
| **Host Agent**          | Google ADK      | -     | Task orchestration & agent selection |

## Remote Agents

### 1 Currency Agent

#### Langgraph API

https://python.langchain.com/docs/integrations/providers/openai/

`remotes/langgraph/agent.py`

```python
class CurrencyAgent:
    self.model = ChatOpenAI(
        model=model_name,
        base_url=base_url,
    )
```

#### Tools of Currency Agent

[frankfurter](https://github.com/lineofflight/frankfurter)

```sh
http -b https://api.frankfurter.dev/v1/currencies
```

```sh
http -b "https://api.frankfurter.dev/v1/latest?from=USD&to=CNY&amount=100"
http -b "https://api.frankfurter.app/latest?from=USD&to=CNY&amount=100"
```

#### Start Currency Agent

```bash
# With LM Studio (default)
./start_remote_agent.sh langgraph --host localhost --port 10000 --llm-provider lmstudio --model-name qwen3-8b
# With Ollama
./start_remote_agent.sh langgraph --host localhost --port 10000 --llm-provider ollama --model-name qwen3:8b
```

#### Agent Card of Currency Agent

```bash
http --body http://localhost:10000/.well-known/agent.json
```

```json
{
  "capabilities": {
    "pushNotifications": true,
    "streaming": true
  },
  "defaultInputModes": ["text", "text/plain"],
  "defaultOutputModes": ["text", "text/plain"],
  "description": "Helps with exchange rates for currencies",
  "name": "Currency Agent",
  "skills": [
    {
      "description": "Helps with exchange values between various currencies",
      "examples": ["What is exchange rate between USD and GBP?"],
      "id": "convert_currency",
      "name": "Currency Exchange Rates Tool",
      "tags": ["currency conversion", "currency exchange"]
    }
  ],
  "url": "http://localhost:10000/",
  "version": "1.0.0"
}
```

#### User Case of Currency Agent

```bash
http POST localhost:10000 \
  Content-Type:application/json \
  jsonrpc="2.0" \
  id:=1 \
  method="message/send" \
  params:='{
    "id": "129",
    "sessionId": "test-session",
    "acceptedOutputModes": ["text"],
    "message": {
      "messageId": "msg-01",
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "Convert 100 USD to CNY"
      }]
    }
  }' | jq '.result.artifacts'
```

```json
[
  {
    "artifactId": "e08874b6-3d66-45e1-ab45-cff0633a91ac",
    "name": "conversion_result",
    "parts": [
      {
        "kind": "text",
        "text": "根据最新汇率，100美元兑换人民币为719.98元（汇率：1 USD = 7.1998 CNY）"
      }
    ]
  }
]
```

### 2 YouTube Agent

#### AG2(AutoGen) API

- https://docs.ag2.ai/latest/docs/user-guide/models/lm-studio/
- https://docs.ag2.ai/latest/docs/user-guide/models/ollama/

`remotes/ag2/agent.py`

```python
class YoutubeMCPAgent:
  llm_config = LLMConfig(
      model="qwen3-8b",
      api_type="openai",
      base_url="http://localhost:1234/v1",
      api_key="lm-studio"
  )

  llm_config = LLMConfig(
      model="qwen3:8b",
      api_type="ollama",
      client_host="http://localhost:11434",
  )

  self.agent = AssistantAgent(
      name='YoutubeMCPAgent',
      llm_config=llm_config,
  )
```

#### Mcp Server of YouTube Agent

<https://github.com/sparfenyuk/mcp-youtube>

```bash
uv tool install git+https://github.com/sparfenyuk/mcp-youtube
$HOME/.local/share/uv/tools/mcp-youtube/bin/mcp-youtube --help
```

#### Start YouTube Agent

```bash
# With LM Studio (default)
./start_remote_agent.sh ag2 --host localhost --port 10010 --llm-provider lmstudio --model-name qwen3-30b-a3b
# With Ollama
./start_remote_agent.sh ag2 --host localhost --port 10010 --llm-provider ollama --model-name qwen3:30b-a3b
```

#### Agent Card of YouTube Agent

```bash
http -b http://localhost:10010/.well-known/agent.json
```

```json
{
  "capabilities": {
    "streaming": true
  },
  "defaultInputModes": ["text", "text/plain"],
  "defaultOutputModes": ["text", "text/plain"],
  "description": "AI agent that can extract closed captions and transcripts from YouTube videos. This agent provides raw transcription data that can be used for further processing.",
  "name": "YouTube Captions Agent",
  "skills": [
    {
      "description": "Retrieve closed captions/transcripts from YouTube videos",
      "examples": [
        "Extract the transcript from this YouTube video: https://www.youtube.com/watch?v=xxxxxx",
        "Download the captions for this YouTube tutorial"
      ],
      "id": "download_closed_captions",
      "name": "Download YouTube Closed Captions",
      "tags": ["youtube", "captions", "transcription", "video"]
    }
  ],
  "url": "http://localhost:10010/",
  "version": "1.0.0"
}
```

#### User Case of YouTube Agent

```bash
http -b POST localhost:10010 \
  Content-Type:application/json \
  jsonrpc="2.0" \
  id:=1 \
  method="message/send" \
  params:='{
    "id": "921",
    "sessionId": "test-session",
    "acceptedOutputModes": ["text"],
    "message": {
      "messageId": "msg-01",
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "Please download the captions from this YouTube video and provide a summary based on the content: https://www.youtube.com/watch?v=4pYzYmSdSH4"
      }]
    }
  }'| jq '.result.artifacts'
```

```json
[
  {
    "artifactId": "a4b4e4a8-7900-4cb5-b6c0-a5ab3602df20",
    "description": "智能体请求的结果。",
    "name": "current_result",
    "parts": [
      {
        "kind": "text",
        "text": "{\n  \"text_reply\": \"Here are the captions for the YouTube video along with a summary of the content: The discussion covers advancements in multi-agent systems, where collaboration between different teams' AI agents remains challenging but promising. It addresses 'vibe coding' as a growing practice using AI tools to enhance productivity, though it requires technical understanding despite its name. The speaker also shares insights on starting AI-funded startups, emphasizing speed, technical expertise, and the importance of combining business acumen with deep technology knowledge.\",\n  \"closed_captions\": \"[Captions downloaded successfully]\"\n}"
      }
    ]
  }
]
```

### 3 Reimbursement Agent

#### Google ADK API

- https://google.github.io/adk-docs/agents/models/#using-ollama_chat_provider
- https://google.github.io/adk-docs/agents/models/#using-openai-provider

`remotes/google_adk/agent.py`

```python
class ReimbursementAgent(AgentWithTaskManager):
    return LlmAgent(
        model=LiteLlm(
            model="openai/qwen3-8b",
            api_base="http://localhost:1234/v1",
            api_key="lm-studio"
        ),
    )
```

#### Start Reimbursement Agent

```bash
# With LM Studio (default)
./start_remote_agent.sh google_adk --host localhost --port 10020 --llm-provider lmstudio --model-name qwen3-8b
# With Ollama
./start_remote_agent.sh google_adk --host localhost --port 10020 --llm-provider ollama --model-name qwen3:8b
```

#### Agent Card of Reimbursement Agent

```bash
http -b http://localhost:10020/.well-known/agent.json
```

```json
{
  "capabilities": {
    "streaming": true
  },
  "defaultInputModes": ["text", "text/plain"],
  "defaultOutputModes": ["text", "text/plain"],
  "description": "This agent handles the reimbursement process for the employees given the amount and purpose of the reimbursement.",
  "name": "Reimbursement Agent",
  "skills": [
    {
      "description": "Helps with the reimbursement process for users given the amount and purpose of the reimbursement.",
      "examples": ["Can you reimburse me $20 for my lunch with the clients?"],
      "id": "process_reimbursement",
      "name": "Process Reimbursement Tool",
      "tags": ["reimbursement"]
    }
  ],
  "url": "http://localhost:10020/",
  "version": "1.0.0"
}
```

#### User Case of Reimbursement Agent

**1. New Expense Report Request:**

```bash
curl -X POST http://localhost:10020/ \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-123",
    "method": "message/send",
    "params": {
      "messageId": "msg-456",
      "message": {
        "messageId": "msg-456",
        "role": "user",
        "parts": [
          {
            "text": "请帮我提交一个报销申请，我需要报销出差的交通费用500元"
          }
        ]
      }
    }
  }'
```

**Response:** Agent returns a form with schema and pre-filled data:

```json
{
  "status": {
    "state": "input-required",
    "message": {
      "parts": [
        {
          "data": {
            "form": {
              "type": "object",
              "properties": {
                "date": {
                  "type": "string",
                  "format": "date",
                  "description": "费用日期"
                },
                "amount": {
                  "type": "string",
                  "format": "number",
                  "description": "费用金额"
                },
                "purpose": { "type": "string", "description": "费用目的" },
                "request_id": { "type": "string", "description": "申请ID" }
              },
              "required": ["date", "amount", "purpose"]
            },
            "form_data": {
              "date": "<交差日期>",
              "amount": "500",
              "purpose": "出差的交通费用"
            },
            "instructions": "请确认并补充完整表单信息：1. 交易日期 2. 金额(已填写500) 3. 业务理由(已填写出差的交通费用)"
          }
        }
      ]
    }
  }
}
```

**2. Form Submission:**

```bash
curl -X POST http://localhost:10020/ \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-form-submit",
    "method": "message/send",
    "params": {
      "messageId": "msg-form-submit",
      "message": {
        "messageId": "msg-form-submit",
        "role": "user",
        "parts": [
          {
            "text": "表单已填写完成：\n日期：2024-06-01\n金额：500\n目的：出差的交通费用\n申请ID：REQ001"
          }
        ]
      }
    }
  }'
```

**Response:** Agent processes and completes the expense report:

```json
{
  "status": {
    "state": "completed"
  },
  "artifacts": [
    {
      "name": "response",
      "parts": [
        {
          "text": "\n\n您的报销申请已成功处理！\n✅ 申请ID: request_id_4221165\n✅ 状态: 已批准\n金额: $500\n业务目的: 出差的交通费用\n\n请注意查收报销款项，如有任何疑问请随时联系财务部门。"
        }
      ]
    }
  ]
}
```

**3. Direct Request Processing:**

```bash
curl -X POST http://localhost:10020/ \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-reimburse",
    "method": "message/send",
    "params": {
      "messageId": "msg-reimburse",
      "message": {
        "messageId": "msg-reimburse",
        "role": "user",
        "parts": [
          {
            "text": "请处理申请ID为REQ001的报销申请"
          }
        ]
      }
    }
  }'
```

### 4 Travel Agent

#### Semantic Kernel API

- https://learn.microsoft.com/en-us/semantic-kernel/overview/

`remotes/semantickernel/agent.py`

```python
class SemanticKernelTravelAgent:
    openai_client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=base_url
    )
    currency_exchange_agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(
            ai_model_id=model_id,
            api_key=api_key,
            async_client=openai_client
        )
    )
    activity_planner_agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(
            ai_model_id=model_name,
            api_key=api_key,
            async_client=openai_client
        )
    )
    self.agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(
            ai_model_id=model_name,
            api_key=api_key,
            async_client=openai_client
        ),
        plugins=[currency_exchange_agent, activity_planner_agent]

```

#### Start Travel Agent

```bash
# With LM Studio (default)
./start_remote_agent.sh semantickernel --host localhost --port 10030 --llm-provider lmstudio --model-name qwen3-30b-a3b
# With Ollama
./start_remote_agent.sh semantickernel --host localhost --port 10030 --llm-provider ollama --model-name qwen3:30b-a3b
```

#### Agent Card of Travel Agent

```bash
http --body http://localhost:10030/.well-known/agent.json
```

```json
{
  "capabilities": {
    "streaming": true
  },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "description": "Semantic Kernel-based travel agent providing comprehensive trip planning services including currency exchange and personalized activity planning.",
  "name": "SK Travel Agent",
  "skills": [
    {
      "description": "Handles comprehensive trip planning, including currency exchanges, itinerary creation, sightseeing, dining recommendations, and event bookings using Frankfurter API for currency conversions.",
      "examples": [
        "Plan a budget-friendly day trip to Seoul including currency exchange.",
        "What's the exchange rate and recommended itinerary for visiting Tokyo?"
      ],
      "id": "trip_planning_sk",
      "name": "Semantic Kernel Trip Planning",
      "tags": ["trip", "planning", "travel", "currency", "semantic-kernel"]
    }
  ],
  "url": "http://localhost:10030/",
  "version": "1.0.0"
}
```

#### User Case of Travel Agent

**Testing Travel Agent with Multi-Agent Integration:**

```bash
http --stream POST localhost:10030 \
  Content-Type:application/json \
  jsonrpc="2.0" \
  id:=1 \
  method="message/send" \
  params:='{
    "id": "travel-korea-plan",
    "sessionId": "test-session",
    "acceptedOutputModes": ["text"],
    "streaming": true,
    "message": {
      "messageId": "msg-01",
      "role": "user",
      "parts": [{
        "type": "text",
        "text": "我有5000美元预算，想去韩国首尔旅行7天，请帮我制定详细的旅行计划，包括汇率转换和具体的行程安排"
      }]
    }
  }'
```

**Response with Multi-Agent Collaboration:**

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [
      {
        "artifactId": "travel-plan-korea",
        "name": "seoul_travel_plan",
        "parts": [
          {
            "kind": "text",
            "text": "# 📍 首尔7天详细旅行计划\n\n## 💰 预算与汇率信息\n- **总预算**: 5000 USD\n- **当前汇率**: 1 USD = 1376.78 KRW\n- **韩元预算**: 约 6,883,900 KRW\n\n## 🗓️ 详细行程安排\n\n### Day 1: 抵达首尔 (预算: 800,000 KRW)\n- **住宿**: 明洞地区酒店 (120,000 KRW/晚)\n- **交通**: 仁川机场快线 → 明洞 (9,000 KRW)\n- **晚餐**: 明洞街头美食体验 (30,000 KRW)\n- **活动**: 明洞购物街漫步，适应时差\n\n### Day 2: 宫殿文化之旅 (预算: 150,000 KRW)\n- **景点**: 景福宫 + 昌德宫 (门票: 8,000 KRW)\n- **体验**: 韩服租赁体验 (20,000 KRW)\n- **午餐**: 仁寺洞传统韩式料理 (25,000 KRW)\n- **下午**: 北村韩屋村 + 三清洞咖啡街\n- **晚餐**: 弘大韩式烤肉 (40,000 KRW)\n\n### Day 3: 现代首尔体验 (预算: 200,000 KRW)\n- **上午**: 乐天世界塔 + 天空步道 (门票: 27,000 KRW)\n- **午餐**: 江南区精致餐厅 (50,000 KRW)\n- **下午**: 江南COEX购物中心 + 星空图书馆\n- **晚上**: 汉江公园野餐 + 夜景 (15,000 KRW)\n\n### Day 4: 传统市场与美食 (预算: 120,000 KRW)\n- **上午**: 广藏市场传统美食巡礼 (30,000 KRW)\n- **中午**: 东大门设计广场 (DDP)\n- **下午**: 梨泰院国际街区 (25,000 KRW)\n- **晚餐**: 新村大学路韩式炸鸡配啤酒 (25,000 KRW)\n\n### Day 5: 自然与休闲 (预算: 100,000 KRW)\n- **全天**: 南山首尔塔 + 缆车 (门票: 21,000 KRW)\n- **午餐**: 南山韩屋村餐厅 (30,000 KRW)\n- **下午**: 汝矣岛汉江公园骑行 (自行车租赁: 10,000 KRW)\n- **晚餐**: 汝矣岛夜市小吃 (20,000 KRW)\n\n### Day 6: 购物与娱乐 (预算: 300,000 KRW)\n- **上午**: 明洞乐天免税店购物 (200,000 KRW)\n- **午餐**: 明洞韩式拌饭专门店 (15,000 KRW)\n- **下午**: 弘大Club + K-POP体验馆 (30,000 KRW)\n- **晚餐**: 弘大大学路聚餐 (35,000 KRW)\n\n### Day 7: 离别首尔 (预算: 50,000 KRW)\n- **上午**: 仁寺洞纪念品购买 (30,000 KRW)\n- **午餐**: 机场简餐 (15,000 KRW)\n- **交通**: 明洞 → 仁川机场 (9,000 KRW)\n\n## 🏨 住宿推荐 (7晚 × 120,000 KRW = 840,000 KRW)\n- **明洞乐天酒店** 或 **首尔明洞九树酒店**\n- 位置优越，交通便利，购物方便\n\n## 🚌 交通费用总计: 约 100,000 KRW\n- 地铁7日通票: 53,200 KRW\n- 机场快线往返: 18,000 KRW\n- 市内出租车: 30,000 KRW\n\n## 💵 总费用明细 (KRW)\n- **住宿**: 840,000\n- **餐饮**: 315,000\n- **交通**: 100,000\n- **景点门票**: 84,000\n- **购物娱乐**: 530,000\n- **其他杂费**: 100,000\n- **总计**: 1,969,000 KRW (约 1,430 USD)\n\n## ✅ 预算充足提示\n剩余预算约 3,570 USD，可以:\n- 升级住宿至五星级酒店\n- 增加购物预算\n- 体验更多高端餐厅\n- 考虑济州岛1-2日游\n\n## 📱 实用信息\n- **天气**: 春季(15-20°C) 夏季(25-30°C)\n- **必备APP**: 지하철(地铁), 카카오맵(地图)\n- **语言**: 下载翻译APP，基础韩语学习\n- **网络**: 租赁随身WiFi或购买当地SIM卡\n\n🎉 **祝您首尔之旅愉快！**"
          }
        ]
      }
    ],
    "status": {
      "state": "completed"
    }
  }
}
```

### 5 File Chat Agent

#### LlamaIndex API

- https://docs.llamaindex.ai/en/stable/examples/llm/ollama/
- https://docs.llamaindex.ai/en/stable/examples/llm/lmstudio/

`remotes/llama_index_file_chat/agent.py`

```python
class ParseAndChat(Workflow):
    self._sllm = OpenAI(
        model=model_name,
        base_url="http://localhost:1234/v1",
    )
```

#### Start File Chat Agent

```bash
./start_remote_agent.sh llama_index_file_chat --host localhost --port 10040 --llm-provider lmstudio --model-name qwen3-30b-a3b
./start_remote_agent.sh llama_index_file_chat --host localhost --port 10040 --llm-provider ollama --model-name qwen3:30b-a3b
```

#### Agent Card of File Chat Agent

```bash
http --body http://localhost:10040/.well-known/agent.json
```

```json
{
  "capabilities": {
    "pushNotifications": true,
    "streaming": true
  },
  "defaultInputModes": [
    "text/plain",
    "application/pdf",
    "application/msword",
    "image/png",
    "image/jpeg"
  ],
  "defaultOutputModes": ["text", "text/plain"],
  "description": "Parses a file and then chats with a user using the parsed content as context.",
  "name": "Parse and Chat",
  "skills": [
    {
      "description": "Parses a file and then chats with a user using the parsed content as context.",
      "examples": ["What does this file talk about?"],
      "id": "parse_and_chat",
      "name": "Parse and Chat",
      "tags": ["parse", "chat", "file", "llama_parse"]
    }
  ],
  "url": "http://localhost:10040/",
  "version": "1.0.0"
}
```

#### User Case of File Chat Agent

```bash
export DOC_PATH=/Users/han/coding/a2a_google/hello-a2a-examples/test_ai_document.txt
export DOC_BASE64=$(base64 -i $DOC_PATH)

http POST localhost:10040 \
  Content-Type:application/json \
  jsonrpc="2.0" \
  id:=2 \
  method="message/send" \
  params:="{
    \"id\": \"file-analysis-test\",
    \"sessionId\": \"file-chat-session\",
    \"acceptedOutputModes\": [\"text\"],
    \"message\": {
      \"messageId\": \"msg-file-01\",
      \"role\": \"user\",
      \"parts\": [
        {
          \"type\": \"text\",
          \"text\": \"请分析并总结这个文档\"
        },
        {
          \"type\": \"file\",
          \"file\": {
            \"name\": \"ai_document.txt\",
            \"mimeType\": \"text/plain\",
            \"bytes\": \"$DOC_BASE64\"
          }
        }
      ]
    }
  }" | jq '.result.artifacts'
```

```json
[
  {
    "artifactId": "f427dc45-f27e-4bf5-9df4-b62e170e7ec8",
    "metadata": {},
    "name": "llama_summary",
    "parts": [
      {
        "kind": "text",
        "text": "<think>\n好的，用户让我分析并总结这个文档。首先我需要仔细阅读文档内容，了解其结构和主要信息。文档标题是“人工智能技术发展报告”，分为几个主要部分：应用领域和未来发展趋势。\n\n先看应用领域部分，有四个主要领域：医疗健康、金融服务、自动驾驶和自然语言处理。每个领域下都有具体的子点。比如医疗健康包括医学影像分析、疾病预测和精准医疗。这些内容对应的行号是4到9，我需要记住每个子点对应的行号，以便后续引用。\n\n接下来是金融服务，行号11到15，提到风险评估、算法交易和反欺诈检测。自动驾驶部分在行号17到21，涉及环境感知、路径规划和车联网。自然语言处理部分在行号23到27，包括机器翻译、智能客服和文本摘要。\n\n然后是未来发展趋势，行号28到33，提到生成式AI、多模态系统、伦理安全和边缘计算优化。我需要确保每个总结点都对应正确的行号，并且引用时使用正确的编号格式。\n\n用户可能希望得到一个结构清晰的总结，涵盖各个主要部分，并正确引用文档中的内容。需要注意的是，内联引用要从[1]开始，每增加一个引用递增，连续行用单个引用，非连续行则分开标注。例如，医疗健康部分有三个子点，可能需要引用行4到9，但具体要看每个子点对应的行号是否连续。\n\n现在组织语言，先概述文档整体内容，然后分点总结应用领域和未来趋势，确保每个要点都有对应的引用。检查是否有遗漏的部分，并确保引用格式正确，避免使用行号作为引用编号，而是按照规则递增。\n</think>\n\n该文档系统阐述了人工智能技术的发展现状与未来方向，以下是核心内容的结构化分析：  \n\n1. **主要应用领域**  \n   - **医疗健康** [4]：AI通过医学影像分析[6]、疾病预测和早期诊断[7]、精准医疗方案制定[8]等技术革新医疗体系。  \n   - **金融服务** [11]：涵盖风险评估和信用分析[12]、算法交易及投资决策[13]、反欺诈检测系统[14]等场景。  \n   - **自动驾驶** [17]：依赖环境感知与目标识别[18]、路径规划与决策系统[19]、车联网与智能交通[20]技术实现。  \n   - **自然语言处理** [23]：推动机器翻译[24]、智能客服与对话系统[25]、文本摘要及信息提取[26]等应用落地。  \n\n2. **未来发展趋势** [28]  \n   - 生成式AI模型持续进化[29]，多模态AI系统实现跨感官数据融合[30]。  \n   - 强调AI伦理与安全性建设[31]，同时优化边缘计算与专用芯片性能[32]以提升效率。  \n\n文档整体呈现了AI技术从垂直领域渗透到跨行业协同的发展脉络，并前瞻性地提出技术演进与社会价值平衡的双重命题。"
      }
    ]
  }
]
```

## Cli

```bash
./start_cli.sh --agent http://localhost:10000

Convert 100 USD to CNY
```

```bash
Task status: completed

2025-06-02: 100.0 USD = 719.98 CNY (1 USD = 7.1998 CNY)
```

## Host Agent

```bash
./start_host_agent.sh
```

<http://localhost:12000>
