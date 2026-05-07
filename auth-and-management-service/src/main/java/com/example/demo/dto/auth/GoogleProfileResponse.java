package com.example.demo.dto.auth;

import lombok.Builder;
import lombok.Data;

/**
 * Returned when a Google user does not yet have an account.
 * Frontend uses this to pre-fill the registration form.
 */
@Data
@Builder
public class GoogleProfileResponse {
    private String googleId;
    private String email;
    private String name;
    private String picture;
}
