package com.google.a2a.client;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * Manages a single remote agent process
 */
public class RemoteAgentProcess {
    
    private final String agentType;
    private final int port;
    private final String host;
    private final String llmProvider;
    private final String modelName;
    private final String url;
    private final HttpClient httpClient;
    private Process process;
    
    public RemoteAgentProcess(String agentType, int port, String llmProvider, String modelName) {
        this(agentType, port, "localhost", llmProvider, modelName);
    }
    
    public RemoteAgentProcess(String agentType, int port, String host, String llmProvider, String modelName) {
        this.agentType = agentType;
        this.port = port;
        this.host = host;
        this.llmProvider = llmProvider;
        this.modelName = modelName;
        this.url = "http://" + host + ":" + port;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();
    }
    
    /**
     * Start the agent process
     */
    public boolean start() {
        try {
            System.out.println("🚀 Starting " + agentType + " agent on port " + port + "...");
            
            // Build command for Python agent using virtual environment
            ProcessBuilder processBuilder = new ProcessBuilder(
                "/bin/bash", "-c",
                "source venv/bin/activate && python -m remotes." + agentType + 
                " --host " + host + 
                " --port " + port + 
                " --llm-provider " + llmProvider + 
                " --model-name " + modelName
            );
            
            // Set working directory to the Python project root
            processBuilder.directory(new java.io.File("/Users/han/coding/hello-a2a/hello-a2a-python"));
            
            // Start process
            process = processBuilder.start();
            
            // Wait for startup (check if agent is responding)
            for (int attempt = 0; attempt < 30; attempt++) { // 30 second timeout
                try {
                    HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(url + "/.well-known/agent.json"))
                        .timeout(Duration.ofSeconds(2))
                        .GET()
                        .build();
                    
                    HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                    if (response.statusCode() == 200) {
                        System.out.println("✅ " + agentType + " agent started successfully");
                        return true;
                    }
                } catch (Exception e) {
                    // Ignore and retry
                }
                
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            }
            
            System.out.println("❌ Failed to start " + agentType + " agent");
            return false;
            
        } catch (IOException e) {
            System.err.println("❌ Error starting " + agentType + ": " + e.getMessage());
            return false;
        }
    }
    
    /**
     * Stop the agent process
     */
    public void stop() {
        if (process != null) {
            try {
                process.destroy();
                boolean terminated = process.waitFor(5, TimeUnit.SECONDS);
                if (terminated) {
                    System.out.println("🛑 Stopped " + agentType + " agent");
                } else {
                    process.destroyForcibly();
                    System.out.println("🔥 Killed " + agentType + " agent");
                }
            } catch (InterruptedException e) {
                process.destroyForcibly();
                System.out.println("🔥 Killed " + agentType + " agent");
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                System.err.println("⚠️ Error stopping " + agentType + ": " + e.getMessage());
            }
        }
    }
    
    /**
     * Get the URL of the agent
     */
    public String getUrl() {
        return url;
    }
    
    /**
     * Get the agent type
     */
    public String getAgentType() {
        return agentType;
    }
    
    /**
     * Get the port
     */
    public int getPort() {
        return port;
    }
    
    /**
     * Check if the process is alive
     */
    public boolean isAlive() {
        return process != null && process.isAlive();
    }
}
