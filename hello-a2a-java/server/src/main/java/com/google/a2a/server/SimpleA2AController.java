package com.google.a2a.server;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Simple A2A REST controller for handling basic requests
 */
@RestController
public class SimpleA2AController {

    /**
     * Handle JSON-RPC requests
     */
    @PostMapping("/a2a")
    public ResponseEntity<Map<String, Object>> handleJsonRpcRequest(@RequestBody Map<String, Object> request) {
        // Simple response for now
        Map<String, Object> response = Map.of(
            "jsonrpc", "2.0",
            "id", request.get("id"),
            "result", Map.of(
                "status", "success",
                "message", "A2A server is running"
            )
        );
        return ResponseEntity.ok(response);
    }

    /**
     * Get agent card information
     */
    @GetMapping("/.well-known/agent-card")
    public ResponseEntity<Map<String, Object>> getAgentCard() {
        Map<String, Object> agentCard = Map.of(
            "name", "AI Translation Bot (Ollama qwen3:8b)",
            "description", "Professional AI translation service powered by local Ollama qwen3:8b model",
            "url", "http://localhost:8080",
            "version", "1.0.0",
            "capabilities", Map.of(
                "streaming", true,
                "pushNotifications", false,
                "stateTransitionHistory", true
            ),
            "defaultInputModes", java.util.List.of("text"),
            "defaultOutputModes", java.util.List.of("text"),
            "skills", java.util.List.of(
                Map.of(
                    "id", "ai-translator",
                    "name", "AI Translation Service",
                    "description", "Professional AI translator supporting multiple languages",
                    "tags", java.util.List.of("translation", "language", "ai")
                )
            )
        );
        return ResponseEntity.ok(agentCard);
    }
}