/**
 * Ollama client for local AI model integration
 */

interface OllamaResponse {
    model: string;
    response: string;
    done: boolean;
    context?: number[];
}

interface OllamaGenerateRequest {
    model: string;
    prompt: string;
    stream?: boolean;
    system?: string;
}

export class OllamaClient {
    private baseUrl: string;

    constructor(baseUrl: string = 'http://localhost:11434') {
        this.baseUrl = baseUrl;
    }

    async generate(request: OllamaGenerateRequest): Promise<string> {
        try {
            const response = await fetch(`${this.baseUrl}/api/generate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ...request,
                    stream: false, // For non-streaming responses
                }),
            });

            if (!response.ok) {
                throw new Error(`Ollama API error: ${response.status} ${response.statusText}`);
            }

            const data: OllamaResponse = await response.json();
            return data.response;
        } catch (error) {
            console.error('Error calling Ollama API:', error);
            throw new Error(`Failed to generate response from Ollama: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    async *generateStream(request: OllamaGenerateRequest): AsyncGenerator<string, void, unknown> {
        try {
            const response = await fetch(`${this.baseUrl}/api/generate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ...request,
                    stream: true, // Enable streaming
                }),
            });

            if (!response.ok) {
                throw new Error(`Ollama API error: ${response.status} ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error('No response body from Ollama API');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n').filter(line => line.trim());

                    for (const line of lines) {
                        try {
                            const data: OllamaResponse = JSON.parse(line);
                            if (data.response) {
                                yield data.response;
                            }
                            if (data.done) {
                                return;
                            }
                        } catch (parseError) {
                            // Skip invalid JSON lines
                            console.warn('Failed to parse Ollama response line:', line);
                        }
                    }
                }
            } finally {
                reader.releaseLock();
            }
        } catch (error) {
            console.error('Error in Ollama streaming:', error);
            throw new Error(`Failed to stream from Ollama: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    async checkHealth(): Promise<boolean> {
        try {
            const response = await fetch(`${this.baseUrl}/api/tags`, {
                method: 'GET',
            });
            return response.ok;
        } catch (error) {
            console.error('Ollama health check failed:', error);
            return false;
        }
    }
}

export const ollamaClient = new OllamaClient();
