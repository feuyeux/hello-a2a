package com.samples.a2a;

import io.a2a.server.PublicAgentCard;
import io.a2a.spec.*;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Produces;
import jakarta.inject.Inject;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.util.List;

/**
 * Producer for dice agent card configuration.
 */
@ApplicationScoped
@Slf4j
public final class DiceAgentCardProducer {

    /**
     * The HTTP port for the agent service.
     */
    @Inject
    @ConfigProperty(name = "quarkus.http.port")
    private int httpPort;

    /**
     * Produces the agent card for the dice agent.
     *
     * @return the configured agent card
     */
    @Produces
    @PublicAgentCard
    public AgentCard agentCard() {
        final String name = "Dice Agent";
        final String description = "Rolls an N-sided dice and answers questions about the "
                + "outcome of the dice rolls. Can also answer questions "
                + "about prime numbers.";
        final String preferredTransport = TransportProtocol.GRPC.asString();
        final String url = "localhost:" + httpPort;

        final List<AgentSkill> skills = List.of(
                new AgentSkill.Builder()
                        .id("dice_roller")
                        .name("Roll dice")
                        .description("Rolls dice and discusses outcomes")
                        .tags(List.of("dice", "games", "random"))
                        .examples(
                                List.of("Can you roll a 6-sided die?"))
                        .build(),
                new AgentSkill.Builder()
                        .id("prime_checker")
                        .name("Check prime numbers")
                        .description("Checks if given numbers are prime")
                        .tags(List.of("math", "prime", "numbers"))
                        .examples(
                                List.of(
                                        "Is 17 a prime number?",
                                        "Which of these numbers are prime: 1, 4, 6, 7"))
                        .build());

        AgentCard card = new AgentCard.Builder()
                .name(name)
                .description(description)
                .preferredTransport(preferredTransport)
                .url(url)
                .version("1.0.0")
                .documentationUrl("http://example.com/docs")
                .capabilities(
                        new AgentCapabilities.Builder()
                                .streaming(true)
                                .pushNotifications(false)
                                .stateTransitionHistory(false)
                                .build())
                .defaultInputModes(List.of("text"))
                .defaultOutputModes(List.of("text"))
                .skills(skills)
                .protocolVersion("0.3.0")
                .additionalInterfaces(
                        List.of(
                                new AgentInterface(TransportProtocol.GRPC.asString(), url),
                                new AgentInterface(TransportProtocol.JSONRPC.asString(), "http://" + url)))
                .build();

        // Log key agent card fields for observability
        log.info("Produced public agent card: name='{}', url='{}', preferredTransport='{}', skills={}",
                name, url, preferredTransport, skills.stream().map(AgentSkill::id).toList());

        return card;
    }
}
