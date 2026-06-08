package com.example.demo.controller;

import com.example.demo.dto.AdminMailRequest;
import com.example.demo.service.email.EmailService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/admin/mail")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
@Slf4j
public class AdminMailController {

    private final EmailService emailService;

    @PostMapping("/send")
    public ResponseEntity<Map<String, String>> sendMail(@Valid @RequestBody AdminMailRequest request) {
        log.info("Admin initiated email sending to: {}, CC: {}, BCC: {}, Subject: {}",
                request.getTo(), request.getCc(), request.getBcc(), request.getSubject());

        emailService.sendAdminMailAsync(
                request.getTo(),
                request.getCc(),
                request.getBcc(),
                request.getSubject(),
                request.getBody(),
                request.getSignatureType(),
                request.getTemplateType()
        );

        return ResponseEntity.ok(Map.of("message", "Email sending initiated successfully"));
    }
}
