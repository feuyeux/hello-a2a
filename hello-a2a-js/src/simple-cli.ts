#!/usr/bin/env node
/**
 * Simple CLI client for testing A2A agents without cloud API dependencies
 */

import { A2AClient } from "./client/client.js";
import {
    Message,
    MessageSendParams,
    TaskQueryParams
} from "./schema.js";

async function testCoderAgent() {
    console.log("🤖 Testing Ollama Coder Agent...");

    const client = new A2AClient("http://localhost:41242");

    try {
        // Test agent card retrieval
        console.log("📋 Getting agent card...");
        const agentCard = await client.getAgentCard();
        console.log(`Agent: ${agentCard.name} v${agentCard.version}`);
        console.log(`Description: ${agentCard.description}`);

        // Test code generation
        console.log("\n💻 Requesting code generation...");
        const message: Message = {
            kind: 'message',
            role: 'user',
            messageId: crypto.randomUUID(),
            parts: [{
                kind: 'text',
                text: 'Write a simple Python function that calculates the factorial of a number'
            }],
            contextId: crypto.randomUUID()
        };

        const params: MessageSendParams = {
            message: message,
            configuration: {
                acceptedOutputModes: ['text', 'file'],
                blocking: false
            }
        };

        console.log("📤 Sending request...");
        const response = await client.sendMessage(params);

        if ('result' in response && response.result.kind === 'task') {
            const taskId = response.result.id;
            console.log(`✅ Task submitted with ID: ${taskId}`);

            // Wait for completion
            console.log("⏳ Waiting for task completion...");
            let attempts = 0;
            const maxAttempts = 30;

            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 1000));

                const taskParams: TaskQueryParams = { id: taskId };
                const taskResponse = await client.getTask(taskParams);

                if ('result' in taskResponse && taskResponse.result) {
                    const task = taskResponse.result;
                    console.log(`Status: ${task.status.state}`);

                    if (task.status.state === 'completed') {
                        console.log("🎉 Task completed successfully!");

                        if (task.status.message?.parts) {
                            console.log("\n📝 Response:");
                            task.status.message.parts.forEach(part => {
                                if (part.kind === 'text' && 'text' in part) {
                                    console.log(part.text);
                                }
                            });
                        }

                        if (task.artifacts && task.artifacts.length > 0) {
                            console.log(`\n📁 Generated ${task.artifacts.length} file(s):`);
                            task.artifacts.forEach(artifact => {
                                console.log(`- ${artifact.name}`);
                                if (artifact.parts) {
                                    artifact.parts.forEach(part => {
                                        if (part.kind === 'text' && 'text' in part) {
                                            console.log(`\n${artifact.name}:`);
                                            console.log("```");
                                            console.log(part.text);
                                            console.log("```");
                                        }
                                    });
                                }
                            });
                        }
                        return;
                    } else if (task.status.state === 'failed') {
                        console.log("❌ Task failed!");
                        if (task.status.message?.parts) {
                            task.status.message.parts.forEach(part => {
                                if (part.kind === 'text' && 'text' in part) {
                                    console.log(`Error: ${part.text}`);
                                }
                            });
                        }
                        return;
                    }
                }

                attempts++;
            }

            console.log("⏰ Timeout waiting for task completion");
        } else {
            console.log("❌ Failed to submit task");
            console.log(response);
        }

    } catch (error) {
        console.error("❌ Error testing coder agent:", error);
    }
}

