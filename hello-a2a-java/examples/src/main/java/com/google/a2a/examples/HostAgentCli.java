package com.google.a2a.examples;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.a2a.client.A2AClient;
import com.google.a2a.client.StreamingEventListener;
import com.google.a2a.client.util.LLMAgentSelector;
import com.google.a2a.client.util.RemoteAgentRegistry;
import com.google.a2a.client.util.RemoteAgentProcess;
import io.a2a.spec.*;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;


/**
 * Host Agent CLI for A2A Multi-Agent System
 * 
 * This CLI acts as a host agent that manages and communicates with multiple remote agents:
 * 1. Auto-startup of 5 remote agents with A2A protocol registration
 * 2. LLM-based intelligent agent selection for user queries  
 * 3. A2A protocol communication with selected remote agents
 * 4. Streaming and non-streaming response handling
 * 
 * Usage: java HostAgentCli [--auto-start] [--llm-provider ollama|lmstudio] [--model-name MODEL]
 */
public class HostAgentCli {
    
    // Remote agent configurations (following README port assignments)
    private static final Map<String, AgentConfig> REMOTE_AGENTS = Map.of(
        "langgraph", new AgentConfig(10000, "Currency exchange agent"),
        "ag2", new AgentConfig(10010, "YouTube video analysis agent"),
        "google_adk", new AgentConfig(10020, "Reimbursement processing agent"),
        "semantickernel", new AgentConfig(10030, "Travel planning agent"),
        "llama_index_file_chat", new AgentConfig(10040, "File parsing and chat agent")
    );
    
    private final boolean autoStart;
    private final String llmProvider;
    private final String modelName;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final Map<String, RemoteAgentProcess> agentProcesses;
    private final RemoteAgentRegistry registry;
    private final LLMAgentSelector selector;
    private final Scanner scanner;
    
    public HostAgentCli(boolean autoStart, String llmProvider, String modelName) {
        this.autoStart = autoStart;
        this.llmProvider = llmProvider;
        this.modelName = modelName;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();
        this.objectMapper = new ObjectMapper();
        this.agentProcesses = new ConcurrentHashMap<>();
        this.registry = new RemoteAgentRegistry(httpClient, objectMapper);
        this.selector = new LLMAgentSelector(llmProvider, modelName);
        this.scanner = new Scanner(System.in);
        
        // Setup shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(this::cleanup));
    }
    
    /**
     * Start all remote agents
     */
    public boolean startRemoteAgents() {
        System.out.println("🔄 Starting remote agents...");
        
        int successCount = 0;
        for (Map.Entry<String, AgentConfig> entry : REMOTE_AGENTS.entrySet()) {
            String agentType = entry.getKey();
            AgentConfig config = entry.getValue();
            
            RemoteAgentProcess agentProcess = new RemoteAgentProcess(
                agentType, config.port(), llmProvider, modelName
            );
            
            if (agentProcess.start()) {
                agentProcesses.put(agentType, agentProcess);
                successCount++;
            } else {
                System.out.println("⚠️ Failed to start " + agentType);
            }
        }
        
        System.out.println("✅ Started " + successCount + "/" + REMOTE_AGENTS.size() + " agents");
        return successCount > 0;
    }
    
    /**
     * Register all started agents
     */
    public boolean registerAllAgents() {
        System.out.println("📋 Registering agents...");
        
        int successCount = 0;
        for (Map.Entry<String, RemoteAgentProcess> entry : agentProcesses.entrySet()) {
            String agentType = entry.getKey();
            RemoteAgentProcess process = entry.getValue();
            
            AgentCard card = registry.registerAgent(process.getUrl());
            if (card != null) {
                successCount++;
            }
        }
        
        System.out.println("✅ Registered " + successCount + "/" + agentProcesses.size() + " agents");
        return successCount > 0;
    }
    
