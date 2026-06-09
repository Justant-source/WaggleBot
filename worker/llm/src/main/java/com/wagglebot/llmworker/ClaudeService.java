package com.wagglebot.llmworker;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

@Service
public class ClaudeService {

    private static final Logger log = LoggerFactory.getLogger(ClaudeService.class);

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

        Future<String> future = executor.submit(() -> runClaude(prompt, resolvedModel, jsonMode));
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
        pb.environment().put("HOME", "/root");
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

        return output;
    }
}
