package com.example.demo.service.email;

public interface EmailTemplateProvider {
    String buildWelcomeHtml(String name, String email, String password);
    String buildPasswordConfirmHtml(String name, String token);
    String buildPasswordChangedHtml(String name);
    String buildForgotPasswordHtml(String name, String token);
}