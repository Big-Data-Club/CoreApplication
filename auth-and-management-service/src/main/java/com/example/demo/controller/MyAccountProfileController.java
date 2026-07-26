package com.example.demo.controller;

import com.example.demo.dto.PublicUserProfileResponse;
import com.example.demo.dto.UserProfileConfigRequest;
import com.example.demo.service.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/myaccount/profile-config")
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
