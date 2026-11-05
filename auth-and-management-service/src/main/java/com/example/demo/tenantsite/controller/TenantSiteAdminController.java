package com.example.demo.tenantsite.controller;

import com.example.demo.tenantsite.dto.SiteRequests;
import com.example.demo.tenantsite.service.TenantSiteService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController @RequiredArgsConstructor
@RequestMapping("/api/admin/organizations/{id}/site")
@PreAuthorize("hasRole('ADMIN')")
public class TenantSiteAdminController {
    private final TenantSiteService service;
    @GetMapping public TenantSiteService.Editor get(@PathVariable Long id) { return service.editor(id); }
    @PutMapping public TenantSiteService.Editor save(@PathVariable Long id, @RequestBody SiteRequests.Save req) { return service.save(id, req.revision(), req.document()); }
    @PostMapping("/publish") public TenantSiteService.Editor publish(@PathVariable Long id, @RequestBody SiteRequests.Revision req) { return service.publish(id, req.revision(), true); }
    @PostMapping("/unpublish") public TenantSiteService.Editor unpublish(@PathVariable Long id, @RequestBody SiteRequests.Revision req) { return service.publish(id, req.revision(), false); }
}
