package main

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"a2a/client"
	"a2a/models"
)

func stringPtr(s string) *string {
	return &s
}

func main() {
	// Create A2A client
	a2aClient := client.NewClient("http://localhost:8080/a2a")

	// Test messages in different languages
	testMessages := []string{
		"你好，世界！",
		"Bonjour le monde!",
		"Hola mundo!",
		"こんにちは世界！",
		"안녕하세요 세계!",
	}

	fmt.Println("=== A2A Translation Client Test ===")
	fmt.Println("Testing translation using Ollama qwen3:8b model\n")

	for i, text := range testMessages {
		taskID := fmt.Sprintf("translation-task-%d", i+1)

		fmt.Printf("Test %d: Translating '%s'\n", i+1, text)

		// Create message
		message := models.Message{
			Role: "user",
			Parts: []models.Part{
				models.TextPart{
					Type: "text",
					Text: text,
				},
			},
		}

		// Send task
		response, err := a2aClient.SendTask(models.TaskSendParams{
			ID:      taskID,
			Message: message,
		})
		if err != nil {
			log.Printf("Failed to send task %s: %v\n", taskID, err)
			continue
		}

		// Check if we got a task response
		if response.Result == nil {
			log.Printf("No result in response for task %s\n", taskID)
			continue
		}

		// Try to get the task as a Task object
		taskData, err := json.Marshal(response.Result)
		if err != nil {
			log.Printf("Failed to marshal task result: %v\n", err)
			continue
		}

		var task models.Task
		if err := json.Unmarshal(taskData, &task); err != nil {
			log.Printf("Failed to unmarshal task: %v\n", err)
			continue
		}

		fmt.Printf("Task Status: %s\n", task.Status.State)

		if task.Status.State == models.TaskStateCompleted {
			fmt.Printf("Translation completed successfully! (Check server logs for result)\n")
		} else if task.Status.State == models.TaskStateFailed {
			fmt.Printf("Translation failed!\n")
		}

		fmt.Println("---")
		time.Sleep(1 * time.Second) // Small delay between requests
	}

	// Test streaming functionality
	fmt.Println("\n=== Testing Streaming Translation ===")

	streamingTaskID := "streaming-translation-task"
	streamingMessage := models.Message{
		Role: "user",
		Parts: []models.Part{
			models.TextPart{
				Type: "text",
				Text: "请将这段中文翻译成英文：今天天气真好！",
			},
		},
	}

	// Create channel for streaming events
	eventChan := make(chan interface{}, 10)

	// Start streaming in a goroutine
	go func() {
		err := a2aClient.SendTaskStreaming(models.TaskSendParams{
			ID:      streamingTaskID,
			Message: streamingMessage,
		}, eventChan)
		if err != nil {
			log.Printf("Streaming error: %v\n", err)
		}
		close(eventChan)
	}()

	// Read streaming events
	fmt.Println("Streaming translation events:")
	for event := range eventChan {
		eventData, _ := json.MarshalIndent(event, "", "  ")
		fmt.Printf("Event: %s\n", eventData)
	}

	fmt.Println("\n=== Test Complete ===")
}
