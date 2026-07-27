package com.example.demo.controller;

import com.example.demo.dto.PublicUserProfileResponse;
import com.example.demo.dto.UserProfileConfigRequest;
import com.example.demo.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

@RestController
// Requests to this service pass through the /apiv1 gateway, which strips that
// prefix before forwarding.  Keep the versioned mapping as a direct-service
// compatibility alias, but expose the path the gateway actually forwards.
@RequestMapping({"/myaccount/profile-config", "/api/v1/myaccount/profile-config"})
@RequiredArgsConstructor
public class MyAccountProfileController {

    private final UserProfileService userProfileService;

    @GetMapping
    public ResponseEntity<PublicUserProfileResponse> getProfileConfig() {
        String email = (String) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        return ResponseEntity.ok(userProfileService.getProfileConfig(email));
    }

    @PutMapping
    public ResponseEntity<PublicUserProfileResponse> updateProfileConfig(@RequestBody UserProfileConfigRequest request) {
        String email = (String) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        return ResponseEntity.ok(userProfileService.updateProfileConfig(email, request));
    }
}
