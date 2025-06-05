package com.google.a2a.client;

import com.google.a2a.model.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Test client to verify Ollama integration
 */
public class TestOllamaTranslation {
    
    public static void main(String[] args) {
        // Create client pointing to local server
        A2AClient client = new A2AClient("http://localhost:8080");
        
        try {
            System.out.println("=== Testing Ollama Translation Service ===");
            
            // Get agent card first
            AgentCard agentCard = client.getAgentCard();
            System.out.println("Agent: " + agentCard.name());
            System.out.println("Description: " + agentCard.description());
            System.out.println();
            
            // Test translation request
            TextPart testText = new TextPart("Hello, this is a test message for translation using Ollama qwen3:8b model.", null);
            
            Message message = new Message(
                UUID.randomUUID().toString(),
                "message",
                "user",
                List.of(testText),
                null,
                null,
                null,
                null
            );
            
            TaskSendParams params = new TaskSendParams(
                "ollama-test-task",
                null,
                message,
                null,
                null,
                Map.of()
            );
            
            System.out.println("Sending translation request: " + testText.text());
            JSONRPCResponse response = client.sendTask(params);
            Task task = (Task) response.result();
            
            System.out.println("Task ID: " + task.id());
            System.out.println("Status: " + task.status().state());
            
            if (task.history() != null && task.history().size() > 1) {
                Message lastMessage = task.history().get(task.history().size() - 1);
                if (lastMessage.role().equals("assistant") && !lastMessage.parts().isEmpty()) {
                    Part resultPart = lastMessage.parts().get(0);
                    if (resultPart instanceof TextPart textPart) {
                        System.out.println("Translation Result: " + textPart.text());
                    }
                }
            }
            
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
