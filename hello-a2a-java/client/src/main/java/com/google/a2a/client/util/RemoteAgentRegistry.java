package com.google.a2a.client.util;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.a2a.client.A2AClient;
import com.google.a2a.model.AgentCard;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;


/**
 * Manages registration and communication with remote agents
 */
public class RemoteAgentRegistry {
    
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final Map<String, AgentCard> agents;
    private final Map<String, A2AClient> clients;
    
    public RemoteAgentRegistry(HttpClient httpClient, ObjectMapper objectMapper) {
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
        this.agents = new ConcurrentHashMap<>();
        this.clients = new ConcurrentHashMap<>();
    }
    
    /**
     * Register an agent by resolving its card
     */
    public AgentCard registerAgent(String url) {
        try {
            // Get agent card
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url + "/.well-known/agent-card"))
                .header("Accept", "application/json")
                .GET()
                .build();
            
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            
            if (response.statusCode() != 200) {
                System.err.println("❌ Failed to get agent card from " + url + ": HTTP " + response.statusCode());
                return null;
            }
            
            AgentCard card = objectMapper.readValue(response.body(), AgentCard.class);
            
            // Create a new card with the URL set
            AgentCard cardWithUrl = new AgentCard(
                card.name(),
                card.description(),
                url,  // Set the URL
                card.provider(),
                card.version(),
                card.documentationUrl(),
                card.capabilities(),
                card.authentication(),
                card.defaultInputModes(),
                card.defaultOutputModes(),
                card.skills()
            );
            
            // Create A2A client for this agent
            A2AClient client = new A2AClient(url, httpClient);
            
            agents.put(card.name(), cardWithUrl);
            clients.put(card.name(), client);
            
            System.out.println("📋 Registered agent: " + card.name());
            System.out.println("   Description: " + card.description());
            System.out.println("   URL: " + url);
            
            return cardWithUrl;
            
        } catch (Exception e) {
            System.err.println("❌ Failed to register agent at " + url + ": " + e.getMessage());
            return null;
        }
    }
    
    /**
     * List all registered agents
     */
    public List<AgentInfo> listAgents() {
        List<AgentInfo> agentInfoList = new ArrayList<>();
        for (AgentCard card : agents.values()) {
            agentInfoList.add(new AgentInfo(
                card.name(),
                card.description() != null ? card.description() : "No description",
                card.url() != null ? card.url() : "unknown"
            ));
        }
        return agentInfoList;
    }
    
    /**
     * AgentInfo record for listing agents
     */
    public record AgentInfo(
        String name,
        String description,
        String url
    ) {}
    
    /**
     * Get an A2A client for a specific agent
     */
    public A2AClient getClient(String agentName) {
        return clients.get(agentName);
    }
    
    /**
     * Get an agent card for a specific agent
     */
    public AgentCard getAgentCard(String agentName) {
        return agents.get(agentName);
    }
    
    /**
     * Check if an agent is registered
     */
    public boolean isAgentRegistered(String agentName) {
        return agents.containsKey(agentName);
    }
    
    /**
     * Get all registered agent names
     */
    public List<String> getAgentNames() {
        return new ArrayList<>(agents.keySet());
    }
    
    /**
     * Remove an agent from the registry
     */
    public void removeAgent(String agentName) {
        agents.remove(agentName);
        clients.remove(agentName);
    }
    
    /**
     * Clear all registered agents
     */
    public void clear() {
        agents.clear();
        clients.clear();
    }
}
