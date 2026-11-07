package com.example.demo.tenantsite.controller;

import com.example.demo.tenantsite.service.TenantSiteService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import java.util.concurrent.TimeUnit;

@RestController @RequiredArgsConstructor @RequestMapping("/api/tenant-sites")
public class TenantSitePublicController {
    private final TenantSiteService service;
    @GetMapping("/{slug}") public ResponseEntity<TenantSiteService.Published> get(@PathVariable String slug) {
        return ResponseEntity.ok().cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS).cachePublic()).body(service.published(slug));
    }
}
