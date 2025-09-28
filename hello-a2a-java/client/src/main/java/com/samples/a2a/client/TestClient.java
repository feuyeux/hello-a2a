package com.samples.a2a.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.a2a.A2A;
import io.a2a.client.*;
import io.a2a.client.config.ClientConfig;
import io.a2a.client.http.A2ACardResolver;
import io.a2a.client.transport.grpc.GrpcTransport;
import io.a2a.client.transport.grpc.GrpcTransportConfig;
import io.a2a.client.transport.jsonrpc.JSONRPCTransport;
import io.a2a.client.transport.jsonrpc.JSONRPCTransportConfig;
import io.a2a.spec.*;
import io.grpc.Channel;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import lombok.extern.slf4j.Slf4j;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import java.util.function.Function;

/**
 * Creates an A2A client that sends a test message to the A2A server agent.
 */
@Slf4j
public final class TestClient {

    /**
     * The default server URL to use.
     */
    private static final String DEFAULT_SERVER_URL = "http://localhost:11000";

    /**
     * The default message text to send.
     */
    private static final String MESSAGE_TEXT = "Can you roll a 5 sided die?";

    /**
     * Object mapper to use.
     */
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private TestClient() {
        // this avoids a lint issue
    }

    /**
     * Client entry point.
     *
     * @param args can optionally contain the --server-url and --message to use
     */
    public static void main(final String[] args) {
        String serverUrl = DEFAULT_SERVER_URL;
        String messageText = MESSAGE_TEXT;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--server-url":
                    if (i + 1 < args.length) {
                        serverUrl = args[i + 1];
                        i++;
                    } else {
                        log.error("Error: --server-url requires a value");
                        printUsageAndExit();
                    }
                    break;
                case "--message":
                    if (i + 1 < args.length) {
                        messageText = args[i + 1];
                        i++;
                    } else {
                        log.error("Error: --message requires a value");
                        printUsageAndExit();
                    }
                    break;
                case "--help":
                case "-h":
                    printUsageAndExit();
                    break;
                default:
                    log.error("Error: Unknown argument: {}", args[i]);
                    printUsageAndExit();
            }
        }
        try {
            run(serverUrl, messageText);
        } catch (Exception e) {
            log.error("An error occurred: {}", e.getMessage(), e);
        }
    }

    /**
     * Client entry point.
     *
     * @param serverUrl   The server URL to connect to.
     * @param messageText The message to send.
     * @throws Exception if an error occurs.
     */
    public static void run(final String serverUrl, final String messageText) throws Exception {
        log.info("Connecting to dice agent at: {}", serverUrl);

        // Fetch the public agent card
        AgentCard publicAgentCard = new A2ACardResolver(serverUrl).getAgentCard();
        log.info("Successfully fetched public agent card:");
        log.info(OBJECT_MAPPER.writeValueAsString(publicAgentCard));
        log.info("Using public agent card for client initialization.");

        // Create a CompletableFuture to handle async response
        final CompletableFuture<String> messageResponse = new CompletableFuture<>();

        // Keep track of managed channels for cleanup
        final List<ManagedChannel> managedChannels = new ArrayList<>();

        // Create the client
        Client client = initClient(publicAgentCard, messageResponse, managedChannels);

        try {
            // Create and send the message
            Message message = A2A.toUserMessage(messageText);

            log.info("Sending message: {}", messageText);
            client.sendMessage(message);
            log.info("Message sent successfully. Waiting for response...");

            try {
                // Wait for response with timeout
                String responseText = messageResponse.get();
                log.info("Final response: {}", responseText);
            } catch (InterruptedException e) {
                log.error("Interrupted while waiting for response: {}", e.getMessage(), e);
                Thread.currentThread().interrupt();
            } catch (ExecutionException e) {
                log.error("Failed to get response: {}", e.getCause().getMessage(), e.getCause());
            }
        } finally {
            // Clean up resources
            cleanupResources(client, managedChannels);
        }
    }

    private static Client initClient(
            final AgentCard publicAgentCard,
            final CompletableFuture<String> messageResponse,
            final List<ManagedChannel> managedChannels) throws A2AClientException {
        // Create consumers for handling client events
        List<BiConsumer<ClientEvent, AgentCard>> consumers = getConsumers(messageResponse);

        // Create error handler for streaming errors
        Consumer<Throwable> streamingErrorHandler =
                (error) -> {
                    log.error("Streaming error occurred: {}", error.getMessage(), error);
                    messageResponse.completeExceptionally(error);
                };

        // Create channel factory for gRPC transport that tracks channels for cleanup
        Function<String, Channel> channelFactory =
                agentUrl -> {
                    ManagedChannel channel = ManagedChannelBuilder.forTarget(agentUrl).usePlaintext().build();
                    managedChannels.add(channel);
                    return channel;
                };

        ClientConfig clientConfig = new ClientConfig.Builder().setAcceptedOutputModes(List.of("Text")).build();

        // Create the client with both JSON-RPC and gRPC transport support.
        // The A2A server agent's preferred transport is gRPC, since the client
        // also supports gRPC, this is the transport that will get used
        return Client.builder(publicAgentCard)
                .addConsumers(consumers)
                .streamingErrorHandler(streamingErrorHandler)
                .withTransport(GrpcTransport.class, new GrpcTransportConfig(channelFactory))
                .withTransport(JSONRPCTransport.class, new JSONRPCTransportConfig())
                .clientConfig(clientConfig)
                .build();
    }

    private static List<BiConsumer<ClientEvent, AgentCard>> getConsumers(
            final CompletableFuture<String> messageResponse) {
        List<BiConsumer<ClientEvent, AgentCard>> consumers = new ArrayList<>();
        consumers.add(
                (event, agentCard) -> {
                    if (event instanceof MessageEvent messageEvent) {
                        Message responseMessage = messageEvent.getMessage();
                        String text = extractTextFromParts(responseMessage.getParts());
                        log.info("Received message: {}", text);
                        messageResponse.complete(text);
                    } else if (event instanceof TaskUpdateEvent taskUpdateEvent) {
                        UpdateEvent updateEvent = taskUpdateEvent.getUpdateEvent();
                        if (updateEvent
                                instanceof TaskStatusUpdateEvent taskStatusUpdateEvent) {
                            log.info(
                                    "Received status-update: {}",
                                    taskStatusUpdateEvent.getStatus().state().asString());
                            if (taskStatusUpdateEvent.isFinal()) {
                                StringBuilder textBuilder = new StringBuilder();
                                List<Artifact> artifacts
                                        = taskUpdateEvent.getTask().getArtifacts();
                                for (Artifact artifact : artifacts) {
                                    textBuilder.append(extractTextFromParts(artifact.parts()));
                                }
                                String text = textBuilder.toString();
                                messageResponse.complete(text);
                            }
                        } else if (updateEvent instanceof TaskArtifactUpdateEvent
                                taskArtifactUpdateEvent) {
                            List<Part<?>> parts = taskArtifactUpdateEvent
                                    .getArtifact()
                                    .parts();
                            String text = extractTextFromParts(parts);
                            log.info("Received artifact-update: {}", text);
                        }
                    } else if (event instanceof TaskEvent taskEvent) {
                        log.info("Received task event: {}", taskEvent.getTask().getId());
                    }
                });
        return consumers;
    }

    private static String extractTextFromParts(final List<Part<?>> parts) {
        final StringBuilder textBuilder = new StringBuilder();
        if (parts != null) {
            for (final Part<?> part : parts) {
                if (part instanceof TextPart textPart) {
                    textBuilder.append(textPart.getText());
                }
            }
        }
        return textBuilder.toString();
    }

    /**
     * Clean up client and gRPC resources to prevent thread lingering warnings.
     *
     * @param client          The A2A client to close
     * @param managedChannels List of gRPC channels to shut down
     */
    private static void cleanupResources(final Client client, final List<ManagedChannel> managedChannels) {
        log.info("Cleaning up resources...");

        // Close the client if it implements AutoCloseable
        try {
            if (client instanceof AutoCloseable) {
                ((AutoCloseable) client).close();
            }
        } catch (Exception e) {
            log.warn("Error closing client: {}", e.getMessage(), e);
        }

        // Shutdown all managed channels
        for (ManagedChannel channel : managedChannels) {
            try {
                channel.shutdown();
                if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                    log.warn("Channel did not terminate gracefully, forcing shutdown");
                    channel.shutdownNow();
                    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                        log.warn("Channel did not terminate after forced shutdown");
                    }
                }
            } catch (InterruptedException e) {
                log.warn("Interrupted while shutting down channel: {}", e.getMessage(), e);
                channel.shutdownNow();
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                log.warn("Error shutting down channel: {}", e.getMessage(), e);
            }
        }

        log.info("Resource cleanup completed");
    }

    private static void printUsageAndExit() {
        log.info("Usage: TestClient [OPTIONS]");
        log.info("");
        log.info("Options:");
        log.info("  --server-url URL    "
                + "The URL of the A2A server agent (default: "
                + DEFAULT_SERVER_URL + ")");
        log.info("  --message TEXT      "
                + "The message to send to the agent "
                + "(default: \"" + MESSAGE_TEXT + "\")");
        log.info("  --help, -h          "
                + "Show this help message and exit");
        log.info("");
        log.info("Examples:");
        log.info("  TestClient --server-url http://localhost:11001");
        log.info("  TestClient --message "
                + "\"Can you roll a 12-sided die?\"");
        log.info("  TestClient --server-url http://localhost:11001 "
                + "--message \"Is 17 prime?\"");
        System.exit(0);
    }
}
