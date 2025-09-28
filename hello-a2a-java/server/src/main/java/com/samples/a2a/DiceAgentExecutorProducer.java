package com.samples.a2a;

import io.a2a.server.agentexecution.AgentExecutor;
import io.a2a.server.agentexecution.RequestContext;
import io.a2a.server.events.EventQueue;
import io.a2a.server.tasks.TaskUpdater;
import io.a2a.spec.*;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;
import jakarta.inject.Inject;
import lombok.extern.slf4j.Slf4j;

import java.util.List;

/**
 * Producer for dice agent executor.
 */
@ApplicationScoped
@Slf4j
public final class DiceAgentExecutorProducer {

    /**
     * The dice agent instance.
     */
    @Inject
    private DiceAgent diceAgent;

    /**
     * Produces the agent executor for the dice agent.
     *
     * @return the configured agent executor
     */
    @Produces
    public AgentExecutor agentExecutor() {
        log.info("Producing DiceAgentExecutor");
        return new DiceAgentExecutor(diceAgent);
    }

    /**
     * Dice agent executor implementation.
     */
    @Slf4j
    private static class DiceAgentExecutor implements AgentExecutor {

        /**
         * The dice agent instance.
         */
        private final DiceAgent agent;

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
                log.info("Received new request. taskId={}", context.getTask() == null ? "<none>" : context.getTask().getId());

                // mark the task as submitted and start working on it
                if (context.getTask() == null) {
                    log.debug("No task in context; marking submitted");
                    updater.submit();
                    log.info("Task submitted");
                }
                updater.startWork();
                log.info("Task started working: {}", context.getTask() == null ? "<none>" : context.getTask().getId());

                // extract the text from the message
                final String assignment = extractTextFromMessage(context.getMessage());
                log.debug("Extracted message text: {}", assignment);

                // call the dice agent with the message
                log.info("Invoking agent.rollAndAnswer with assignment");
                final String response = agent.rollAndAnswer(assignment);
                log.info("Agent returned response length={} ", response == null ? 0 : response.length());
                log.debug("Agent response content: {}", response);

                // create the response part
                final TextPart responsePart = new TextPart(response, null);
                final List<Part<?>> parts = List.of(responsePart);

                // add the response as an artifact and complete the task
                log.info("Adding artifact to task and completing. partsCount={}", parts.size());
                updater.addArtifact(parts, null, null, null);
                log.debug("Artifact added");
                updater.complete();
                log.info("Task completed: {}", context.getTask() == null ? "<none>" : context.getTask().getId());
            } catch (JSONRPCError e) {
                log.error("JSONRPCError while executing task: {}", e.getMessage(), e);
                throw e;
            } catch (Exception e) {
                log.error("Unexpected error during agent execution: {}", e.getMessage(), e);
                // try to mark task as failed via updater if possible
                try {
                    updater.addArtifact(List.of(new TextPart("Internal server error: " + e.getMessage(), null)), null, null, null);
                    updater.complete();
                    log.info("Marked task complete after error");
                } catch (Exception inner) {
                    log.warn("Failed to update task after error: {}", inner.getMessage(), inner);
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

            log.info("Cancel requested for task: {}", task == null ? "<none>" : task.getId());

            if (task.getStatus().state() == TaskState.CANCELED) {
                // task already cancelled
                log.warn("Task already cancelled: {}", task.getId());
                throw new TaskNotCancelableError();
            }

            if (task.getStatus().state() == TaskState.COMPLETED) {
                // task already completed
                log.warn("Task already completed (cannot cancel): {}", task.getId());
                throw new TaskNotCancelableError();
            }

            // cancel the task
            final TaskUpdater updater = new TaskUpdater(context, eventQueue);
            updater.cancel();
            log.info("Task cancelled: {}", task.getId());
        }
    }
}
