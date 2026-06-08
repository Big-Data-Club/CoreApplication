package com.example.demo.service.email.impl;

import com.example.demo.service.email.EmailSender;
import com.example.demo.service.email.EmailService;
import com.example.demo.service.email.EmailTemplateProvider;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.List;
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

    @Async("virtualThreadExecutor")
    @Override
    public CompletableFuture<Void> sendAdminMailAsync(String to, List<String> cc, List<String> bcc, String subject, String body, String signatureType, String templateType) {
        return CompletableFuture.runAsync(() -> {
            String content = body;
            boolean inlineLogo = false;

            // 1. Determine signature HTML
            String signatureHtml = "";
            if ("bdc-1".equalsIgnoreCase(signatureType)) {
                inlineLogo = true;
                signatureHtml = """
                    <table border="0" cellpadding="0" cellspacing="0" style="margin-top: 30px; border-top: 1px solid #1e293b; padding-top: 20px; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; width: 100%;">
                      <tr>
                        <td style="vertical-align: top; padding-right: 16px; width: 60px;">
                          <img src="cid:bdc-logo" alt="BDC Logo" width="55" height="55" style="display: block; border-radius: 8px; border: 1px solid #3b82f6;" />
                        </td>
                        <td style="vertical-align: top; line-height: 1.5;">
                          <div style="font-size: 15px; font-weight: 700; color: #3b82f6; letter-spacing: 0.5px;">Big Data Club</div>
                          <div style="font-size: 12px; font-weight: 600; color: #64748b; margin-top: 2px;">Trường Đại học Bách Khoa</div>
                          <div style="font-size: 11px; color: #94a3b8;">Đại học Quốc gia Thành phố Hồ Chí Minh</div>
                          <div style="margin-top: 8px; font-size: 12px;">
                            <a href="https://www.facebook.com/BDCofHCMUT" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: 600;">Facebook</a>
                            <span style="color: #cbd5e1; margin: 0 8px;">|</span>
                            <a href="https://bdc.hpcc.vn" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: 600;">Website</a>
                          </div>
                        </td>
                      </tr>
                    </table>
                    """;
            }

            // 2. Wrap body in cosmic template if requested
            if ("cosmic".equalsIgnoreCase(templateType)) {
                content = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                      <meta charset="UTF-8">
                      <meta name="viewport" content="width=device-width, initial-scale=1.0">
                      <title>%s</title>
                      <style>
                        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
                        body {
                          font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        }
                      </style>
                    </head>
                    <body style="margin: 0; padding: 0; background-color: #030712; color: #f8fafc; -webkit-text-size-adjust: none; -ms-text-size-adjust: none;">
                      <div style="background-color: #030712; padding: 40px 10px; min-height: 100%%;">
                        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%%" style="max-width: 600px; background-color: #0f172a; border-radius: 24px; overflow: hidden; border: 1px solid #1e293b; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4); margin: 0 auto;">
                          <!-- Top cosmic gradient bar -->
                          <tr>
                            <td style="background: linear-gradient(90deg, #3b82f6, #8b5cf6, #ec4899); height: 6px; line-height: 6px; font-size: 0px; padding: 0;">&nbsp;</td>
                          </tr>
                          
                          <!-- Header -->
                          <tr>
                            <td style="padding: 40px 40px 20px 40px; text-align: center;">
                              <table border="0" cellpadding="0" cellspacing="0" align="center">
                                <tr>
                                  <td align="center" style="background: linear-gradient(135deg, #1e3a8a, #311042); border-radius: 16px; padding: 12px 24px; border: 1px solid #3b82f6; box-shadow: 0 0 20px rgba(59, 130, 246, 0.2);">
                                    <span style="font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 24px; color: #38bdf8; letter-spacing: 2px;">BDC HUB</span>
                                  </td>
                                </tr>
                              </table>
                              <h1 style="font-family: 'Outfit', sans-serif; font-size: 24px; font-weight: 700; color: #f8fafc; margin: 24px 0 0 0; letter-spacing: -0.5px;">%s</h1>
                            </td>
                          </tr>
                          
                          <!-- Main Content -->
                          <tr>
                            <td style="padding: 20px 40px 40px 40px; font-size: 16px; line-height: 1.8; color: #cbd5e1;">
                              <div style="margin-bottom: 24px;">
                                %s
                              </div>
                              
                              <!-- Signature area -->
                              %s
                            </td>
                          </tr>
                          
                          <!-- Footer -->
                          <tr>
                            <td style="background-color: #0b0f19; padding: 32px 40px; border-top: 1px solid #1e293b; text-align: center;">
                              <p style="font-size: 14px; color: #94a3b8; margin: 0 0 8px 0; font-weight: 600; letter-spacing: 0.5px;">Big Data Club (BDC) App</p>
                              <p style="font-size: 12px; color: #64748b; line-height: 1.5; margin: 0;">
                                Đây là email được gửi từ Ban Quản Trị hệ thống BDC Hub.<br>
                                &copy; 2026 Big Data Club. All rights reserved.
                              </p>
                            </td>
                          </tr>
                        </table>
                      </div>
                    </body>
                    </html>
                    """.formatted(subject, subject, body, signatureHtml);
            } else {
                content = body + (signatureHtml.isEmpty() ? "" : "<br>" + signatureHtml);
            }

            emailSender.sendHtmlWithCcBcc(to, cc, bcc, subject, content, inlineLogo);
        });
    }
}