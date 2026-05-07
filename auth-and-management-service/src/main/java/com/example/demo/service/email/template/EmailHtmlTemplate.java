package com.example.demo.service.email.template;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import com.example.demo.service.email.EmailTemplateProvider;

@Component
public class EmailHtmlTemplate implements EmailTemplateProvider{
    @Value("${spring.mail.username}")
    private String fromEmail;

    @Value("${app.name}")
    private String appName;

    @Value("${app.url}")
    private String appUrl;
    
    private static final DateTimeFormatter DT_FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm:ss");

    public String buildWelcomeHtml(String name, String email, String password) {
        return """
            <!DOCTYPE html><html><head><meta charset="UTF-8">
            <style>
              body{font-family:Arial,sans-serif;color:#333}
              .header{background:#4CAF50;color:#fff;padding:20px;text-align:center}
              .content{background:#f9f9f9;padding:30px}
              .cred{background:#fff;padding:15px;border-left:4px solid #4CAF50;margin:20px 0}
              .pwd{font-size:18px;font-weight:bold;color:#d32f2f;letter-spacing:2px;font-family:monospace}
              .btn{display:inline-block;padding:12px 30px;background:#4CAF50;color:#fff;text-decoration:none;border-radius:5px}
              .warn{background:#fff3cd;padding:10px;border-left:4px solid #ffc107;margin:15px 0}
            </style></head><body>
            <div class="header"><h1>Chào mừng đến với %s</h1></div>
            <div class="content">
              <p>Xin chào <strong>%s</strong>,</p>
              <p>Bạn đã được thêm vào hệ thống <strong>%s</strong>.</p>
              <div class="cred">
                <p><strong>Email:</strong> %s</p>
                <p><strong>Mật khẩu tạm thời:</strong></p>
                <p class="pwd">%s</p>
              </div>
              <div class="warn">
                ⚠️ Vui lòng đổi mật khẩu sau lần đăng nhập đầu tiên.
              </div>
              <div style="text-align:center;margin-top:20px">
                <a href="%s/login" class="btn">Đăng nhập ngay</a>
              </div>
            </div>
            </body></html>
            """.formatted(appName, name, appName, email, password, appUrl);
    }

    public String buildPasswordConfirmHtml(String name, String token) {
        String confirmUrl = appUrl + "/confirm-password-change?token=" + token;
        return """
            <!DOCTYPE html><html><head><meta charset="UTF-8">
            <style>
              body{font-family:Arial,sans-serif;color:#333}
              .header{background:#2196F3;color:#fff;padding:20px;text-align:center}
              .content{background:#f9f9f9;padding:30px}
              .btn{display:inline-block;padding:15px 40px;background:#2196F3;color:#fff;text-decoration:none;border-radius:5px;font-weight:bold}
              .warn{background:#ffebee;padding:15px;border-left:4px solid #f44336;margin:20px 0}
            </style></head><body>
            <div class="header"><h1>🔐 Xác nhận thay đổi mật khẩu</h1></div>
            <div class="content">
              <p>Xin chào <strong>%s</strong>,</p>
              <p>Click vào nút bên dưới để xác nhận đổi mật khẩu:</p>
              <div style="text-align:center;margin:20px 0">
                <a href="%s" class="btn">XÁC NHẬN ĐỔI MẬT KHẨU</a>
              </div>
              <div class="warn">
                ⚠️ Link có hiệu lực <strong>15 phút</strong> và chỉ dùng được 1 lần.
                Nếu bạn không yêu cầu, hãy bỏ qua email này.
              </div>
            </div>
            </body></html>
            """.formatted(name, confirmUrl);
    }

    public String buildPasswordChangedHtml(String name) {
        return """
            <!DOCTYPE html><html><head><meta charset="UTF-8">
            <style>
              body{font-family:Arial,sans-serif;color:#333}
              .header{background:#4CAF50;color:#fff;padding:20px;text-align:center}
              .content{background:#f9f9f9;padding:30px}
              .success{background:#e8f5e9;padding:15px;border-left:4px solid #4CAF50;margin:20px 0}
              .warn{background:#ffebee;padding:15px;border-left:4px solid #f44336;margin:20px 0}
            </style></head><body>
            <div class="header"><h1>✅ Mật khẩu đã được thay đổi</h1></div>
            <div class="content">
              <p>Xin chào <strong>%s</strong>,</p>
              <div class="success">
                <p>✓ Mật khẩu thay đổi thành công lúc <strong>%s</strong></p>
              </div>
              <div class="warn">
                Nếu bạn không thực hiện thao tác này, hãy liên hệ quản trị viên ngay.
              </div>
            </div>
            </body></html>
            """.formatted(name, LocalDateTime.now().format(DT_FORMAT));
    }

    public String buildForgotPasswordHtml(String name, String token) {
        String resetUrl = appUrl + "/confirm-password-change?token=" + token + "&type=reset";
        return """
            <!DOCTYPE html><html><head><meta charset="UTF-8">
            <style>
              body{font-family:Arial,sans-serif;color:#333}
              .header{background:#7C3AED;color:#fff;padding:20px;text-align:center}
              .content{background:#f9f9f9;padding:30px}
              .btn{display:inline-block;padding:15px 40px;background:#7C3AED;color:#fff;text-decoration:none;border-radius:5px;font-weight:bold}
              .warn{background:#ffebee;padding:15px;border-left:4px solid #f44336;margin:20px 0}
              .note{background:#f3f0ff;padding:12px;border-left:4px solid #7C3AED;margin:15px 0;font-size:13px}
            </style></head><body>
            <div class="header"><h1>🔑 Đặt lại mật khẩu</h1></div>
            <div class="content">
              <p>Xin chào <strong>%s</strong>,</p>
              <p>Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Click vào nút bên dưới để tiếp tục:</p>
              <div style="text-align:center;margin:25px 0">
                <a href="%s" class="btn">ĐẶT LẠI MẬT KHẨU</a>
              </div>
              <div class="note">
                💡 Link có hiệu lực <strong>15 phút</strong> và chỉ dùng được 1 lần.
              </div>
              <div class="warn">
                ⚠️ Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.
                Tài khoản của bạn vẫn an toàn.
              </div>
            </div>
            </body></html>
            """.formatted(name, resetUrl);
    }
}