    /**
     * Handle a user query by selecting and communicating with an agent
     */
    public boolean handleUserQuery(String query) {
        // Get available agents
        List<RemoteAgentRegistry.AgentInfo> availableAgents = registry.listAgents();
        if (availableAgents.isEmpty()) {
            System.out.println("❌ No agents available");
            return false;
        }
        
        System.out.println("\n🤔 Analyzing query: '" + query + "'");
        System.out.println("🔍 Available agents:");
        for (RemoteAgentRegistry.AgentInfo agent : availableAgents) {
            System.out.println("   - " + agent.name() + ": " + agent.description());
        }
        
        // Use LLM to select agent
        String selectedAgentName = selector.selectAgent(query, availableAgents);
        
        if (selectedAgentName == null) {
            System.out.println("❌ No suitable agent found for this query");
            return false;
        }
        
        System.out.println("🎯 Selected agent: " + selectedAgentName);
        
        // Get agent client and card
        A2AClient client = registry.getClient(selectedAgentName);
        AgentCard card = registry.getAgentCard(selectedAgentName);
        
        if (client == null || card == null) {
            System.out.println("❌ Client for " + selectedAgentName + " not found");
            return false;
        }
        
        // Prepare message
        TextPart textPart = new TextPart(query, null);
        Message message = new Message(
            UUID.randomUUID().toString(),  // messageId
            "message",                     // kind
            "user",                        // role
            List.of(textPart),            // parts
            null,                         // contextId
            null,                         // taskId
            null,                         // referenceTaskIds
            null                          // metadata
        );
        
        TaskSendParams params = new TaskSendParams(
            "host-query-" + UUID.randomUUID().toString(),
            null,  // sessionId
            message,
            null,  // pushNotification
            null,  // historyLength
            Map.of()  // metadata
        );
        
        System.out.println("📤 Sending message to " + selectedAgentName + "...");
        
        try {
            // Check if agent supports streaming
            if (card.capabilities() != null && card.capabilities().streaming() != null && card.capabilities().streaming()) {
                System.out.println("🌊 Using streaming communication...");
                
                CountDownLatch streamingLatch = new CountDownLatch(1);
                
                client.sendTaskStreaming(params, new StreamingEventListener() {
                    @Override
                    public void onEvent(Object event) {
                        handleStreamingEvent(selectedAgentName, event);
                    }
                    
                    @Override
                    public void onError(Exception exception) {
                        System.err.println("❌ Streaming error: " + exception.getMessage());
                        streamingLatch.countDown();
                    }
                    
                    @Override
                    public void onComplete() {
                        System.out.println("✅ Streaming completed");
                        streamingLatch.countDown();
                    }
                });
                
                // Wait for streaming to complete
                if (streamingLatch.await(30, TimeUnit.SECONDS)) {
                    System.out.println("✅ Streaming finished successfully");
                } else {
                    System.out.println("⚠️ Streaming timed out");
                }
            } else {
                System.out.println("📞 Using non-streaming communication...");
                
                JSONRPCResponse response = client.sendTask(params);
                
                if (response.error() != null) {
                    System.out.println("❌ Agent error: " + response.error().message());
                    return false;
                }
                
                handleNonStreamingResponse(selectedAgentName, response.result());
            }
            
            return true;
            
        } catch (Exception e) {
            System.err.println("❌ Error communicating with " + selectedAgentName + ": " + e.getMessage());
            return false;
        }
    }
    
    /**
     * Handle streaming event from agent
     */
    private void handleStreamingEvent(String agentName, Object event) {
        System.out.println("📨 Received event type: " + event.getClass().getSimpleName());
        
        if (event instanceof Task task) {
            System.out.println("\n📋 " + agentName + " task:");
            System.out.println("   Task ID: " + task.id());
            System.out.println("   Status: " + (task.status() != null ? task.status().state() : "Unknown"));
            
            // Print task history if available
            if (task.history() != null && !task.history().isEmpty()) {
                System.out.println("   📜 History (" + task.history().size() + " messages):");
                for (int i = 0; i < task.history().size(); i++) {
                    Message msg = task.history().get(i);
                    System.out.println("      Message " + (i + 1) + " (" + msg.role() + "):");
                    if (msg.parts() != null) {
                        for (int j = 0; j < msg.parts().size(); j++) {
                            Part part = msg.parts().get(j);
                            if (part instanceof TextPart textPart) {
                                System.out.println("         " + textPart.text());
                            }
                        }
                    }
                }
            }
        } else {
            System.out.println("   ❓ Unknown event: " + event);
        }
    }
    
    /**
     * Handle non-streaming response from agent
     */
    private void handleNonStreamingResponse(String agentName, Object result) {
        System.out.println("📨 Received result type: " + result.getClass().getSimpleName());
        
        if (result instanceof Task task) {
            System.out.println("\n📋 " + agentName + " task:");
            System.out.println("   Task ID: " + task.id());
            System.out.println("   Status: " + (task.status() != null ? task.status().state() : "Unknown"));
            
            // Print task history if available
            if (task.history() != null && !task.history().isEmpty()) {
                System.out.println("   📜 History (" + task.history().size() + " messages):");
                for (int i = 0; i < task.history().size(); i++) {
                    Message msg = task.history().get(i);
                    if ("assistant".equals(msg.role()) && msg.parts() != null) {
                        for (Part part : msg.parts()) {
                            if (part instanceof TextPart textPart) {
                                System.out.println("      " + textPart.text());
                            }
                        }
                    }
                }
            }
        } else {
            System.out.println("   ❓ Unknown result type: " + result);
        }
    }
    
