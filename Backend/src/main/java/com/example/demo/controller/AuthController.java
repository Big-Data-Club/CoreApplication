package com.example.demo.controller;

import com.example.demo.dto.auth.BulkRegisterRequest;
import com.example.demo.dto.auth.ConfirmPasswordChangeRequest;
import com.example.demo.dto.auth.LoginRequest;
import com.example.demo.dto.auth.MessageResponse;
import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.model.User;
import com.example.demo.service.AuthService;
import com.example.demo.service.UserService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {
    private final AuthService authService;
    private final UserService userService;

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody LoginRequest request) {
        User user = authService.authenticate(request);

        String token = authService.generateToken(user);

        ResponseCookie cookie = ResponseCookie.from("token", token)
                .httpOnly(true)
                .secure(false) // false if testing on HTTP
                .path("/")
                .maxAge(24 * 60 * 60) // 1 day
                .sameSite("Strict")
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(Map.of(
                        "token", token,
                        "userId", user.getId(),
                        "name", user.getName(),
                        "email", user.getEmail(),
                        "role", user.getRole().name()
                ));
    }

    @PostMapping("/register/bulk")
    @PreAuthorize("hasAuthority('ROLE_ADMIN')")
    public ResponseEntity<List<User>> bulkRegister(@RequestBody BulkRegisterRequest request) {
        return ResponseEntity.ok(authService.bulkRegister(request));
    }

    @PostMapping("/logout")
    public ResponseEntity<?> logout() {
        ResponseCookie cookie = ResponseCookie.from("token", "")
                .httpOnly(true)
                .secure(true)
                .path("/")
                .maxAge(0)
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(Map.of("message", "Logged out successfully"));
    }

    @PostMapping("/request-password-change")
    public ResponseEntity<MessageResponse> requestPasswordChange(
            @Valid @RequestBody PasswordChangeRequest request) {
        
        userService.requestPasswordChange(request);
        
        return ResponseEntity.ok(new MessageResponse(
            "Email xác nhận đã được gửi. Vui lòng kiểm tra hộp thư để hoàn tất việc đổi mật khẩu."
        ));
    }

    @PostMapping("/confirm-password-change")
    public ResponseEntity<MessageResponse> confirmPasswordChange(
            @Valid @RequestBody ConfirmPasswordChangeRequest request) {
        
        userService.confirmPasswordChange(request.getToken(), request.getNewPassword());
        
        return ResponseEntity.ok(new MessageResponse(
            "Đổi mật khẩu thành công! Vui lòng đăng nhập lại với mật khẩu mới."
        ));
    }
}
