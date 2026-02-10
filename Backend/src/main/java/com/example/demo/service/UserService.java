package com.example.demo.service;

import com.example.demo.dto.auth.PasswordChangeRequest;
import com.example.demo.model.User;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

public interface UserService {
    List<User> getAllUsers();
    User getUserById(Long id);
    User getUserByEmail(String email);
    User updateUser(Long id, User user);
    
    void changePassword(Long userId, String currentPassword, String newPassword);
    
    void requestPasswordChange(PasswordChangeRequest request);
    void confirmPasswordChange(String token, String newPassword);
    
    String uploadProfilePicture(Long userId, MultipartFile file);
    void deleteUser(Long id);
}