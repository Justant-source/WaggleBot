package com.wagglebot.llmworker;

public class InvokeRequest {
    public String prompt;
    public String model;
    public Boolean jsonMode;
    public Integer maxTokens;
    public Double temperature;
    public String callType;
    public String correlationId;
    public Long timeoutMs;
}
