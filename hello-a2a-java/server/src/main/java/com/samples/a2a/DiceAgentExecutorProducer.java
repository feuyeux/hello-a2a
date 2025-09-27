package com.samples.a2a;

import io.a2a.server.agentexecution.AgentExecutor;
import io.a2a.server.agentexecution.RequestContext;
import io.a2a.server.events.EventQueue;
import io.a2a.server.tasks.TaskUpdater;
import io.a2a.spec.JSONRPCError;
import io.a2a.spec.Message;
import io.a2a.spec.Part;
import io.a2a.spec.Task;
import io.a2a.spec.TaskNotCancelableError;
import io.a2a.spec.TaskState;
import io.a2a.spec.TextPart;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;
import jakarta.inject.Inject;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Producer for dice agent executor. */
@ApplicationScoped
public final class DiceAgentExecutorProducer {

  /** The dice agent instance. */
  @Inject private DiceAgent diceAgent;

  /** SLF4J logger for executor. */
  private static final Logger LOGGER = LoggerFactory.getLogger(DiceAgentExecutorProducer.class);

  /**
   * Produces the agent executor for the dice agent.
   *
   * @return the configured agent executor
   */
  @Produces
  public AgentExecutor agentExecutor() {
    LOGGER.info("Producing DiceAgentExecutor");
    return new DiceAgentExecutor(diceAgent);
  }

  /** Dice agent executor implementation. */
  private static class DiceAgentExecutor implements AgentExecutor {

    /** The dice agent instance. */
    private final DiceAgent agent;

    /** Logger for the inner executor class. */
    private static final Logger EXEC_LOG = LoggerFactory.getLogger(DiceAgentExecutor.class);

    /**
     * Constructor for DiceAgentExecutor.
     *
     * @param diceAgentInstance the dice agent instance
     */
    DiceAgentExecutor(final DiceAgent diceAgentInstance) {
      this.agent = diceAgentInstance;
    }

    @Override
    public void execute(final RequestContext context,
                        final EventQueue eventQueue)
        throws JSONRPCError {
      final TaskUpdater updater = new TaskUpdater(context, eventQueue);

      try {
        EXEC_LOG.info("Received new request. taskId={}", context.getTask() == null ? "<none>" : context.getTask().getId());

        // mark the task as submitted and start working on it
        if (context.getTask() == null) {
          EXEC_LOG.debug("No task in context; marking submitted");
          updater.submit();
          EXEC_LOG.info("Task submitted");
        }
        updater.startWork();
        EXEC_LOG.info("Task started working: {}", context.getTask() == null ? "<none>" : context.getTask().getId());

        // extract the text from the message
        final String assignment = extractTextFromMessage(context.getMessage());
        EXEC_LOG.debug("Extracted message text: {}", assignment);

        // call the dice agent with the message
        EXEC_LOG.info("Invoking agent.rollAndAnswer with assignment");
        final String response = agent.rollAndAnswer(assignment);
        EXEC_LOG.info("Agent returned response length={} ", response == null ? 0 : response.length());
        EXEC_LOG.debug("Agent response content: {}", response);

        // create the response part
        final TextPart responsePart = new TextPart(response, null);
        final List<Part<?>> parts = List.of(responsePart);

        // add the response as an artifact and complete the task
        EXEC_LOG.info("Adding artifact to task and completing. partsCount={}", parts.size());
        updater.addArtifact(parts, null, null, null);
        EXEC_LOG.debug("Artifact added");
        updater.complete();
        EXEC_LOG.info("Task completed: {}", context.getTask() == null ? "<none>" : context.getTask().getId());
      } catch (JSONRPCError e) {
        EXEC_LOG.error("JSONRPCError while executing task: {}", e.getMessage(), e);
        throw e;
      } catch (Exception e) {
        EXEC_LOG.error("Unexpected error during agent execution: {}", e.getMessage(), e);
        // try to mark task as failed via updater if possible
        try {
          updater.addArtifact(List.of(new TextPart("Internal server error: " + e.getMessage(), null)), null, null, null);
          updater.complete();
          EXEC_LOG.info("Marked task complete after error");
        } catch (Exception inner) {
          EXEC_LOG.warn("Failed to update task after error: {}", inner.getMessage(), inner);
        }
        // JSONRPCError requires (code, message, data) — use a generic server error code 0 and no data
        throw new JSONRPCError(0, e.getMessage(), null);
      }
    }

    private String extractTextFromMessage(final Message message) {
      final StringBuilder textBuilder = new StringBuilder();
      if (message.getParts() != null) {
        for (final Part<?> part : message.getParts()) {
          if (part instanceof TextPart textPart) {
            textBuilder.append(textPart.getText());
          }
        }
      }
      return textBuilder.toString();
    }

    @Override
    public void cancel(final RequestContext context,
                       final EventQueue eventQueue)
        throws JSONRPCError {
      final Task task = context.getTask();

      EXEC_LOG.info("Cancel requested for task: {}", task == null ? "<none>" : task.getId());

      if (task.getStatus().state() == TaskState.CANCELED) {
        // task already cancelled
        EXEC_LOG.warn("Task already cancelled: {}", task.getId());
        throw new TaskNotCancelableError();
      }

      if (task.getStatus().state() == TaskState.COMPLETED) {
        // task already completed
        EXEC_LOG.warn("Task already completed (cannot cancel): {}", task.getId());
        throw new TaskNotCancelableError();
      }

      // cancel the task
      final TaskUpdater updater = new TaskUpdater(context, eventQueue);
      updater.cancel();
      EXEC_LOG.info("Task cancelled: {}", task.getId());
    }
  }
}
