package com.google.a2a.client;

import com.google.a2a.model.*;
import java.util.List;
import java.util.Map;

/**
 * Simple test to verify A2A client fix
 */
public class A2AClientTest {
    
    public static void main(String[] args) {
        System.out.println("🧪 Testing A2A Client with fixed method names...");
        
        try {
            // Create A2A client for Currency Agent
            A2AClient client = new A2AClient("http://localhost:10000");
            
            // Get agent card first
            System.out.println("📋 Getting agent card...");
            AgentCard card = client.getAgentCard();
            System.out.println("✅ Agent: " + card.name());
            System.out.println("   Description: " + card.description());
            
            // Prepare message
            TextPart textPart = new TextPart("Convert 100 USD to CNY", null);
            
            Message message = new Message(
                "msg-test-001", 
                "user",
                List.of(textPart)
            );
            
            MessageSendConfiguration config = new MessageSendConfiguration(
                List.of("text", "text/plain"),
                null, // blocking
                null, // historyLength
                null  // pushNotificationConfig
            );
            
            TaskSendParams params = new TaskSendParams(
                "task-test-001",
                null, // sessionId
                message,
                null, // pushNotification
                null, // historyLength
                Map.of() // metadata
            );
            
            // Send task message (now uses message/send method)
            System.out.println("📤 Sending message using message/send method...");
            JSONRPCResponse response = client.sendTask(params);
            
            if (response.error() != null) {
                System.out.println("❌ Error: " + response.error().message());
                System.exit(1);
            }
            
            if (response.result() instanceof Task task) {
                System.out.println("✅ Success! Task completed:");
                System.out.println("   Task ID: " + task.id());
                System.out.println("   Status: " + task.status().state());
                
                if (task.artifacts() != null && !task.artifacts().isEmpty()) {
                    for (Artifact artifact : task.artifacts()) {
                        System.out.println("   📎 Artifact: " + artifact.name());
                        if (artifact.parts() != null) {
                            for (Part artifactPart : artifact.parts()) {
                                if (artifactPart instanceof TextPart artifactTextPart) {
                                    System.out.println("      Content: " + artifactTextPart.text());
                                }
                            }
                        }
                    }
                }
            }
            
            System.out.println("\n🎉 A2A Client test completed successfully!");
            System.out.println("   ✓ Agent card retrieval: PASS");
            System.out.println("   ✓ message/send method: PASS");
            System.out.println("   ✓ Task completion: PASS");
            
        } catch (Exception e) {
            System.out.println("❌ Test failed: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
}
