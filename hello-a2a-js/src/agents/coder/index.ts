import express from "express";
import { v4 as uuidv4 } from 'uuid'; // For generating unique IDs

import {
  InMemoryTaskStore,
  TaskStore,
  A2AExpressApp,
  AgentExecutor,
  RequestContext,
  IExecutionEventBus,
  DefaultRequestHandler,
  schema,
} from "../../server/index.js"; // Import server components
import { ollamaClient } from "./ollama-client.js";
import { CodeMessage, parseCodeFromText } from "./simple-code-format.js";

/**
 * CoderAgentExecutor implements the agent's core logic for code generation using Ollama.
 */
class CoderAgentExecutor implements AgentExecutor {
  async execute(
    requestContext: RequestContext,
    eventBus: IExecutionEventBus
  ): Promise<void> {
    const userMessage = requestContext.userMessage;
    const existingTask = requestContext.task;

    const taskId = existingTask?.id || uuidv4();
    const contextId = userMessage.contextId || existingTask?.contextId || uuidv4();

    console.log(
      `[CoderAgentExecutor] Processing message ${userMessage.messageId} for task ${taskId} (context: ${contextId})`
    );

    // 1. Check Ollama health
    const isOllamaHealthy = await ollamaClient.checkHealth();
    if (!isOllamaHealthy) {
      console.error('[CoderAgentExecutor] Ollama service is not available');
      const failureUpdate: schema.TaskStatusUpdateEvent = {
        kind: 'status-update',
        taskId: taskId,
        contextId: contextId,
        status: {
          state: schema.TaskState.Failed,
          message: {
            kind: 'message',
            role: 'agent',
            messageId: uuidv4(),
            parts: [{ kind: 'text', text: 'Ollama service is not available. Please ensure Ollama is running on localhost:11434' }],
            taskId: taskId,
            contextId: contextId,
          },
          timestamp: new Date().toISOString(),
        },
        final: true,
      };
      eventBus.publish(failureUpdate);
      return;
    }

    // 2. Publish initial Task event if it's a new task
    if (!existingTask) {
      const initialTask: schema.Task = {
        kind: 'task',
        id: taskId,
        contextId: contextId,
        status: {
          state: schema.TaskState.Submitted,
          timestamp: new Date().toISOString(),
        },
        history: [userMessage],
        metadata: userMessage.metadata,
        artifacts: [], // Initialize artifacts array
      };
      eventBus.publish(initialTask);
    }

    // 3. Publish "working" status update
    const workingStatusUpdate: schema.TaskStatusUpdateEvent = {
      kind: 'status-update',
      taskId: taskId,
      contextId: contextId,
      status: {
        state: schema.TaskState.Working,
        message: {
          kind: 'message',
          role: 'agent',
          messageId: uuidv4(),
          parts: [{ kind: 'text', text: 'Generating code using Ollama...' }],
          taskId: taskId,
          contextId: contextId,
        },
        timestamp: new Date().toISOString(),
      },
      final: false,
    };
    eventBus.publish(workingStatusUpdate);

    // 4. Prepare prompt from user message
    const historyForPrompt = existingTask?.history ? [...existingTask.history] : [];
    if (!historyForPrompt.find(m => m.messageId === userMessage.messageId)) {
      historyForPrompt.push(userMessage);
    }

    // Extract text from user messages
    const userPrompts = historyForPrompt
      .filter(m => m.role === 'user')
      .map(m => m.parts
        .filter((p): p is schema.TextPart => p.kind === 'text' && !!(p as schema.TextPart).text)
        .map(p => (p as schema.TextPart).text)
        .join(' ')
      )
      .filter(text => text.trim().length > 0);

    if (userPrompts.length === 0) {
      console.warn(
        `[CoderAgentExecutor] No valid text messages found in history for task ${taskId}.`
      );
      const failureUpdate: schema.TaskStatusUpdateEvent = {
        kind: 'status-update',
        taskId: taskId,
        contextId: contextId,
        status: {
          state: schema.TaskState.Failed,
          message: {
            kind: 'message',
            role: 'agent',
            messageId: uuidv4(),
            parts: [{ kind: 'text', text: 'No input message found to process.' }],
            taskId: taskId,
            contextId: contextId,
          },
          timestamp: new Date().toISOString(),
        },
        final: true,
      };
      eventBus.publish(failureUpdate);
      return;
    }

    const prompt = userPrompts.join('\n\n');
    const systemPrompt = `You are an expert coding assistant. Generate high-quality code based on the user's request. 

Instructions:
- Provide complete, working code
- Use appropriate file names and extensions
- Format your response with code blocks using triple backticks
- Include filename comments like: // filename: example.js
- Generate multiple files if needed
- Write clean, well-documented code

User request: ${prompt}`;

    try {
      // 5. Generate response using Ollama
      const response = await ollamaClient.generate({
        model: 'qwen3:8b', // Use qwen3:8b model (available in Ollama)
        prompt: systemPrompt,
        system: 'You are a helpful coding assistant that generates clean, working code based on user requests.'
      });

      // 6. Parse the response to extract code files
      const codeMessage: CodeMessage = parseCodeFromText(response);

      // 7. Emit artifacts for each generated file
      for (let i = 0; i < codeMessage.files.length; i++) {
        const file = codeMessage.files[i];
        console.log(
          `[CoderAgentExecutor] Emitting file artifact: ${file.filename}`
        );

        const artifactUpdate: schema.TaskArtifactUpdateEvent = {
          kind: 'artifact-update',
          taskId: taskId,
          contextId: contextId,
          artifact: {
            artifactId: file.filename,
            name: file.filename,
            parts: [{ kind: 'text', text: file.content }],
          },
          append: false,
          lastChunk: true,
        };
        eventBus.publish(artifactUpdate);

        // Check if the request has been cancelled
        if (requestContext.isCancelled()) {
          console.log(`[CoderAgentExecutor] Request cancelled for task: ${taskId}`);
          const cancelledUpdate: schema.TaskStatusUpdateEvent = {
            kind: 'status-update',
            taskId: taskId,
            contextId: contextId,
            status: {
              state: schema.TaskState.Canceled,
              timestamp: new Date().toISOString(),
            },
            final: true,
          };
          eventBus.publish(cancelledUpdate);
          return;
        }
      }

      const generatedFiles = codeMessage.files.map(f => f.filename);

      // 8. Publish final task status update
      const finalUpdate: schema.TaskStatusUpdateEvent = {
        kind: 'status-update',
        taskId: taskId,
        contextId: contextId,
        status: {
          state: schema.TaskState.Completed,
          message: {
            kind: 'message',
            role: 'agent',
            messageId: uuidv4(),
            parts: [
              {
                kind: 'text',
                text:
                  generatedFiles.length > 0
                    ? `Generated files using Ollama qwen3:8b: ${generatedFiles.join(', ')}`
                    : 'Completed processing, but no files were generated.',
              },
            ],
            taskId: taskId,
            contextId: contextId,
          },
          timestamp: new Date().toISOString(),
        },
        final: true,
      };
      eventBus.publish(finalUpdate);

      console.log(
        `[CoderAgentExecutor] Task ${taskId} completed successfully with ${generatedFiles.length} files`
      );

    } catch (error: any) {
      console.error(
        `[CoderAgentExecutor] Error processing task ${taskId}: `,
        error
      );
      const errorUpdate: schema.TaskStatusUpdateEvent = {
        kind: 'status-update',
        taskId: taskId,
        contextId: contextId,
        status: {
          state: schema.TaskState.Failed,
          message: {
            kind: 'message',
            role: 'agent',
            messageId: uuidv4(),
            parts: [{ kind: 'text', text: `Ollama error: ${error.message}` }],
            taskId: taskId,
            contextId: contextId,
          },
          timestamp: new Date().toISOString(),
        },
        final: true,
      };
      eventBus.publish(errorUpdate);
    }
  }
}

