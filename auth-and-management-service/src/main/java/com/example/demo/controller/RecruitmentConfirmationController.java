package com.example.demo.controller;

import com.example.demo.dto.RecruitmentConfirmationRequest;
import com.example.demo.service.email.EmailService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

/**
 * Internal bridge used by the Next.js form handler after Google Sheets accepts
 * a recruitment application. It is deliberately protected by a shared secret:
 * this endpoint must never become a public email relay.
 */
@RestController
@RequestMapping("/api/internal/recruitment")
@RequiredArgsConstructor
@Slf4j
public class RecruitmentConfirmationController {

    private final EmailService emailService;

    @Value("${ai-service.api.secret}")
    private String internalServiceSecret;

    @PostMapping("/confirmation")
    public ResponseEntity<Map<String, String>> sendConfirmation(
            @RequestHeader(value = "X-Internal-Service-Secret", required = false) String providedSecret,
            @Valid @RequestBody RecruitmentConfirmationRequest request) {

        if (providedSecret == null || !MessageDigest.isEqual(
                internalServiceSecret.getBytes(StandardCharsets.UTF_8),
                providedSecret.getBytes(StandardCharsets.UTF_8))) {
            log.warn("Rejected recruitment confirmation request with an invalid internal secret");
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(Map.of("message", "Forbidden"));
        }

        emailService.sendRecruitmentConfirmationAsync(
                request.email(), request.fullName(), request.department());
        log.info("Queued recruitment confirmation email for {}", request.email());
        return ResponseEntity.accepted().body(Map.of("message", "Confirmation email queued"));
    }
}
