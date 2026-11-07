package com.example.demo.tenantsite.service;

import com.example.demo.repository.OrganizationRepository;
import com.example.demo.tenantsite.model.TenantSite;
import com.example.demo.tenantsite.repository.TenantSiteRepository;
import com.fasterxml.jackson.databind.*;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.time.Instant;

@Service @RequiredArgsConstructor
public class TenantSiteService {
    private final OrganizationRepository organizations;
    private final TenantSiteRepository sites;
    private final ObjectMapper mapper;
    private final SiteDocumentValidator validator;
    public record Editor(long revision, JsonNode draft, Instant publishedAt) {}
    public record Published(long revision, JsonNode document) {}

    @Transactional(readOnly = true)
    public Editor editor(Long id) {
        if (!organizations.existsById(id)) missing();
        return sites.findById(id).map(this::editorResponse).orElse(new Editor(0, null, null));
    }
    @Transactional
    public Editor save(Long id, long revision, JsonNode document) {
        validator.validate(document);
        TenantSite site = locked(id, revision);
        site.setDraft(document.toString()); site.setRevision(site.getRevision() + 1);
        return editorResponse(sites.save(site));
    }
    @Transactional
    public Editor publish(Long id, long revision, boolean publish) {
        TenantSite site = locked(id, revision);
        if (site.getDraft() == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Save a draft first");
        if (publish) validator.validate(parse(site.getDraft()));
        site.setPublished(publish ? site.getDraft() : null);
        site.setPublishedAt(publish ? Instant.now() : null);
        site.setRevision(site.getRevision() + 1);
        return editorResponse(sites.save(site));
    }
    @Transactional(readOnly = true)
    public Published published(String slug) {
        var org = organizations.findBySlug(slug).filter(o -> o.isActive()).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        var site = sites.findById(org.getId()).filter(s -> s.getPublished() != null).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new Published(site.getRevision(), parse(site.getPublished()));
    }
    private TenantSite locked(Long id, long revision) {
        organizations.lockForSiteUpdate(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        TenantSite site = sites.findById(id).orElseGet(() -> { var s = new TenantSite(); s.setOrgId(id); return s; });
        if (revision != site.getRevision()) throw new ResponseStatusException(HttpStatus.CONFLICT, "Site changed. Reload before saving.");
        return site;
    }
    private Editor editorResponse(TenantSite site) { return new Editor(site.getRevision(), site.getDraft() == null ? null : parse(site.getDraft()), site.getPublishedAt()); }
    private JsonNode parse(String json) { try { return mapper.readTree(json); } catch (Exception e) { throw new IllegalStateException("Invalid stored site document", e); } }
    private void missing() { throw new ResponseStatusException(HttpStatus.NOT_FOUND); }
}
