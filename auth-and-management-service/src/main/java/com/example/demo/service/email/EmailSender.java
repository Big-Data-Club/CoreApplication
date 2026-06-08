package com.example.demo.service.email;

import java.util.List;

public interface EmailSender {
    void send(String to, String subject, String content);

    void sendHtmlWithCcBcc(String to, List<String> cc, List<String> bcc, String subject, String content, boolean inlineLogo);
}
