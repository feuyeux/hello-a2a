# Hello Agent2Agent (A2A) Protocol with Ollama Integration

## Resources

- 🔗 A2A Protocol Specification https://a2a-protocol.org/latest/
- 🔗 Official A2A SDK Documentation https://a2a-protocol.org/latest/sdk
    - A2A https://github.com/a2aproject/A2A
    - [A2A Java SDK](https://github.com/a2aproject/a2a-java) https://github.com/a2aproject/a2a-java/tags
    - [A2A Python SDK](https://github.com/a2aproject/a2a-python) https://github.com/a2aproject/a2a-python/tags
    - [A2A JavaScript SDK](https://github.com/a2aproject/a2a-js) https://github.com/a2aproject/a2a-js/tags
    - [A2A .NET SDK](https://github.com/a2aproject/a2a-dotnet) https://github.com/a2aproject/a2a-dotnet/tags
    - [A2A Go SDK](https://github.com/a2aproject/a2a-go)
- 🔗 Agent2Agent (A2A) Samples https://github.com/a2aproject/a2a-samples


[Method Mapping Reference Table](https://a2a-protocol.org/latest/specification/#356-method-mapping-reference-table)

| JSON-RPC Method                       | gRPC Method                  | REST Endpoint                                              | Description                     |
| :------------------------------------ | :--------------------------- | :--------------------------------------------------------- | :------------------------------ |
| `message/send`                        | `SendMessage`                | `POST /v1/message:send`                                    | Send message to agent           |
| `message/stream`                      | `SendStreamingMessage`       | `POST /v1/message:stream`                                  | Send message with streaming     |
| `tasks/get`                           | `GetTask`                    | `GET /v1/tasks/{id}`                                       | Get task status                 |
| `tasks/list`                          | `ListTask`                   | `GET /v1/tasks`                                            | List tasks (gRPC/REST only)     |
| `tasks/cancel`                        | `CancelTask`                 | `POST /v1/tasks/{id}:cancel`                               | Cancel task                     |
| `tasks/resubscribe`                   | `TaskSubscription`           | `POST /v1/tasks/{id}:subscribe`                            | Resume task streaming           |
| `tasks/pushNotificationConfig/set`    | `CreateTaskPushNotification` | `POST /v1/tasks/{id}/pushNotificationConfigs`              | Set push notification config    |
| `tasks/pushNotificationConfig/get`    | `GetTaskPushNotification`    | `GET /v1/tasks/{id}/pushNotificationConfigs/{configId}`    | Get push notification config    |
| `tasks/pushNotificationConfig/list`   | `ListTaskPushNotification`   | `GET /v1/tasks/{id}/pushNotificationConfigs`               | List push notification configs  |
| `tasks/pushNotificationConfig/delete` | `DeleteTaskPushNotification` | `DELETE /v1/tasks/{id}/pushNotificationConfigs/{configId}` | Delete push notification config |
| `agent/getAuthenticatedExtendedCard`  | `GetAgentCard`               | `GET /v1/card`                                             | Get authenticated agent card    |