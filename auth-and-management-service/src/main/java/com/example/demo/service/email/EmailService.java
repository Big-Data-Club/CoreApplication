package com.example.demo.service.email;

import java.util.Map;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public interface EmailService {
    void sendWelcomeEmail(String to, String name, String tempPassword);

    void sendPasswordChangeConfirmation(String to, String name, String token);

    void sendPasswordChangedNotification(String to, String name);

    void sendForgotPasswordEmail(String to, String name, String token);

    CompletableFuture<Void> sendWelcomeEmailAsync(String to, String name, String tempPassword);

    CompletableFuture<Void> sendWelcomeBatch(Map<String, String> emailToPassword, Map<String, String> emailToName);

    CompletableFuture<Void> sendPasswordChangeConfirmationAsync(String to, String name, String token);

    CompletableFuture<Void> sendPasswordChangedNotificationAsync(String to, String name);

    CompletableFuture<Void> sendForgotPasswordEmailAsync(String to, String name, String token);

    CompletableFuture<Void> sendAdminMailAsync(String to, List<String> cc, List<String> bcc, String subject, String body, String signatureType, String templateType);
}