package com.example.demo.tenantsite.dto;

import com.fasterxml.jackson.databind.JsonNode;

public final class SiteRequests {
    private SiteRequests() {}
    public record Save(long revision, JsonNode document) {}
    public record Revision(long revision) {}
}
