import express from "express";
import { v4 as uuidv4 } from 'uuid';

import {
    InMemoryTaskStore,
    TaskStore,
    schema,
    A2AExpressApp,
    AgentExecutor,
    RequestContext,
    IExecutionEventBus,
    DefaultRequestHandler
} from "../../server/index.js";
import { ollamaClient } from "../coder/ollama-client.js";

/**
 * SimpleMovieAgentExecutor - A simplified movie agent that uses Ollama without external APIs
 */
class SimpleMovieAgentExecutor implements AgentExecutor {
    async execute(
        requestContext: RequestContext,
        eventBus: IExecutionEventBus
    ): Promise<void> {
        const userMessage = requestContext.userMessage;
        const existingTask = requestContext.task;

        const taskId = existingTask?.id || uuidv4();
        const contextId = userMessage.contextId || existingTask?.contextId || uuidv4();

        console.log(
            `[SimpleMovieAgentExecutor] Processing message ${userMessage.messageId} for task ${taskId}`
        );

        // Check Ollama health
        const isOllamaHealthy = await ollamaClient.checkHealth();
        if (!isOllamaHealthy) {
            console.error('[SimpleMovieAgentExecutor] Ollama service is not available');
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

        // Publish initial task if new
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
                artifacts: [],
            };
            eventBus.publish(initialTask);
        }

        // Publish working status
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
                    parts: [{ kind: 'text', text: 'Processing movie request using Ollama...' }],
                    taskId: taskId,
                    contextId: contextId,
                },
                timestamp: new Date().toISOString(),
            },
            final: false,
        };
        eventBus.publish(workingStatusUpdate);

        // Extract user message text
        const userText = userMessage.parts
            .filter((p): p is schema.TextPart => p.kind === 'text' && !!(p as schema.TextPart).text)
            .map(p => (p as schema.TextPart).text)
            .join(' ');

        if (!userText.trim()) {
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
                        parts: [{ kind: 'text', text: 'No text input found to process.' }],
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

        try {
            // Generate response using Ollama
            const systemPrompt = `You are a helpful movie assistant. You can discuss movies, provide recommendations, 
      analyze plots, discuss actors and directors, and answer movie-related questions. Since you don't have access 
      to real-time movie databases, provide responses based on your training knowledge about movies.
      
      Be helpful, informative, and engaging. If asked about specific movie details like release dates or cast,
      mention that the information is based on your training data and may not be completely up-to-date.`;

            const response = await ollamaClient.generate({
                model: 'qwen3:8b',
                prompt: userText,
                system: systemPrompt
            });

            // Publish final status update
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
                        parts: [{ kind: 'text', text: response }],
                        taskId: taskId,
                        contextId: contextId,
                    },
                    timestamp: new Date().toISOString(),
                },
                final: true,
            };
            eventBus.publish(finalUpdate);

            console.log(`[SimpleMovieAgentExecutor] Task ${taskId} completed successfully`);

        } catch (error: any) {
            console.error(`[SimpleMovieAgentExecutor] Error processing task ${taskId}:`, error);
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
                        parts: [{ kind: 'text', text: `Error: ${error.message}` }],
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

// Agent card for the simple movie agent
const simpleMovieAgentCard: schema.AgentCard = {
    name: 'Simple Movie Agent (Ollama)',
    description: 'A movie discussion agent powered by local Ollama qwen3:8b model',
    url: 'http://localhost:41241/',
    provider: {
        organization: 'A2A Samples - Local Ollama',
        url: 'https://example.com/a2a-samples',
    },
    version: '0.0.3',
    capabilities: {
        streaming: false,
        pushNotifications: false,
        stateTransitionHistory: true,
    },
    securitySchemes: undefined,
    security: undefined,
    defaultInputModes: ['text'],
    defaultOutputModes: ['text'],
    skills: [
        {
            id: 'movie_discussion',
            name: 'Movie Discussion',
            description: 'Discuss movies, provide recommendations, and answer movie-related questions using local AI',
            tags: ['movies', 'entertainment', 'recommendations', 'ollama', 'local'],
            examples: [
                'What are some good sci-fi movies from the 2020s?',
                'Tell me about the movie Inception',
                'Recommend movies similar to The Matrix',
            ],
            inputModes: ['text'],
            outputModes: ['text'],
        },
    ],
    supportsAuthenticatedExtendedCard: false,
};

async function main() {
    // Create TaskStore
    const taskStore: TaskStore = new InMemoryTaskStore();

    // Create AgentExecutor
    const agentExecutor: AgentExecutor = new SimpleMovieAgentExecutor();

    // Create DefaultRequestHandler
    const requestHandler = new DefaultRequestHandler(
        simpleMovieAgentCard,
        taskStore,
        agentExecutor
    );

    // Create and setup A2AExpressApp
    const appBuilder = new A2AExpressApp(requestHandler);
    const expressApp = appBuilder.setupRoutes(express(), '');

    // Start the server
    const PORT = process.env.MOVIE_AGENT_PORT || 41241;
    expressApp.listen(PORT, () => {
        console.log(`[SimpleMovieAgent] Server started on http://localhost:${PORT}`);
        console.log(`[SimpleMovieAgent] Agent Card: http://localhost:${PORT}/.well-known/agent.json`);
        console.log('[SimpleMovieAgent] Using local Ollama qwen3:8b model');
        console.log('[SimpleMovieAgent] Make sure Ollama is running on http://localhost:11434');
        console.log('[SimpleMovieAgent] Press Ctrl+C to stop the server');
    });
}

main().catch(console.error);
