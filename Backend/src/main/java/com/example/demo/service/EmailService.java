package com.example.demo.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

@Service
@RequiredArgsConstructor
@Slf4j
public class EmailService {
    
    private final JavaMailSender mailSender;
    
    @Value("${spring.mail.username}")
    private String fromEmail;
    
    @Value("${app.name}")
    private String appName;
    
    @Value("${app.url}")
    private String appUrl;

    public void sendWelcomeEmail(String toEmail, String userName, String temporaryPassword) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            
            helper.setFrom(fromEmail);
            helper.setTo(toEmail);
            helper.setSubject("Chào mừng đến với hệ thống " + appName);
            
            String htmlContent = buildWelcomeEmailContent(userName, toEmail, temporaryPassword);
            helper.setText(htmlContent, true);
            
            mailSender.send(message);
            log.info("Welcome email sent successfully to: {}", toEmail);
            
        } catch (MessagingException e) {
            log.error("Failed to send welcome email to: {}", toEmail, e);
            throw new RuntimeException("Failed to send welcome email", e);
        }
    }
    
    public void sendPasswordChangeConfirmation(String toEmail, String userName, String token) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            
            helper.setFrom(fromEmail);
            helper.setTo(toEmail);
            helper.setSubject("Xác nhận thay đổi mật khẩu - " + appName);
            
            String htmlContent = buildPasswordChangeConfirmationEmail(userName, token);
            helper.setText(htmlContent, true);
            
            mailSender.send(message);
            log.info("Password change confirmation email sent to: {}", toEmail);
            
        } catch (MessagingException e) {
            log.error("Failed to send password change confirmation to: {}", toEmail, e);
            throw new RuntimeException("Failed to send confirmation email", e);
        }
    }
    
    public void sendPasswordChangedNotification(String toEmail, String userName) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            
            helper.setFrom(fromEmail);
            helper.setTo(toEmail);
            helper.setSubject("Mật khẩu đã được thay đổi - " + appName);
            
            String htmlContent = buildPasswordChangedNotificationEmail(userName);
            helper.setText(htmlContent, true);
            
            mailSender.send(message);
            log.info("Password changed notification sent to: {}", toEmail);
            
        } catch (MessagingException e) {
            log.error("Failed to send password changed notification to: {}", toEmail, e);
        }
    }
    
    private String buildWelcomeEmailContent(String userName, String email, String password) {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
                    .content { background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }
                    .credentials { background-color: #fff; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0; }
                    .password { font-size: 18px; font-weight: bold; color: #d32f2f; letter-spacing: 2px; font-family: monospace; }
                    .button { display: inline-block; padding: 12px 30px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                    .footer { text-align: center; margin-top: 20px; font-size: 12px; color: #777; }
                    .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 15px 0; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Chào mừng đến với %s</h1>
                    </div>
                    <div class="content">
                        <p>Xin chào <strong>%s</strong>,</p>
                        
                        <p>Bạn đã được thêm vào hệ thống %s. Dưới đây là thông tin đăng nhập của bạn:</p>
                        
                        <div class="credentials">
                            <p><strong>Email:</strong> %s</p>
                            <p><strong>Mật khẩu tạm thời:</strong></p>
                            <p class="password">%s</p>
                        </div>
                        
                        <div class="warning">
                            <strong>⚠️ Lưu ý quan trọng:</strong>
                            <ul>
                                <li>Đây là mật khẩu tạm thời được tạo tự động</li>
                                <li>Vui lòng đổi mật khẩu ngay sau lần đăng nhập đầu tiên</li>
                                <li>Không chia sẻ mật khẩu này với bất kỳ ai</li>
                            </ul>
                        </div>
                        
                        <h3>Hướng dẫn đăng nhập:</h3>
                        <ol>
                            <li>Truy cập: <a href="%s/login">%s/login</a></li>
                            <li>Nhập email: <strong>%s</strong></li>
                            <li>Nhập mật khẩu tạm thời ở trên</li>
                            <li>Sau khi đăng nhập, vào phần "Đổi mật khẩu"</li>
                        </ol>
                        
                        <div style="text-align: center;">
                            <a href="%s/login" class="button">Đăng nhập ngay</a>
                        </div>
                        
                        <p style="margin-top: 30px;">Nếu có thắc mắc, vui lòng liên hệ quản trị viên.</p>
                        
                        <p>Trân trọng,<br><strong>%s Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>Email này được gửi tự động, vui lòng không trả lời.</p>
                        <p>&copy; 2024 %s. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """.formatted(
                appName, userName, appName, email, password,
                appUrl, appUrl, email, appUrl, appName, appName
            );
    }
    
    private String buildPasswordChangeConfirmationEmail(String userName, String token) {
        String confirmUrl = appUrl + "/confirm-password-change?token=" + token;
        
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background-color: #2196F3; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
                    .content { background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }
                    .button { display: inline-block; padding: 15px 40px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }
                    .warning { background-color: #ffebee; padding: 15px; border-left: 4px solid #f44336; margin: 20px 0; }
                    .info { background-color: #e3f2fd; padding: 15px; border-left: 4px solid #2196F3; margin: 20px 0; }
                    .footer { text-align: center; margin-top: 20px; font-size: 12px; color: #777; }
                    .token-box { background-color: #fff; padding: 15px; border: 2px dashed #2196F3; margin: 15px 0; text-align: center; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔐 Xác nhận thay đổi mật khẩu</h1>
                    </div>
                    <div class="content">
                        <p>Xin chào <strong>%s</strong>,</p>
                        
                        <p>Chúng tôi nhận được yêu cầu thay đổi mật khẩu cho tài khoản của bạn.</p>
                        
                        <div class="info">
                            <strong>ℹ️ Để bảo mật tài khoản:</strong>
                            <p>Vui lòng click vào nút bên dưới để xác nhận và hoàn tất việc thay đổi mật khẩu.</p>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="%s" class="button">XÁC NHẬN THAY ĐỔI MẬT KHẨU</a>
                        </div>
                        
                        <p style="margin-top: 20px;">Hoặc copy link và paste vào trình duyệt:</p>
                        <div class="token-box">
                            <code style="word-break: break-all; color: #2196F3; font-size: 12px;">%s</code>
                        </div>
                        
                        <div class="warning">
                            <strong>⚠️ Lưu ý bảo mật:</strong>
                            <ul>
                                <li>Link có hiệu lực trong <strong>15 phút</strong></li>
                                <li>Link chỉ sử dụng được <strong>1 lần duy nhất</strong></li>
                                <li>Nếu bạn không yêu cầu, vui lòng <strong>BỎ QUA</strong> email này</li>
                            </ul>
                        </div>
                        
                        <p>Trân trọng,<br><strong>%s Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>&copy; 2024 %s. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """.formatted(userName, confirmUrl, confirmUrl, appName, appName);
    }
    
    private String buildPasswordChangedNotificationEmail(String userName) {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
                    .content { background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }
                    .success { background-color: #e8f5e9; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0; }
                    .warning { background-color: #ffebee; padding: 15px; border-left: 4px solid #f44336; margin: 20px 0; }
                    .footer { text-align: center; margin-top: 20px; font-size: 12px; color: #777; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ Mật khẩu đã được thay đổi</h1>
                    </div>
                    <div class="content">
                        <p>Xin chào <strong>%s</strong>,</p>
                        
                        <div class="success">
                            <p><strong>✓ Mật khẩu của bạn đã được thay đổi thành công!</strong></p>
                            <p>Thời gian: <strong>%s</strong></p>
                        </div>
                        
                        <p>Từ giờ trở đi, vui lòng sử dụng mật khẩu mới để đăng nhập.</p>
                        
                        <div class="warning">
                            <strong>⚠️ Nếu bạn không thực hiện thay đổi này?</strong>
                            <p>Tài khoản của bạn có thể đã bị xâm nhập. Vui lòng liên hệ ngay với bộ phận hỗ trợ.</p>
                        </div>
                        
                        <p>Trân trọng,<br><strong>%s Team</strong></p>
                    </div>
                    <div class="footer">
                        <p>&copy; 2024 %s. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """.formatted(
                userName, 
                java.time.LocalDateTime.now().format(java.time.format.DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm:ss")),
                appName, 
                appName
            );
    }
}