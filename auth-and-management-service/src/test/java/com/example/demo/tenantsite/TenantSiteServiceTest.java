package com.example.demo.tenantsite;

import com.example.demo.model.Organization;
import com.example.demo.repository.OrganizationRepository;
import com.example.demo.tenantsite.model.TenantSite;
import com.example.demo.tenantsite.repository.TenantSiteRepository;
import com.example.demo.tenantsite.service.*;
import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.Optional;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class TenantSiteServiceTest {
    final ObjectMapper mapper = new ObjectMapper();
    final OrganizationRepository orgs = mock(OrganizationRepository.class);
    final TenantSiteRepository sites = mock(TenantSiteRepository.class);
    final SiteDocumentValidator validator = new SiteDocumentValidator();
    final TenantSiteService service = new TenantSiteService(orgs, sites, mapper, validator);
    static final String DOCUMENT = """
      {"schemaVersion":1,"template":"classic","primaryColor":"#075985","tagline":"Test","footerText":"Footer",
       "contact":{"hotline":"","email":"","address":"","hours":"","zaloUrl":"","mapUrl":""},
       "slides":[],"slideInterval":5,"autoplay":false,"menu":[],"sections":[],"pages":[]}
      """;
    @Test void publicSnapshotNeverLeaksDraftAndConflictDoesNotWrite() throws Exception {
        var org = Organization.builder().id(9L).slug("cce").isActive(true).build();
        var site = new TenantSite(); site.setOrgId(9L); site.setRevision(1); site.setDraft(DOCUMENT);
        when(orgs.lockForSiteUpdate(9L)).thenReturn(Optional.of(org));
        when(orgs.findBySlug("cce")).thenReturn(Optional.of(org));
        when(sites.findById(9L)).thenReturn(Optional.of(site));
        when(sites.save(any())).thenAnswer(invocation -> invocation.getArgument(0));
        assertEquals(404, assertThrows(ResponseStatusException.class, () -> service.published("cce")).getStatusCode().value());
        service.publish(9L, 1, true);
        var draft = mapper.readTree(DOCUMENT); ((com.fasterxml.jackson.databind.node.ObjectNode) draft).put("tagline", "Private draft");
        service.save(9L, 2, draft);
        assertEquals("Test", service.published("cce").document().path("tagline").asText());
        assertEquals(409, assertThrows(ResponseStatusException.class, () -> service.save(9L, 1, draft)).getStatusCode().value());
        service.publish(9L, 3, false);
        assertThrows(ResponseStatusException.class, () -> service.published("cce"));
        org.setActive(false);
        assertThrows(ResponseStatusException.class, () -> service.published("cce"));
    }
    @Test void validatesLinksSizeAndStructure() throws Exception {
        var doc = (com.fasterxml.jackson.databind.node.ObjectNode) mapper.readTree(DOCUMENT);
        assertDoesNotThrow(() -> validator.validate(doc));
        ((com.fasterxml.jackson.databind.node.ObjectNode) doc.path("contact")).put("zaloUrl", "javascript:alert(1)");
        assertEquals(400, assertThrows(ResponseStatusException.class, () -> validator.validate(doc)).getStatusCode().value());
        ((com.fasterxml.jackson.databind.node.ObjectNode) doc.path("contact")).put("zaloUrl", "relative");
        assertThrows(ResponseStatusException.class, () -> validator.validate(doc));
        ((com.fasterxml.jackson.databind.node.ObjectNode) doc.path("contact")).put("zaloUrl", "");
        doc.put("tagline", "a".repeat(300000));
        assertThrows(ResponseStatusException.class, () -> validator.validate(doc));
    }
}