// --- Server Setup ---

const coderAgentCard: schema.AgentCard = {
  name: 'Ollama Coder Agent',
  description:
    'An agent that generates code using local Ollama qwen3:8b model based on natural language instructions.',
  url: 'http://localhost:41242/',
  provider: {
    organization: 'A2A Samples - Local Ollama',
    url: 'https://example.com/a2a-samples',
  },
  version: '0.0.3', // Updated version for Ollama integration
  capabilities: {
    streaming: false, // Simplified to non-streaming for Ollama
    pushNotifications: false,
    stateTransitionHistory: true,
  },
  securitySchemes: undefined,
  security: undefined,
  defaultInputModes: ['text'],
  defaultOutputModes: ['text', 'file'],
  skills: [
    {
      id: 'code_generation',
      name: 'Code Generation with Ollama',
      description:
        'Generates code snippets or complete files using local Ollama qwen3:8b model based on user requests.',
      tags: ['code', 'development', 'programming', 'ollama', 'local'],
      examples: [
        'Write a python function to calculate fibonacci numbers.',
        'Create an HTML file with a basic button that alerts "Hello!" when clicked.',
        'Generate a simple REST API in Node.js with Express.',
      ],
      inputModes: ['text'],
      outputModes: ['text', 'file'],
    },
  ],
  supportsAuthenticatedExtendedCard: false,
};

async function main() {
  // 1. Create TaskStore
  const taskStore: TaskStore = new InMemoryTaskStore();

  // 2. Create AgentExecutor
  const agentExecutor: AgentExecutor = new CoderAgentExecutor();

  // 3. Create DefaultRequestHandler
  const requestHandler = new DefaultRequestHandler(
    coderAgentCard,
    taskStore,
    agentExecutor
  );

  // 4. Create and setup A2AExpressApp
  const appBuilder = new A2AExpressApp(requestHandler);
  const expressApp = appBuilder.setupRoutes(express(), '');

  // 5. Start the server
  const PORT = process.env.CODER_AGENT_PORT || 41242;
  expressApp.listen(PORT, () => {
    console.log(`[OllamaCoderAgent] Server started on http://localhost:${PORT}`);
    console.log(`[OllamaCoderAgent] Agent Card: http://localhost:${PORT}/.well-known/agent.json`);
    console.log('[OllamaCoderAgent] Using local Ollama qwen3:8b model');
    console.log('[OllamaCoderAgent] Make sure Ollama is running on http://localhost:11434');
    console.log('[OllamaCoderAgent] Press Ctrl+C to stop the server');
  });
}

main().catch(console.error);
