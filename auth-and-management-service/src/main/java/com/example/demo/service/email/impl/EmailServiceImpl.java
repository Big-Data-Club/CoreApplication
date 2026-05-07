package com.example.demo.service.email.impl;

import com.example.demo.service.email.EmailSender;
import com.example.demo.service.email.EmailService;
import com.example.demo.service.email.EmailTemplateProvider;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;

@Service
@RequiredArgsConstructor
@Slf4j
public class EmailServiceImpl implements EmailService {
    private final EmailSender emailSender;
    private final EmailTemplateProvider emailTemplateProvider;

    @Value("${app.name}")
    private String appName;

    public void sendWelcomeEmail(String to, String name, String tempPassword) {
        emailSender.send(to, "Chào mừng đến với hệ thống " + appName,
             emailTemplateProvider.buildWelcomeHtml(name, to, tempPassword));
    }

    public void sendPasswordChangeConfirmation(String to, String name, String token) {
        emailSender.send(to, "Xác nhận thay đổi mật khẩu - " + appName,
             emailTemplateProvider.buildPasswordConfirmHtml(name, token));
    }

    public void sendPasswordChangedNotification(String to, String name) {
        emailSender.send(to, "Mật khẩu đã được thay đổi - " + appName,
             emailTemplateProvider.buildPasswordChangedHtml(name));
    }

    public void sendForgotPasswordEmail(String to, String name, String token) {
        emailSender.send(to, "Đặt lại mật khẩu - " + appName,
             emailTemplateProvider.buildForgotPasswordHtml(name, token));
    }

    @Async("emailExecutor")
    public CompletableFuture<Void> sendWelcomeEmailAsync(String to, String name, String tempPassword) {
        return CompletableFuture.runAsync(() -> sendWelcomeEmail(to, name, tempPassword));
    }

    @Async("emailExecutor")
    public CompletableFuture<Void> sendWelcomeBatch(Map<String, String> emailToPassword,
                                                     Map<String, String> emailToName) {
        try (var vtExecutor = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = emailToPassword.entrySet().stream()
                    .map(entry -> CompletableFuture.runAsync(
                            () -> sendWelcomeEmail(entry.getKey(),
                                    emailToName.getOrDefault(entry.getKey(), ""),
                                    entry.getValue()),
                            vtExecutor
                    ).exceptionally(ex -> {
                        log.error("Failed email to {}: {}", entry.getKey(), ex.getMessage());
                        return null;
                    }))
                    .toArray(CompletableFuture[]::new);
            return CompletableFuture.allOf(futures);
        }
    }

    @Async("emailExecutor")
    public CompletableFuture<Void> sendPasswordChangeConfirmationAsync(String to, String name, String token) {
        return CompletableFuture.runAsync(() -> sendPasswordChangeConfirmation(to, name, token));
    }

    @Async("emailExecutor")
    public CompletableFuture<Void> sendPasswordChangedNotificationAsync(String to, String name) {
        return CompletableFuture.runAsync(() -> sendPasswordChangedNotification(to, name));
    }

    @Async("emailExecutor")
    public CompletableFuture<Void> sendForgotPasswordEmailAsync(String to, String name, String token) {
        return CompletableFuture.runAsync(() -> sendForgotPasswordEmail(to, name, token));
    }
}