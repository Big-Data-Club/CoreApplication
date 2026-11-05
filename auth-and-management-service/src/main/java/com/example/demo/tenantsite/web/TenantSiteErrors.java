package com.example.demo.tenantsite.web;

import com.example.demo.tenantsite.controller.TenantSiteAdminController;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.*;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.Map;

@RestControllerAdvice(basePackageClasses = TenantSiteAdminController.class) @Order(Ordered.HIGHEST_PRECEDENCE)
public class TenantSiteErrors {
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<?> status(ResponseStatusException ex) { return ResponseEntity.status(ex.getStatusCode()).body(Map.of("message", ex.getReason() == null ? "Request failed" : ex.getReason())); }
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<?> denied() { return ResponseEntity.status(403).body(Map.of("message", "Administrator access required")); }
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<?> malformed() { return ResponseEntity.badRequest().body(Map.of("message", "Invalid site document")); }
}