    /**
     * Run interactive CLI mode for the host agent
     */
    public void runInteractiveMode() {
        System.out.println("\n🎉 Host Agent CLI Ready!");
        System.out.println("As a host agent, I can help you communicate with remote agents.");
        System.out.println("Type your queries below. Type 'quit' or ':q' to exit.");
        System.out.println("Type 'agents' to list available remote agents.");
        System.out.println("-".repeat(60));
        
        while (true) {
            try {
                System.out.print("\n💬 Your query: ");
                String query = scanner.nextLine().trim();
                
                if (query.equalsIgnoreCase("quit") || query.equals(":q") || query.equalsIgnoreCase("exit")) {
                    break;
                } else if (query.equalsIgnoreCase("agents")) {
                    List<AgentInfo> agents = registry.listAgents();
                    System.out.println("\n📋 Available remote agents:");
                    for (AgentInfo agent : agents) {
                        System.out.println("   • " + agent.name() + ": " + agent.description());
                    }
                } else if (!query.isEmpty()) {
                    handleUserQuery(query);
                }
                
            } catch (Exception e) {
                System.err.println("❌ Error: " + e.getMessage());
            }
        }
    }
    
    /**
     * Cleanup processes and resources
     */
    public void cleanup() {
        System.out.println("\n🧹 Cleaning up...");
        
        // Stop all agent processes
        for (RemoteAgentProcess process : agentProcesses.values()) {
            process.stop();
        }
        
        // Close scanner
        scanner.close();
        
        System.out.println("✅ Cleanup completed");
    }
    
    /**
     * Main run method
     */
    public void run() {
        try {
            if (autoStart) {
                // Start remote agents
                if (!startRemoteAgents()) {
                    System.err.println("❌ Failed to start agents");
                    return;
                }
                
                // Wait a bit for agents to stabilize
                try {
                    Thread.sleep(2000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                
                // Register agents
                if (!registerAllAgents()) {
                    System.err.println("❌ Failed to register agents");
                    return;
                }
            } else {
                System.out.println("🔧 Manual mode: Agents should be started separately");
                // Try to register any already running agents
                for (Map.Entry<String, AgentConfig> entry : REMOTE_AGENTS.entrySet()) {
                    String agentType = entry.getKey();
                    AgentConfig config = entry.getValue();
                    String url = "http://localhost:" + config.port();
                    registry.registerAgent(url);
                }
            }
            
            // Run interactive mode
            runInteractiveMode();
            
        } finally {
            cleanup();
        }
    }
    
    /**
     * Main entry point
     */
    public static void main(String[] args) {
        boolean autoStart = false;
        String llmProvider = "lmstudio";
        String modelName = "qwen3-8b";
        
        // Parse command line arguments
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--auto-start":
                    autoStart = true;
                    break;
                case "--llm-provider":
                    if (i + 1 < args.length) {
                        llmProvider = args[++i];
                    }
                    break;
                case "--model-name":
                    if (i + 1 < args.length) {
                        modelName = args[++i];
                    }
                    break;
                case "--help":
                    printUsage();
                    return;
            }
        }
        
        System.out.println("🚀 Starting Host Agent CLI...");
        System.out.println("   Auto-start: " + autoStart);
        System.out.println("   LLM Provider: " + llmProvider);
        System.out.println("   Model Name: " + modelName);
        
        HostAgentCli cli = new HostAgentCli(autoStart, llmProvider, modelName);
        cli.run();
    }
    
    private static void printUsage() {
        System.out.println("Host Agent CLI for A2A Multi-Agent System");
        System.out.println();
        System.out.println("Usage: java HostAgentCli [options]");
        System.out.println();
        System.out.println("Options:");
        System.out.println("  --auto-start                 Automatically start remote agents");
        System.out.println("  --llm-provider <provider>    LLM provider (ollama|lmstudio, default: lmstudio)");
        System.out.println("  --model-name <model>         LLM model name (default: qwen3-8b)");
        System.out.println("  --help                       Show this help message");
    }
    
    /**
     * Agent configuration record
     */
    public record AgentConfig(int port, String description) {}
    
    /**
     * Agent information record
     */

}
