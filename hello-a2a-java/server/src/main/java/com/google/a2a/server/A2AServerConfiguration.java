package com.google.a2a.server;

import com.google.a2a.model.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A2A server configuration class - AI Translation Bot
 */
@Configuration
public class A2AServerConfiguration {

    /**
     * Configure A2AServer bean
     */
    @Bean
    public A2AServer a2aServer(ObjectMapper objectMapper) {
        // Create translation agent card
        AgentCard agentCard = createTranslationAgentCard();

        // Create translation task handler with Ollama
        TaskHandler taskHandler = createOllamaTranslationTaskHandler(objectMapper);

        return new A2AServer(agentCard, taskHandler, objectMapper);
    }

    /**
     * Create translation agent card
     */
    private AgentCard createTranslationAgentCard() {
        AgentProvider provider = new AgentProvider(
            "Google",
            "https://google.com"
        );

        AgentCapabilities capabilities = new AgentCapabilities(
            true,  // streaming
            true,  // pushNotifications
            true   // stateTransitionHistory
        );

        AgentAuthentication authentication = new AgentAuthentication(
            List.of("bearer"),
            null
        );

        AgentSkill skill = new AgentSkill(
            "ai-translator",
            "AI Translation Service",
            "Professional AI translator supporting multiple languages. Can translate text between various language pairs including English, Chinese, Japanese, French, Spanish, German, and more.",
            List.of("translation", "language", "ai", "multilingual"),
            List.of(
                "Example: Translate 'Hello World' to Chinese",
                "Example: 请把这句话翻译成英文: '你好'",
                "Example: Translate from French to Spanish: 'Bonjour le monde'"
            ),
            List.of("text"),
            List.of("text")
        );

        return new AgentCard(
            "AI Translation Bot (Ollama qwen3:8b)",
            "Professional AI translation service powered by local Ollama qwen3:8b model. Supports translation between multiple languages with high accuracy and context awareness.",
            "http://localhost:8080/a2a",
            provider,
            "1.0.0",
            "http://localhost:8080/docs",
            capabilities,
            authentication,
            List.of("text"),
            List.of("text"),
            List.of(skill)
        );
    }

    /**
     * Create translation task handler using Ollama local API
     */
    private TaskHandler createOllamaTranslationTaskHandler(ObjectMapper objectMapper) {
        // Create HTTP client for Ollama API calls
        HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();

        return (task, message) -> {
            try {
                // Extract text content from message parts
                String textToTranslate = extractTextFromMessage(message);

                if (textToTranslate == null || textToTranslate.trim().isEmpty()) {
                    return createErrorTask(task, "No text content found in the message");
                }

                // Create translation prompt
                String translationPrompt = createTranslationPrompt(textToTranslate);

                // Call Ollama API for translation
                String translatedText = callOllamaAPI(httpClient, objectMapper, translationPrompt);

                // Create response message with translation
                TextPart responsePart = new TextPart(translatedText, null);
                Message responseMessage = new Message(
                    UUID.randomUUID().toString(),
                    "message",
                    "assistant",
                    List.of(responsePart),
                    message.contextId(),
                    task.id(),
                    List.of(message.messageId()),
                    null
                );

                // Create completed status
                TaskStatus completedStatus = new TaskStatus(
                    TaskState.COMPLETED,
                    null,  // No status message
                    Instant.now().toString()
                );

                // Add response to history
                List<Message> updatedHistory = task.history() != null ?
                    List.of(task.history().toArray(new Message[0])) :
                    List.of();
                updatedHistory = List.of(
                    java.util.stream.Stream.concat(
                        updatedHistory.stream(),
                        java.util.stream.Stream.of(message, responseMessage)
                    ).toArray(Message[]::new)
                );

                return new Task(
                    task.id(),
                    task.contextId(),
                    task.kind(),
                    completedStatus,
                    task.artifacts(),
                    updatedHistory,
                    task.metadata()
                );

            } catch (Exception e) {
                return createErrorTask(task, "Translation failed: " + e.getMessage());
            }
        };
    }

    /**
     * Call Ollama API for text generation
     */
    private String callOllamaAPI(HttpClient httpClient, ObjectMapper objectMapper, String prompt) throws Exception {
        // Prepare Ollama API request payload
        Map<String, Object> requestBody = Map.of(
            "model", "qwen3:8b",
            "prompt", prompt,
            "stream", false
        );

        String requestJson = objectMapper.writeValueAsString(requestBody);

        // Create HTTP request
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:11434/api/generate"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestJson))
            .timeout(Duration.ofMinutes(2))
            .build();

        // Send request and get response
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new RuntimeException("Ollama API call failed with status: " + response.statusCode() + ", body: " + response.body());
        }

        // Parse response to extract generated text
        JsonNode responseNode = objectMapper.readTree(response.body());
        if (responseNode.has("response")) {
            return responseNode.get("response").asText();
        } else {
            throw new RuntimeException("Invalid response from Ollama API: " + response.body());
        }
    }

    /**
     * Extract text content from message parts
     */
    private String extractTextFromMessage(Message message) {
        if (message.parts() == null || message.parts().isEmpty()) {
            return null;
        }

        StringBuilder textBuilder = new StringBuilder();
        for (Part part : message.parts()) {
            if (part instanceof TextPart textPart) {
                if (textBuilder.length() > 0) {
                    textBuilder.append("\n");
                }
                textBuilder.append(textPart.text());
            }
        }

        return textBuilder.toString();
    }

    /**
     * Create translation prompt for ChatClient
     */
    private String createTranslationPrompt(String text) {
        return String.format("""
            You are a professional translator. Please translate the following text to the most appropriate target language.
            
            Instructions:
            1. If the text is in Chinese, translate to English
            2. If the text is in English, translate to Chinese
            3. If the text is in other languages, translate to English
            4. Maintain the original meaning and context
            5. Provide natural, fluent translations
            6. Only return the translated text, no explanations
            
            Text to translate: %s
            """, text);
    }

    /**
     * Create error task for translation failures
     */
    private Task createErrorTask(Task originalTask, String errorMessage) {
        TaskStatus errorStatus = new TaskStatus(
            TaskState.FAILED,
            null,  // No status message
            Instant.now().toString()
        );

        return new Task(
            originalTask.id(),
            originalTask.contextId(),
            originalTask.kind(),
            errorStatus,
            originalTask.artifacts(),
            originalTask.history(),
            originalTask.metadata()
        );
    }
}
