package com.example.demo.service;

import com.example.demo.model.PasswordResetToken;
import com.example.demo.model.User;
import com.example.demo.repository.PasswordResetTokenRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class PasswordResetService {
    
    private final PasswordResetTokenRepository tokenRepository;
    private static final int EXPIRATION_MINUTES = 15;
    
    @Transactional
    public PasswordResetToken createToken(User user) {
        // Xóa các token cũ
        tokenRepository.deleteByUser(user);
        
        String tokenValue = UUID.randomUUID().toString();
        
        PasswordResetToken token = PasswordResetToken.builder()
                .token(tokenValue)
                .user(user)
                .expiryDate(LocalDateTime.now().plusMinutes(EXPIRATION_MINUTES))
                .createdAt(LocalDateTime.now())
                .used(false)
                .build();
        
        return tokenRepository.save(token);
    }
    
    @Transactional
    public PasswordResetToken validateAndGetToken(String tokenValue) {
        PasswordResetToken token = tokenRepository.findByToken(tokenValue)
                .orElseThrow(() -> new RuntimeException("Token không tồn tại"));
        
        if (token.isUsed()) {
            throw new RuntimeException("Token đã được sử dụng");
        }
        
        if (token.isExpired()) {
            throw new RuntimeException("Token đã hết hạn. Vui lòng yêu cầu đổi mật khẩu lại");
        }
        
        return token;
    }
    
    @Transactional
    public void markTokenAsUsed(PasswordResetToken token) {
        token.setUsed(true);
        tokenRepository.save(token);
    }
    
    @Scheduled(cron = "0 0 2 * * *")
    @Transactional
    public void cleanupExpiredTokens() {
        log.info("Cleaning up expired password reset tokens...");
        tokenRepository.deleteByExpiryDateBefore(LocalDateTime.now());
    }
}