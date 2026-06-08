package com.example.demo.service.email.impl;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

import com.example.demo.exception.ExternalServiceException;
import com.example.demo.service.email.EmailSender;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

import java.util.List;

@Component
@RequiredArgsConstructor
@Slf4j
public class JavaMailSenderImpl implements EmailSender {
    private final JavaMailSender mailSender;
    @Value("${spring.mail.username}") private String fromEmail;

    @Override
    public void send(String to, String subject, String content) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom(fromEmail);
            helper.setTo(to);
            helper.setSubject(subject);
            helper.setText(content, true);
            mailSender.send(message);
        } catch (MessagingException e) {
            log.error("SMTP Error: {}", e.getMessage());
            throw new ExternalServiceException("SMTP", e.getMessage(), e);
        }
    }

    @Override
    public void sendHtmlWithCcBcc(String to, List<String> cc, List<String> bcc, String subject, String content, boolean inlineLogo) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom(fromEmail);
            helper.setTo(to);
            if (cc != null && !cc.isEmpty()) {
                helper.setCc(cc.toArray(new String[0]));
            }
            if (bcc != null && !bcc.isEmpty()) {
                helper.setBcc(bcc.toArray(new String[0]));
            }
            helper.setSubject(subject);
            helper.setText(content, true);

            if (inlineLogo) {
                helper.addInline("bdc-logo", new ClassPathResource("bdclogo.png"));
            }

            mailSender.send(message);
        } catch (MessagingException e) {
            log.error("SMTP Error in sendHtmlWithCcBcc: {}", e.getMessage());
            throw new ExternalServiceException("SMTP", e.getMessage(), e);
        }
    }
}