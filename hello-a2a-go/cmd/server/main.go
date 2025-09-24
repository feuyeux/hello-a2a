package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"a2a/models"
	"a2a/server"
)

// OllamaRequest represents the request structure for Ollama API
type OllamaRequest struct {
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
	Stream bool   `json:"stream"`
}

// OllamaResponse represents the response structure from Ollama API
type OllamaResponse struct {
	Model     string    `json:"model"`
	CreatedAt time.Time `json:"created_at"`
	Response  string    `json:"response"`
	Done      bool      `json:"done"`
}

// callOllama makes a direct HTTP call to the local Ollama API
func callOllama(prompt string) (string, error) {
	reqBody := OllamaRequest{
		Model:  "qwen3:8b",
		Prompt: prompt,
		Stream: false,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	client := &http.Client{
		Timeout: 2 * time.Minute,
	}

	resp, err := client.Post("http://localhost:11434/api/generate", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("failed to call Ollama: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("Ollama API returned status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read response: %w", err)
	}

	var ollamaResp OllamaResponse
	if err := json.Unmarshal(body, &ollamaResp); err != nil {
		return "", fmt.Errorf("failed to unmarshal response: %w", err)
	}

	return ollamaResp.Response, nil
}

// translationTaskHandler handles translation tasks using Ollama
func translationTaskHandler(task *models.Task, message *models.Message) (*models.Task, error) {
	// Extract text from message parts
	var inputText string
	for _, part := range message.Parts {
		if textPart, ok := part.(models.TextPart); ok {
			inputText += textPart.Text
		}
	}

	if inputText == "" {
		task.Status.State = models.TaskStateFailed
		return task, fmt.Errorf("no text found in message")
	}

	// Create translation prompt
	prompt := fmt.Sprintf("Please translate the following text to English: %s", inputText)

	// Call Ollama for translation
	translatedText, err := callOllama(prompt)
	if err != nil {
		task.Status.State = models.TaskStateFailed
		return task, fmt.Errorf("translation failed: %w", err)
	}

	// Update task status to completed
	task.Status.State = models.TaskStateCompleted

	// Note: In this simplified version, we don't store the result in the task
	// but it would be available through the task store for retrieval
	log.Printf("Translation completed for task %s: %s -> %s", task.ID, inputText, translatedText)

	return task, nil
}

func stringPtr(s string) *string {
	return &s
}

func main() {
	// Create agent card
	agentCard := models.AgentCard{
		Name:        "Translation Agent",
		Description: stringPtr("A2A translation agent using Ollama qwen3:8b model"),
		URL:         "http://localhost:8080",
		Version:     "1.0.0",
		Provider: &models.AgentProvider{
			Organization: "Local Development",
			URL:          stringPtr("http://localhost:8080"),
		},
		Capabilities: models.AgentCapabilities{
			Streaming:              boolPtr(true),
			PushNotifications:      boolPtr(false),
			StateTransitionHistory: boolPtr(true),
		},
		Skills: []models.AgentSkill{
			{
				ID:          "translate",
				Name:        "Text Translation",
				Description: stringPtr("Translate text using Ollama qwen3:8b model"),
				Tags:        []string{"translation", "nlp", "ollama"},
			},
		},
	}

	// Create server
	srv := server.NewA2AServer(agentCard, translationTaskHandler)

	log.Println("Starting A2A Translation Server on http://localhost:8080")
	log.Println("Using Ollama qwen3:8b model for translations")

	// Start HTTP server
	mux := http.NewServeMux()

	// Add agent card endpoint
	mux.HandleFunc("/.well-known/agent-card", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(agentCard)
	})

	// Add A2A endpoints
	mux.HandleFunc("/a2a", srv.ServeHTTP)
	mux.HandleFunc("/a2a/stream", srv.ServeHTTP)

	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatal("Failed to start server:", err)
	}
}

func boolPtr(b bool) *bool {
	return &b
}
