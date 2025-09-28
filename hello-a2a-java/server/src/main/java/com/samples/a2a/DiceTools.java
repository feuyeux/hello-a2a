package com.samples.a2a;

import dev.langchain4j.agent.tool.Tool;
import jakarta.enterprise.context.ApplicationScoped;
import lombok.extern.slf4j.Slf4j;

import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

/**
 * Service class that provides dice rolling and prime number functionality.
 */
@ApplicationScoped
@Slf4j
public class DiceTools {

    /**
     * Default number of sides to use.
     */
    private static final int DEFAULT_NUM_SIDES = 6;
    /**
     * For generating rolls.
     */
    private final Random random = new Random();

    /**
     * Rolls an N sided dice. If number of sides aren't given, uses 6.
     *
     * @param n the number of the side of the dice to roll
     * @return A number between 1 and N, inclusive
     */
    @Tool("Rolls an n sided dice. If number of sides aren't given, uses 6.")
    public int rollDice(final int n) {
        log.debug("rollDice called with n={}", n);
        int sides = n;
        if (sides <= 0) {
            log.warn("Invalid number of sides ({}). Falling back to default {}.", sides, DEFAULT_NUM_SIDES);
            sides = DEFAULT_NUM_SIDES; // Default to 6 sides if invalid input
        }
        int result = random.nextInt(sides) + 1;
        log.info("rollDice result: sides={}, result={}", sides, result);
        return result;
    }

    /**
     * Check if a given list of numbers are prime.
     *
     * @param nums The list of numbers to check
     * @return A string indicating which number is prime
     */
    @Tool("Check if a given list of numbers are prime.")
    public String checkPrime(final List<Integer> nums) {
        log.debug("checkPrime called with nums={}", nums);
        Set<Integer> primes = new HashSet<>();

        if (nums == null || nums.isEmpty()) {
            log.info("checkPrime received empty or null list");
        }

        for (Integer number : nums) {
            if (number == null) {
                log.debug("Skipping null entry in nums");
                continue;
            }

            int num = number.intValue();
            if (num <= 1) {
                log.debug("Skipping non-positive or 1: {}", num);
                continue;
            }

            boolean isPrime = true;
            for (int i = 2; i <= Math.sqrt(num); i++) {
                if (num % i == 0) {
                    isPrime = false;
                    break;
                }
            }

            if (isPrime) {
                primes.add(num);
                log.debug("Found prime: {}", num);
            } else {
                log.debug("Not prime: {}", num);
            }
        }

        final String result;
        if (primes.isEmpty()) {
            result = "No prime numbers found.";
            log.info("checkPrime result: {}", result);
        } else {
            result = primes.stream()
                    .sorted()
                    .map(String::valueOf)
                    .collect(java.util.stream.Collectors.joining(", "))
                    + " are prime numbers.";
            log.info("checkPrime result: primes={}, output={}", primes, result);
        }

        return result;
    }
}
