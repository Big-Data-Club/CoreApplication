package com.example.demo.tenantsite.service;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Bounded, structured content only: no executable HTML, CSS or scripts. */
@Component
public class SiteDocumentValidator {
    private static final Set<String> BLOCKS = Set.of("hero", "text", "cards", "image", "cta", "contact");
    public void validate(JsonNode doc) {
        require(doc != null && doc.isObject() && doc.path("schemaVersion").asInt() == 1, "Unsupported site schema");
        require(doc.toString().getBytes(StandardCharsets.UTF_8).length <= 262144, "Site exceeds 256 KB");
        require(doc.path("primaryColor").asText().matches("#[0-9a-fA-F]{6}"), "Invalid primary color");
        require(Set.of("classic", "modern").contains(doc.path("template").asText()), "Invalid template");
        text(doc, "tagline", 200); text(doc, "footerText", 1000);
        require(doc.path("autoplay").isBoolean(), "Invalid autoplay");
        JsonNode contact = doc.path("contact"); require(contact.isObject(), "Contact is required");
        for (String key : List.of("hotline", "email", "address", "hours")) text(contact, key, 2000);
        url(contact.path("zaloUrl").asText(), false); url(contact.path("mapUrl").asText(), false);
        for (JsonNode slide : array(doc, "slides", 12)) {
            require(slide.path("enabled").isBoolean(), "Invalid slide visibility");
            url(slide.path("image").asText(), true); url(slide.path("href").asText(), false);
            text(slide, "title", 200); text(slide, "alt", 300);
        }
        require(doc.path("slideInterval").asInt() >= 3 && doc.path("slideInterval").asInt() <= 30, "Slider interval must be 3–30 seconds");
        Set<String> pages = new HashSet<>();
        for (JsonNode page : array(doc, "pages", 30)) {
            String slug = page.path("slug").asText();
            require(slug.matches("[a-z0-9][a-z0-9-]{0,79}") && pages.add(slug), "Invalid or duplicate page slug");
            text(page, "title", 200); blocks(page.path("sections"));
        }
        menu(doc.path("menu"), 0, pages);
        blocks(doc.path("sections"));
    }
    private void blocks(JsonNode nodes) {
        require(nodes.isArray() && nodes.size() <= 30, "Maximum 30 sections per page");
        Set<String> ids = new HashSet<>();
        for (JsonNode block : nodes) {
            require(block.path("enabled").isBoolean(), "Invalid section visibility");
            require(ids.add(block.path("id").asText()) && block.path("id").asText().matches("[a-zA-Z0-9_-]{1,80}"), "Invalid section ID");
            require(BLOCKS.contains(block.path("type").asText()), "Unknown section type");
            require(Set.of("left", "center").contains(block.path("align").asText()), "Invalid alignment");
            require(Set.of("plain", "muted", "brand").contains(block.path("tone").asText()), "Invalid section tone");
            text(block, "title", 300); text(block, "body", 15000); text(block, "buttonLabel", 100);
            url(block.path("image").asText(), true); url(block.path("buttonHref").asText(), false);
            for (JsonNode card : array(block, "items", 12)) {
                text(card, "title", 200); text(card, "body", 3000);
                url(card.path("image").asText(), true); url(card.path("href").asText(), false);
            }
        }
    }
    private void menu(JsonNode nodes, int depth, Set<String> pages) {
        require(nodes.isArray() && nodes.size() <= 12 && depth <= 1, "Menu supports 12 items and two levels");
        for (JsonNode node : nodes) {
            require(node.path("children").isArray(), "Menu children must be an array");
            text(node, "label", 100); url(node.path("href").asText(), false);
            String href = node.path("href").asText();
            if (href.startsWith("/thong-tin/")) require(pages.contains(href.substring(11)), "Menu links to a missing page");
            if (node.has("children") && !node.path("children").isEmpty()) menu(node.path("children"), depth + 1, pages);
        }
    }
    private JsonNode array(JsonNode node, String key, int max) {
        JsonNode values = node.path(key); require(values.isArray() && values.size() <= max, "Invalid " + key); return values;
    }
    private void text(JsonNode node, String key, int max) {
        require(node.path(key).isTextual() && node.path(key).asText().length() <= max, "Invalid " + key);
    }
    private void url(String value, boolean image) {
        if (value.isEmpty()) return;
        require(value.length() <= 2000, "URL too long");
        require(!value.matches(".*[\\\\\\p{Cntrl}\\s].*") && !value.startsWith("//"), "Invalid URL");
        if (value.startsWith("/")) return;
        if (!image && value.startsWith("#")) return;
        try {
            URI uri = URI.create(value);
            require(uri.getScheme() != null && Set.of("https", "http").contains(uri.getScheme()) && uri.getHost() != null && uri.getUserInfo() == null, "Only HTTP(S) URLs allowed");
        } catch (IllegalArgumentException ex) { throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid URL"); }
    }
    private void require(boolean valid, String message) { if (!valid) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message); }
}
