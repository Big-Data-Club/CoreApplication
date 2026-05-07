package com.example.demo.controller;

import com.example.demo.dto.auth.*;
import com.example.demo.model.User;
import com.example.demo.service.auth.AuthService;
import com.example.demo.service.user.UserService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
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

    @Value("${jwt.expirationMs:3600000}")
    private long expirationMs;

    @Value("${jwt.refreshExpirationMs:604800000}")
    private long refreshExpirationMs;

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody LoginRequest req) {
        User user  = authService.authenticate(req);
        String at  = authService.generateToken(user);
        String rt  = authService.generateRefreshToken(user);

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookieOf("authToken",    at, expirationMs / 1000))
                .header(HttpHeaders.SET_COOKIE, cookieOf("refreshToken", rt, refreshExpirationMs / 1000))
                .body(Map.of(
                    "userId",    user.getId(),
                    "name",      user.getName(),
                    "email",     user.getEmail(),
                    "role",      user.getRole().name(),
                    "token",     at,
                    "expiresIn", expirationMs
                ));
    }

    @PostMapping("/refresh")
    public ResponseEntity<?> refresh(
            @RequestBody(required = false) Map<String, String> body,
            @CookieValue(name = "refreshToken", required = false) String cookieRt) {

        String rt = cookieRt != null ? cookieRt : (body != null ? body.get("refreshToken") : null);

        if (rt == null || !authService.validateToken(rt)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("message", "Invalid or missing refresh token"));
        }

        User user   = userService.getUserByEmail(authService.extractEmail(rt));
        String newAt = authService.generateToken(user);
        String newRt = authService.generateRefreshToken(user);

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookieOf("authToken",    newAt, expirationMs / 1000))
                .header(HttpHeaders.SET_COOKIE, cookieOf("refreshToken", newRt, refreshExpirationMs / 1000))
                .body(Map.of("expiresIn", expirationMs));
    }

    @PostMapping("/logout")
    public ResponseEntity<?> logout() {
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookieOf("authToken",    "", 0))
                .header(HttpHeaders.SET_COOKIE, cookieOf("refreshToken", "", 0))
                .body(Map.of("message", "Logged out successfully"));
    }

    @PostMapping("/register/bulk")
    @PreAuthorize("hasAuthority('ROLE_ADMIN')")
    public ResponseEntity<List<User>> bulkRegister(@RequestBody BulkRegisterRequest req) {
        return ResponseEntity.ok(authService.bulkRegister(req));
    }

    @PostMapping("/request-password-change")
    public ResponseEntity<MessageResponse> requestPasswordChange(
            @Valid @RequestBody PasswordChangeRequest req) {
        userService.requestPasswordChange(req);
        return ResponseEntity.ok(new MessageResponse(
            "Email xác nhận đã được gửi. Vui lòng kiểm tra hộp thư."));
    }

    @PostMapping("/confirm-password-change")
    public ResponseEntity<MessageResponse> confirmPasswordChange(
            @Valid @RequestBody ConfirmPasswordChangeRequest req) {
        userService.confirmPasswordChange(req.getToken(), req.getNewPassword());
        return ResponseEntity.ok(new MessageResponse(
            "Đổi mật khẩu thành công! Vui lòng đăng nhập lại."));
    }

    @PostMapping("/forgot-password")
    public ResponseEntity<MessageResponse> forgotPassword(
            @Valid @RequestBody ForgotPasswordRequest req) {
        // Always return 200 — never reveal whether the email exists
        userService.forgotPassword(req.getEmail());
        return ResponseEntity.ok(new MessageResponse(
            "Nếu email tồn tại trong hệ thống, bạn sẽ nhận được link đặt lại mật khẩu trong vài phút."));
    }

    @PostMapping("/reset-password")
    public ResponseEntity<MessageResponse> resetPassword(
            @Valid @RequestBody ResetPasswordRequest req) {
        userService.resetPassword(req.getToken(), req.getNewPassword());
        return ResponseEntity.ok(new MessageResponse(
            "Đặt lại mật khẩu thành công! Vui lòng đăng nhập lại."));
    }

    private String cookieOf(String name, String value, long maxAge) {
        return ResponseCookie.from(name, value)
                .httpOnly(true)
                .secure(true)
                .path("/")
                .maxAge(maxAge)
                .sameSite("Strict")
                .build()
                .toString();
    }
}