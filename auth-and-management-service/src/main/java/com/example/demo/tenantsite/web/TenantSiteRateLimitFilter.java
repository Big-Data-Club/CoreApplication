package com.example.demo.tenantsite.web;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.util.*;

/** Bounded per-instance safety net. Edge limits should additionally cover all replicas. */
public class TenantSiteRateLimitFilter extends OncePerRequestFilter {
    private record Window(long minute, int count) {}
    private final Map<String, Window> windows = new HashMap<>();
    @Override protected boolean shouldNotFilter(HttpServletRequest req) {
        return !req.getRequestURI().startsWith("/api/tenant-sites/") &&
            !req.getRequestURI().matches("/api/admin/organizations/[0-9]+/site(/(publish|unpublish))?");
    }
    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain) throws ServletException, IOException {
        if (req.getContentLengthLong() > 270336) { res.sendError(413); return; }
        var auth = SecurityContextHolder.getContext().getAuthentication();
        boolean admin = req.getRequestURI().startsWith("/api/admin/");
        if (admin) res.setHeader("Cache-Control", "no-store");
        String key = (admin ? "write:" : "read:") + (auth != null && admin ? auth.getName() : req.getRemoteAddr());
        if (!allow(key, admin ? 60 : 180, System.currentTimeMillis() / 60000)) {
            res.setStatus(429); res.setHeader("Retry-After", "60"); res.setContentType("application/json");
            res.getWriter().write("{\"error\":\"Too many site requests\"}"); return;
        }
        chain.doFilter(req, res);
    }
    synchronized boolean allow(String key, int limit, long minute) {
        if (windows.size() >= 10000) windows.entrySet().removeIf(e -> e.getValue().minute() < minute);
        Window window = windows.get(key);
        if (window == null && windows.size() >= 10000) return false;
        if (window == null || window.minute() != minute) window = new Window(minute, 0);
        if (window.count() >= limit) return false;
        windows.put(key, new Window(minute, window.count() + 1)); return true;
    }
}
