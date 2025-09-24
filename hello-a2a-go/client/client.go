package client

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"a2a/models"
)

// Client represents an A2A protocol client (v0.3.0 compliant)
type Client struct {
	baseURL    string
	httpClient *http.Client
}

// NewClient creates a new A2A client (v0.3.0 compliant)
func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 60 * time.Second, // Increased timeout for Ollama processing
		},
	}
}

// SendMessage sends a message to the agent (A2A v0.3.0 compliant)
func (c *Client) SendMessage(params models.MessageSendParams) (*models.JSONRPCResponse, error) {
	req := models.JSONRPCRequest{
		JSONRPCMessage: models.JSONRPCMessage{
			JSONRPC: "2.0",
			JSONRPCMessageIdentifier: models.JSONRPCMessageIdentifier{
				ID: params.ID + "-request",
			},
		},
		Method: "message/send",
		Params: params,
	}

	var resp models.JSONRPCResponse
	if err := c.doRequest(req, &resp); err != nil {
		return nil, err
	}

	if resp.Error != nil {
		return nil, fmt.Errorf("A2A error: %s (code: %d)", resp.Error.Message, resp.Error.Code)
	}

	return &resp, nil
}

// SendTask sends a task message to the agent (backwards compatibility)
func (c *Client) SendTask(params models.TaskSendParams) (*models.JSONRPCResponse, error) {
	// Convert TaskSendParams to MessageSendParams for compatibility
	msgParams := models.MessageSendParams{
		ID:      params.ID,
		Message: params.Message,
		Config:  nil, // TaskSendParams doesn't have config, set to nil
	}
	return c.SendMessage(msgParams)
}

// GetTask retrieves the status of a task (backwards compatibility)
func (c *Client) GetTask(params models.TaskQueryParams) (*models.JSONRPCResponse, error) {
	return c.ListMessages(params)
}

// SendTaskStreaming sends a task message and streams the response (backwards compatibility)
func (c *Client) SendTaskStreaming(params models.TaskSendParams, eventChan chan<- interface{}) error {
	// Convert TaskSendParams to MessageSendParams for compatibility
	msgParams := models.MessageSendParams{
		ID:      params.ID,
		Message: params.Message,
		Config:  nil, // TaskSendParams doesn't have config, set to nil
	}
	return c.SendMessageStreaming(msgParams, eventChan)
}

// ListMessages retrieves messages (A2A v0.3.0 compliant)
func (c *Client) ListMessages(params models.TaskQueryParams) (*models.JSONRPCResponse, error) {
	req := models.JSONRPCRequest{
		JSONRPCMessage: models.JSONRPCMessage{
			JSONRPC: "2.0",
			JSONRPCMessageIdentifier: models.JSONRPCMessageIdentifier{
				ID: params.ID + "-list-request",
			},
		},
		Method: "message/list",
		Params: params,
	}

	var resp models.JSONRPCResponse
	if err := c.doRequest(req, &resp); err != nil {
		return nil, err
	}

	if resp.Error != nil {
		return nil, fmt.Errorf("A2A error: %s (code: %d)", resp.Error.Message, resp.Error.Code)
	}

	return &resp, nil
}

// CancelTask cancels a task (A2A v0.3.0 compliant)
func (c *Client) CancelTask(params models.TaskIDParams) (*models.JSONRPCResponse, error) {
	req := models.JSONRPCRequest{
		JSONRPCMessage: models.JSONRPCMessage{
			JSONRPC: "2.0",
			JSONRPCMessageIdentifier: models.JSONRPCMessageIdentifier{
				ID: params.ID + "-cancel-request",
			},
		},
		Method: "message/pending",
		Params: params,
	}

	var resp models.JSONRPCResponse
	if err := c.doRequest(req, &resp); err != nil {
		return nil, err
	}

	if resp.Error != nil {
		return nil, fmt.Errorf("A2A error: %s (code: %d)", resp.Error.Message, resp.Error.Code)
	}

	return &resp, nil
}

// SendMessageStreaming sends a message and streams the response (A2A v0.3.0 compliant)
func (c *Client) SendMessageStreaming(params models.MessageSendParams, eventChan chan<- interface{}) error {
	req := models.JSONRPCRequest{
		JSONRPCMessage: models.JSONRPCMessage{
			JSONRPC: "2.0",
			JSONRPCMessageIdentifier: models.JSONRPCMessageIdentifier{
				ID: params.ID + "-stream-request",
			},
		},
		Method: "message/stream",
		Params: params,
	}

	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.baseURL, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")

	httpResp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	decoder := json.NewDecoder(httpResp.Body)
	for {
		var event models.SendMessageStreamingResponse
		if err := decoder.Decode(&event); err != nil {
			if err == io.EOF {
				break
			}
			return fmt.Errorf("failed to decode event: %w", err)
		}

		if event.Error != nil {
			return fmt.Errorf("A2A error: %s (code: %d)", event.Error.Message, event.Error.Code)
		}

		select {
		case eventChan <- event.Result:
		case <-httpReq.Context().Done():
			return httpReq.Context().Err()
		}
	}

	return nil
}

// doRequest performs the HTTP request and handles the response
func (c *Client) doRequest(req interface{}, resp *models.JSONRPCResponse) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequest("POST", c.baseURL, bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	httpResp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	// First decode into a map to handle the Result field correctly
	var rawResp struct {
		JSONRPC string               `json:"jsonrpc"`
		ID      interface{}          `json:"id,omitempty"`
		Result  json.RawMessage      `json:"result,omitempty"`
		Error   *models.JSONRPCError `json:"error,omitempty"`
	}

	if err := json.NewDecoder(httpResp.Body).Decode(&rawResp); err != nil {
		return fmt.Errorf("failed to decode response: %w", err)
	}

	// Copy the basic fields
	resp.JSONRPCMessage.JSONRPC = rawResp.JSONRPC
	resp.JSONRPCMessage.JSONRPCMessageIdentifier.ID = rawResp.ID
	resp.Error = rawResp.Error

	// If there's a result, try to decode it as a Task
	if len(rawResp.Result) > 0 {
		var task models.Task
		if err := json.Unmarshal(rawResp.Result, &task); err != nil {
			return fmt.Errorf("failed to decode task: %w", err)
		}
		resp.Result = &task
	}

	return nil
}

// GetAgentCard retrieves the agent card from the well-known endpoint (A2A v0.3.0 compliant)
func (c *Client) GetAgentCard() (*models.AgentCard, error) {
	httpReq, err := http.NewRequest("GET", c.baseURL+"/.well-known/agent-card", nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Accept", "application/json")

	httpResp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status code: %d", httpResp.StatusCode)
	}

	var agentCard models.AgentCard
	if err := json.NewDecoder(httpResp.Body).Decode(&agentCard); err != nil {
		return nil, fmt.Errorf("failed to decode agent card: %w", err)
	}

	return &agentCard, nil
}
