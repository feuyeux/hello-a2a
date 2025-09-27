package com.samples.a2a.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.a2a.A2A;
import io.a2a.client.Client;
import io.a2a.client.ClientEvent;
import io.a2a.client.MessageEvent;
import io.a2a.client.TaskEvent;
import io.a2a.client.TaskUpdateEvent;
import io.a2a.client.config.ClientConfig;
import io.a2a.client.http.A2ACardResolver;
import io.a2a.client.transport.grpc.GrpcTransport;
import io.a2a.client.transport.grpc.GrpcTransportConfig;
import io.a2a.client.transport.jsonrpc.JSONRPCTransport;
import io.a2a.client.transport.jsonrpc.JSONRPCTransportConfig;
import io.a2a.spec.A2AClientException;
import io.a2a.spec.AgentCard;
import io.a2a.spec.Artifact;
import io.a2a.spec.Message;
import io.a2a.spec.Part;
import io.a2a.spec.TaskArtifactUpdateEvent;
import io.a2a.spec.TaskStatusUpdateEvent;
import io.a2a.spec.TextPart;
import io.a2a.spec.UpdateEvent;
import io.grpc.Channel;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.Consumer;
import java.util.function.Function;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Creates an A2A client that sends a test message to the A2A server agent. */
public final class TestClient {
  private static final Logger LOG = LoggerFactory.getLogger(TestClient.class);

  /** The default server URL to use. */
  private static final String DEFAULT_SERVER_URL = "http://localhost:11000";

  /** The default message text to send. */
  private static final String MESSAGE_TEXT = "Can you roll a 5 sided die?";

  /** Object mapper to use. */
  private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

  private TestClient() {
      // this avoids a lint issue
  }

    /**
     * Client entry point.
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
            LOG.error("Error: --server-url requires a value");
            printUsageAndExit();
          }
          break;
        case "--message":
          if (i + 1 < args.length) {
            messageText = args[i + 1];
            i++;
          } else {
            LOG.error("Error: --message requires a value");
            printUsageAndExit();
          }
          break;
        case "--help":
        case "-h":
          printUsageAndExit();
          break;
        default:
          LOG.error("Error: Unknown argument: {}", args[i]);
          printUsageAndExit();
      }
    }
    try {
      run(serverUrl, messageText);
    } catch (Exception e) {
      LOG.error("An error occurred: {}", e.getMessage(), e);
    }
  }

  /**
   * Client entry point.
   *
   * @param serverUrl The server URL to connect to.
   * @param messageText The message to send.
   * @throws Exception if an error occurs.
   */
  public static void run(final String serverUrl, final String messageText) throws Exception {
    LOG.info("Connecting to dice agent at: {}", serverUrl);

    // Fetch the public agent card
    AgentCard publicAgentCard = new A2ACardResolver(serverUrl).getAgentCard();
    LOG.info("Successfully fetched public agent card:");
    LOG.info(OBJECT_MAPPER.writeValueAsString(publicAgentCard));
    LOG.info("Using public agent card for client initialization.");

    // Create a CompletableFuture to handle async response
    final CompletableFuture<String> messageResponse = new CompletableFuture<>();
    
    // Keep track of managed channels for cleanup
    final List<ManagedChannel> managedChannels = new ArrayList<>();

    // Create the client
    Client client = initClient(publicAgentCard, messageResponse, managedChannels);

    try {
      // Create and send the message
      Message message = A2A.toUserMessage(messageText);

      LOG.info("Sending message: {}", messageText);
      client.sendMessage(message);
      LOG.info("Message sent successfully. Waiting for response...");

      try {
        // Wait for response with timeout
        String responseText = messageResponse.get();
        LOG.info("Final response: {}", responseText);
      } catch (InterruptedException e) {
        LOG.error("Interrupted while waiting for response: {}", e.getMessage(), e);
        Thread.currentThread().interrupt();
      } catch (ExecutionException e) {
        LOG.error("Failed to get response: {}", e.getCause().getMessage(), e.getCause());
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
          LOG.error("Streaming error occurred: {}", error.getMessage(), error);
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
            LOG.info("Received message: {}", text);
            messageResponse.complete(text);
          } else if (event instanceof TaskUpdateEvent taskUpdateEvent) {
            UpdateEvent updateEvent = taskUpdateEvent.getUpdateEvent();
            if (updateEvent
                    instanceof TaskStatusUpdateEvent taskStatusUpdateEvent) {
              LOG.info(
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
              LOG.info("Received artifact-update: {}", text);
            }
          } else if (event instanceof TaskEvent taskEvent) {
            LOG.info("Received task event: {}", taskEvent.getTask().getId());
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
   * @param client The A2A client to close
   * @param managedChannels List of gRPC channels to shut down
   */
  private static void cleanupResources(final Client client, final List<ManagedChannel> managedChannels) {
    LOG.info("Cleaning up resources...");
    
    // Close the client if it implements AutoCloseable
    try {
      if (client instanceof AutoCloseable) {
        ((AutoCloseable) client).close();
      }
    } catch (Exception e) {
      LOG.warn("Error closing client: {}", e.getMessage(), e);
    }
    
    // Shutdown all managed channels
    for (ManagedChannel channel : managedChannels) {
      try {
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
          LOG.warn("Channel did not terminate gracefully, forcing shutdown");
          channel.shutdownNow();
          if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            LOG.warn("Channel did not terminate after forced shutdown");
          }
        }
      } catch (InterruptedException e) {
        LOG.warn("Interrupted while shutting down channel: {}", e.getMessage(), e);
        channel.shutdownNow();
        Thread.currentThread().interrupt();
      } catch (Exception e) {
        LOG.warn("Error shutting down channel: {}", e.getMessage(), e);
      }
    }
    
    LOG.info("Resource cleanup completed");
  }

  private static void printUsageAndExit() {
    LOG.info("Usage: TestClient [OPTIONS]");
    LOG.info("");
    LOG.info("Options:");
    LOG.info("  --server-url URL    "
            + "The URL of the A2A server agent (default: "
            + DEFAULT_SERVER_URL + ")");
    LOG.info("  --message TEXT      "
            + "The message to send to the agent "
            + "(default: \"" + MESSAGE_TEXT + "\")");
    LOG.info("  --help, -h          "
            + "Show this help message and exit");
    LOG.info("");
    LOG.info("Examples:");
    LOG.info("  TestClient --server-url http://localhost:11001");
    LOG.info("  TestClient --message "
            + "\"Can you roll a 12-sided die?\"");
    LOG.info("  TestClient --server-url http://localhost:11001 "
            + "--message \"Is 17 prime?\"");
    System.exit(0);
  }
}
