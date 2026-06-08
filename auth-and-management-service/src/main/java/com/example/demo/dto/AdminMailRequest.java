package com.example.demo.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AdminMailRequest {
    @NotBlank(message = "Recipient email is required")
    private String to;

    private List<String> cc;

    private List<String> bcc;

    @NotBlank(message = "Subject is required")
    private String subject;

    @NotBlank(message = "Body content is required")
    private String body;

    private String signatureType;

    private String templateType;
}
