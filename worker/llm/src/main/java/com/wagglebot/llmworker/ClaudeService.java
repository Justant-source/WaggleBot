package com.wagglebot.llmworker;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class ClaudeService {

    private static final Logger log = LoggerFactory.getLogger(ClaudeService.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Value("${llm.claude-bin:claude}")
    private String claudeBin;

    @Value("${llm.default-model:claude-haiku-4-5-20251001}")
    private String defaultModel;

    @Value("${llm.pool-size:100}")
    private int poolSize;

    private final Semaphore semaphore;
    private final ExecutorService executor;

    public ClaudeService(
            @Value("${llm.pool-size:100}") int poolSize,
            @Value("${llm.queue-capacity:500}") int queueCapacity) {
        this.semaphore = new Semaphore(poolSize);
        this.executor = new ThreadPoolExecutor(
                poolSize, poolSize,
                60L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(queueCapacity),
                new ThreadPoolExecutor.CallerRunsPolicy());
    }

    public String invoke(String prompt, String model, Boolean jsonMode, long timeoutMs)
            throws Exception {
        String resolvedModel = (model != null && !model.isBlank()) ? model : defaultModel;

        Future<String> future = executor.submit(() -> runClaudeWithRetry(prompt, resolvedModel, jsonMode));
        try {
            return future.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw e;
        }
    }

    private String runClaude(String prompt, String model, Boolean jsonMode) throws IOException, InterruptedException {
        List<String> cmd = new ArrayList<>();
        cmd.add(claudeBin);
        cmd.add("--print");
        cmd.add("--model");
        cmd.add(model);
        if (Boolean.TRUE.equals(jsonMode)) {
            cmd.add("--output-format");
            cmd.add("json");
        }
        cmd.add(prompt);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        String homeDir = System.getenv("HOME");
        if (homeDir == null || homeDir.isEmpty()) {
            homeDir = "/home/justant";
        }
        pb.environment().put("HOME", homeDir);
        pb.redirectErrorStream(false);

        log.debug("claude cmd: {} model={}", claudeBin, model);
        Process process = pb.start();

        // Write prompt to stdin as alternative if needed
        process.getOutputStream().close();

        String output;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append("\n");
            }
            output = sb.toString().trim();
        }

        String stderr;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getErrorStream()))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append("\n");
            }
            stderr = sb.toString().trim();
        }

        int exitCode = process.waitFor();
        if (exitCode != 0) {
            log.error("claude exited {}: {}", exitCode, stderr);
            throw new IOException("claude exited " + exitCode + ": " + stderr);
        }

        if (Boolean.TRUE.equals(jsonMode)) {
            return unwrapCliJsonResult(output);
        }
        return output;
    }

    /**
     * Wrapper around runClaude with exponential backoff retry logic (3 attempts).
     * Detects authentication errors and fails immediately without retry.
     */
    private String runClaudeWithRetry(String prompt, String model, Boolean jsonMode)
            throws IOException, InterruptedException {
        final int MAX_RETRIES = 3;
        final long[] BACKOFF_DELAYS = {1000, 2000, 4000}; // milliseconds

        IOException lastException = null;

        for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                return runClaude(prompt, model, jsonMode);
            } catch (IOException e) {
                String stderr = extractStderrFromError(e.getMessage());
                if (isAuthenticationError(stderr)) {
                    log.error("Claude authentication error detected on attempt {}, failing immediately: {}",
                            attempt, stderr);
                    throw e;
                }

                lastException = e;
                if (attempt < MAX_RETRIES) {
                    long delay = BACKOFF_DELAYS[attempt - 1];
                    log.warn("Claude invocation failed on attempt {}/{}, retrying after {}ms: {}",
                            attempt, MAX_RETRIES, delay, e.getMessage());
                    Thread.sleep(delay);
                } else {
                    log.error("Claude invocation failed after all {} attempts", MAX_RETRIES);
                }
            }
        }

        if (lastException != null) {
            throw lastException;
        }

        throw new IOException("Unexpected retry loop termination");
    }

    /**
     * Detects common authentication/authorization error patterns in stderr.
     */
    private boolean isAuthenticationError(String stderr) {
        if (stderr == null || stderr.isEmpty()) {
            return false;
        }

        String lower = stderr.toLowerCase();
        return lower.contains("auth")
                || lower.contains("login")
                || lower.contains("oauth")
                || lower.contains("credential")
                || lower.contains("unauthorized")
                || lower.contains("permission denied")
                || lower.contains("invalid token")
                || lower.contains("access denied");
    }

    /**
     * Extracts stderr portion from error message (format: "claude exited N: <stderr>").
     */
    private String extractStderrFromError(String errorMessage) {
        if (errorMessage == null) {
            return "";
        }

        if (errorMessage.contains(": ")) {
            return errorMessage.split(": ", 2)[1];
        }

        return errorMessage;
    }

    /** Claude --output-format json returns a CLI envelope; surface the model text in result. */
    private static String unwrapCliJsonResult(String output) {
        try {
            JsonNode root = MAPPER.readTree(output);
            if (root != null && root.has("result") && root.get("result").isTextual()) {
                return root.get("result").asText();
            }
        } catch (Exception e) {
            log.debug("CLI JSON unwrap skipped: {}", e.toString());
        }
        return output;
    }
}