async function testMovieAgent() {
    console.log("\n🎬 Testing Simple Movie Agent...");

    const client = new A2AClient("http://localhost:41241");

    try {
        // Test agent card retrieval
        console.log("📋 Getting agent card...");
        const agentCard = await client.getAgentCard();
        console.log(`Agent: ${agentCard.name} v${agentCard.version}`);
        console.log(`Description: ${agentCard.description}`);

        // Test movie discussion
        console.log("\n🎥 Asking about movies...");
        const message: Message = {
            kind: 'message',
            role: 'user',
            messageId: crypto.randomUUID(),
            parts: [{
                kind: 'text',
                text: 'Can you recommend some good science fiction movies from the last 10 years?'
            }],
            contextId: crypto.randomUUID()
        };

        const params: MessageSendParams = {
            message: message,
            configuration: {
                acceptedOutputModes: ['text'],
                blocking: false
            }
        };

        console.log("📤 Sending request...");
        const response = await client.sendMessage(params);

        if ('result' in response && response.result.kind === 'task') {
            const taskId = response.result.id;
            console.log(`✅ Task submitted with ID: ${taskId}`);

            // Wait for completion
            console.log("⏳ Waiting for task completion...");
            let attempts = 0;
            const maxAttempts = 30;

            while (attempts < maxAttempts) {
                await new Promise(resolve => setTimeout(resolve, 1000));

                const taskParams: TaskQueryParams = { id: taskId };
                const taskResponse = await client.getTask(taskParams);

                if ('result' in taskResponse && taskResponse.result) {
                    const task = taskResponse.result;
                    console.log(`Status: ${task.status.state}`);

                    if (task.status.state === 'completed') {
                        console.log("🎉 Task completed successfully!");

                        if (task.status.message?.parts) {
                            console.log("\n📝 Movie recommendations:");
                            task.status.message.parts.forEach(part => {
                                if (part.kind === 'text' && 'text' in part) {
                                    console.log(part.text);
                                }
                            });
                        }
                        return;
                    } else if (task.status.state === 'failed') {
                        console.log("❌ Task failed!");
                        if (task.status.message?.parts) {
                            task.status.message.parts.forEach(part => {
                                if (part.kind === 'text' && 'text' in part) {
                                    console.log(`Error: ${part.text}`);
                                }
                            });
                        }
                        return;
                    }
                }

                attempts++;
            }

            console.log("⏰ Timeout waiting for task completion");
        } else {
            console.log("❌ Failed to submit task");
            console.log(response);
        }

    } catch (error) {
        console.error("❌ Error testing movie agent:", error);
    }
}

async function checkOllama() {
    console.log("🔍 Checking Ollama service...");

    try {
        const response = await fetch('http://localhost:11434/api/tags');
        if (response.ok) {
            const data = await response.json();
            console.log("✅ Ollama is running");
            if (data.models && data.models.length > 0) {
                console.log("📦 Available models:");
                data.models.forEach((model: any) => {
                    console.log(`  - ${model.name}`);
                });

                const hasQwen = data.models.some((model: any) =>
                    model.name.includes('qwen3:8b') || model.name.includes('qwen3')
                );

                if (!hasQwen) {
                    console.log("⚠️  qwen3:8b model not found. You may need to pull it:");
                    console.log("   ollama pull qwen3:8b");
                }
            } else {
                console.log("📦 No models found. You may need to pull qwen3:8b:");
                console.log("   ollama pull qwen3:8b");
            }
        } else {
            console.log("❌ Ollama service not responding");
        }
    } catch (error) {
        console.log("❌ Could not connect to Ollama. Make sure it's running:");
        console.log("   https://ollama.com for installation instructions");
    }
}

async function main() {
    console.log("🚀 A2A JavaScript Local Ollama Test Client");
    console.log("=========================================");

    // Check Ollama first
    await checkOllama();

    const args = process.argv.slice(2);
    const testType = args[0] || 'both';

    console.log(`\nRunning tests: ${testType}`);
    console.log("Make sure the agents are running:");
    console.log("  - Coder Agent: npm run coder");
    console.log("  - Movie Agent: npm run movie");

    console.log("\n" + "=".repeat(50));

    if (testType === 'coder' || testType === 'both') {
        await testCoderAgent();
    }

    if (testType === 'movie' || testType === 'both') {
        await testMovieAgent();
    }

    console.log("\n✨ Test completed!");
}

if (import.meta.url === `file://${process.argv[1]}`) {
    main().catch(console.error);
}
