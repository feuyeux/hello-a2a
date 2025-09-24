package com.google.a2a.client;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * Simple A2A Client Test without Jackson dependencies
 */
public class BasicClientTest {
    
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
        
        try {
            // Test 1: Get Agent Card
            System.out.println("=== Testing Agent Card Endpoint ===");
            HttpRequest agentCardRequest = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:8080/.well-known/agent-card"))
                .header("Accept", "application/json")
                .GET()
                .timeout(Duration.ofSeconds(10))
                .build();
            
            HttpResponse<String> agentCardResponse = client.send(agentCardRequest, 
                HttpResponse.BodyHandlers.ofString());
            
            System.out.println("Status: " + agentCardResponse.statusCode());
            System.out.println("Agent Card Response:");
            System.out.println(agentCardResponse.body());
            System.out.println();
            
            // Test 2: Test A2A JSON-RPC Endpoint
            System.out.println("=== Testing A2A JSON-RPC Endpoint ===");
            String jsonRpcRequest = "{\"jsonrpc\":\"2.0\",\"method\":\"test\",\"id\":\"client-test-123\"}";
            
            HttpRequest a2aRequest = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:8080/a2a"))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonRpcRequest))
                .timeout(Duration.ofSeconds(10))
                .build();
            
            HttpResponse<String> a2aResponse = client.send(a2aRequest, 
                HttpResponse.BodyHandlers.ofString());
            
            System.out.println("Status: " + a2aResponse.statusCode());
            System.out.println("A2A Response:");
            System.out.println(a2aResponse.body());
            System.out.println();
            
            System.out.println("✅ Client test completed successfully!");
            
        } catch (Exception e) {
            System.err.println("❌ Client test failed: " + e.getMessage());
            e.printStackTrace();
        }
    }
}