package com.google.a2a.client.util;

import java.util.List;

/**
 * Uses rule-based logic to select appropriate agent for user queries
 * (Can be enhanced with LLM integration later)
 */
public class LLMAgentSelector {
    
    private final String llmProvider;
    private final String modelName;
    
    public LLMAgentSelector(String llmProvider, String modelName) {
        this.llmProvider = llmProvider;
        this.modelName = modelName;
    }
    
    /**
     * Select the best agent for the user query using rule-based logic
     */
    public String selectAgent(String userQuery, List<RemoteAgentRegistry.AgentInfo> availableAgents) {
        if (availableAgents.isEmpty()) {
            return null;
        }
        
        // Simple rule-based selection
        String lowerQuery = userQuery.toLowerCase();
        
        // Rule-based agent selection
        if (lowerQuery.contains("currency") || lowerQuery.contains("exchange") || 
            lowerQuery.contains("convert") || lowerQuery.contains("usd") || 
            lowerQuery.contains("cny") || lowerQuery.contains("eur") ||
            lowerQuery.contains("dollar") || lowerQuery.contains("yuan")) {
            return findAgentByKeyword(availableAgents, "currency");
        }
        
        if (lowerQuery.contains("youtube") || lowerQuery.contains("video") || 
            lowerQuery.contains("caption") || lowerQuery.contains("analyze")) {
            return findAgentByKeyword(availableAgents, "youtube");
        }
        
        if (lowerQuery.contains("travel") || lowerQuery.contains("trip") || 
            lowerQuery.contains("plan") || lowerQuery.contains("vacation")) {
            return findAgentByKeyword(availableAgents, "travel");
        }
        
        if (lowerQuery.contains("expense") || lowerQuery.contains("reimbursement") || 
            lowerQuery.contains("receipt") || lowerQuery.contains("claim")) {
            return findAgentByKeyword(availableAgents, "reimbursement");
        }
        
        if (lowerQuery.contains("file") || lowerQuery.contains("document") || 
            lowerQuery.contains("parse") || lowerQuery.contains("chat") ||
            lowerQuery.contains("read") || lowerQuery.contains("text")) {
            return findAgentByKeyword(availableAgents, "file");
        }
        
        // Default to first available agent
        return availableAgents.isEmpty() ? null : availableAgents.get(0).name();
    }
    
    /**
     * Find agent by keyword in name or description
     */
    private String findAgentByKeyword(List<RemoteAgentRegistry.AgentInfo> agents, String keyword) {
        for (RemoteAgentRegistry.AgentInfo agent : agents) {
            if (agent.name().toLowerCase().contains(keyword) || 
                agent.description().toLowerCase().contains(keyword)) {
                return agent.name();
            }
        }
        return null;
    }
}
