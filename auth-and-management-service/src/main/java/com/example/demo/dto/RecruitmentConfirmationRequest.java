package com.example.demo.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Trusted server-to-server request to acknowledge a BDC recruitment submission.
 */
public record RecruitmentConfirmationRequest(
        @NotBlank @Email @Size(max = 254) String email,
        @NotBlank @Size(max = 120) String fullName,
        @Size(max = 160) String department
) {
}
