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
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Chào mừng</title>
            </head>
            <body style="margin:0;padding:0;background-color:#f8fafc;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;">
              <div style="background-color:#f8fafc;padding:40px 10px;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 12px rgba(0,0,0,0.03);margin:0 auto;">
                  <tr><td style="background:linear-gradient(90deg, #4f46e5, #7c3aed, #3b82f6);height:6px;line-height:6px;font-size:0px;padding:0;">&nbsp;</td></tr>
                  <tr>
                    <td align="center" style="padding:40px 32px 10px 32px;">
                      <table border="0" cellpadding="0" cellspacing="0">
                        <tr>
                          <td align="center" style="background-color:#e0e7ff;border-radius:12px;padding:12px 20px;font-weight:800;font-size:24px;color:#4f46e5;letter-spacing:1px;">
                            BDC
                          </td>
                        </tr>
                      </table>
                      <h1 style="font-size:22px;font-weight:700;color:#0f172a;margin:20px 0 0 0;letter-spacing:-0.5px;">Chào mừng đến với %s</h1>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:20px 32px 30px 32px;">
                      <p style="font-size:16px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <strong style="color:#0f172a;">%s</strong>,</p>
                      <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 24px 0;">Tài khoản của bạn đã được thiết lập thành công trên hệ thống <strong style="color:#0f172a;">%s</strong>. Dưới đây là thông tin đăng nhập của bạn:</p>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;margin:0 0 24px 0;">
                        <tr>
                          <td style="padding:20px 24px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                              <tr>
                                <td style="padding:0 0 12px 0;font-size:14px;color:#64748b;"><strong>Email đăng nhập:</strong></td>
                                <td style="padding:0 0 12px 0;font-size:15px;color:#0f172a;text-align:right;font-weight:600;">%s</td>
                              </tr>
                              <tr>
                                <td style="padding:8px 0 0 0;font-size:14px;color:#64748b;vertical-align:middle;"><strong>Mật khẩu tạm thời:</strong></td>
                                <td style="padding:8px 0 0 0;text-align:right;">
                                  <span style="font-family:'Courier New',Courier,monospace;font-size:18px;font-weight:bold;color:#4f46e5;background-color:#e0e7ff;padding:4px 10px;border-radius:6px;letter-spacing:1px;display:inline-block;">%s</span>
                                </td>
                              </tr>
                            </table>
                          </td>
                        </tr>
                      </table>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#fffbeb;border-left:4px solid #f59e0b;border-radius:4px 8px 8px 4px;margin:0 0 30px 0;">
                        <tr>
                          <td style="padding:14px 18px;font-size:14px;line-height:1.5;color:#b45309;">
                            <strong>⚠️ Bảo mật tài khoản:</strong> Vui lòng đăng nhập và thực hiện thay đổi mật khẩu ngay trong lần truy cập đầu tiên để bảo vệ thông tin của bạn.
                          </td>
                        </tr>
                      </table>
                      
                      <table border="0" cellspacing="0" cellpadding="0" align="center" style="margin:20px auto 10px auto;">
                        <tr>
                          <td align="center" style="border-radius:12px;background:linear-gradient(135deg, #4f46e5, #7c3aed);box-shadow:0 4px 10px rgba(79, 70, 229, 0.25);">
                            <a href="%s/login" target="_blank" style="font-size:16px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;padding:14px 36px;border:1px solid transparent;display:inline-block;letter-spacing:0.5px;">Đăng nhập ngay</a>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="background-color:#f8fafc;padding:32px;border-top:1px solid #e2e8f0;text-align:center;">
                      <p style="font-size:14px;color:#475569;margin:0 0 8px 0;font-weight:600;">Big Data Club (BDC) App</p>
                      <p style="font-size:12px;color:#64748b;line-height:1.5;margin:0;">Đây là email tự động từ hệ thống. Vui lòng không phản hồi trực tiếp email này.<br>&copy; 2026 Big Data Club. All rights reserved.</p>
                    </td>
                  </tr>
                </table>
              </div>
            </body>
            </html>
            """.formatted(appName, name, appName, email, password, appUrl);
    }

    public String buildPasswordConfirmHtml(String name, String token) {
        String confirmUrl = appUrl + "/confirm-password-change?token=" + token;
        return """
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Xác nhận</title>
            </head>
            <body style="margin:0;padding:0;background-color:#f8fafc;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;">
              <div style="background-color:#f8fafc;padding:40px 10px;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 12px rgba(0,0,0,0.03);margin:0 auto;">
                  <tr><td style="background:linear-gradient(90deg, #2563eb, #3b82f6, #60a5fa);height:6px;line-height:6px;font-size:0px;padding:0;">&nbsp;</td></tr>
                  <tr>
                    <td align="center" style="padding:40px 32px 10px 32px;">
                      <table border="0" cellpadding="0" cellspacing="0">
                        <tr>
                          <td align="center" style="background-color:#eff6ff;border-radius:12px;padding:12px 20px;font-weight:800;font-size:24px;color:#2563eb;letter-spacing:1px;">
                            🔑
                          </td>
                        </tr>
                      </table>
                      <h1 style="font-size:22px;font-weight:700;color:#0f172a;margin:20px 0 0 0;letter-spacing:-0.5px;">Xác nhận đổi mật khẩu</h1>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:20px 32px 30px 32px;">
                      <p style="font-size:16px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <strong style="color:#0f172a;">%s</strong>,</p>
                      <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 24px 0;">Chúng tôi đã nhận được yêu cầu thay đổi mật khẩu của bạn. Vui lòng click vào nút xác nhận bên dưới để hoàn tất:</p>
                      
                      <table border="0" cellspacing="0" cellpadding="0" align="center" style="margin:30px auto;">
                        <tr>
                          <td align="center" style="border-radius:12px;background:linear-gradient(135deg, #2563eb, #3b82f6);box-shadow:0 4px 10px rgba(37, 99, 235, 0.25);">
                            <a href="%s" target="_blank" style="font-size:16px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;padding:14px 36px;border:1px solid transparent;display:inline-block;letter-spacing:0.5px;">Xác nhận đổi mật khẩu</a>
                          </td>
                        </tr>
                      </table>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#fff1f2;border-left:4px solid #f43f5e;border-radius:4px 8px 8px 4px;margin:20px 0 0 0;">
                        <tr>
                          <td style="padding:14px 18px;font-size:14px;line-height:1.5;color:#be123c;">
                            <strong>⚠️ Quan trọng:</strong> Liên kết này chỉ có hiệu lực trong vòng <strong>15 phút</strong> và chỉ sử dụng được 1 lần duy nhất. Nếu bạn không yêu cầu thay đổi mật khẩu, vui lòng bỏ qua email này an toàn.
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="background-color:#f8fafc;padding:32px;border-top:1px solid #e2e8f0;text-align:center;">
                      <p style="font-size:14px;color:#475569;margin:0 0 8px 0;font-weight:600;">Big Data Club (BDC) App</p>
                      <p style="font-size:12px;color:#64748b;line-height:1.5;margin:0;">Đây là email tự động từ hệ thống. Vui lòng không phản hồi trực tiếp email này.<br>&copy; 2026 Big Data Club. All rights reserved.</p>
                    </td>
                  </tr>
                </table>
              </div>
            </body>
            </html>
            """.formatted(name, confirmUrl);
    }

    public String buildPasswordChangedHtml(String name) {
        return """
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Mật khẩu đã đổi</title>
            </head>
            <body style="margin:0;padding:0;background-color:#f8fafc;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;">
              <div style="background-color:#f8fafc;padding:40px 10px;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 12px rgba(0,0,0,0.03);margin:0 auto;">
                  <tr><td style="background:linear-gradient(90deg, #10b981, #34d399, #059669);height:6px;line-height:6px;font-size:0px;padding:0;">&nbsp;</td></tr>
                  <tr>
                    <td align="center" style="padding:40px 32px 10px 32px;">
                      <table border="0" cellpadding="0" cellspacing="0">
                        <tr>
                          <td align="center" style="background-color:#d1fae5;border-radius:12px;padding:12px 20px;font-weight:800;font-size:24px;color:#059669;letter-spacing:1px;">
                            ✅
                          </td>
                        </tr>
                      </table>
                      <h1 style="font-size:22px;font-weight:700;color:#0f172a;margin:20px 0 0 0;letter-spacing:-0.5px;">Mật khẩu đã được thay đổi</h1>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:20px 32px 30px 32px;">
                      <p style="font-size:16px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <strong style="color:#0f172a;">%s</strong>,</p>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f0fdf4;border-left:4px solid #10b981;border-radius:4px 8px 8px 4px;margin:20px 0;">
                        <tr>
                          <td style="padding:16px 18px;font-size:15px;line-height:1.6;color:#047857;">
                            <strong>✓ Thành công:</strong> Mật khẩu của tài khoản đã được thay đổi thành công vào lúc <strong style="color:#065f46;">%s</strong>.
                          </td>
                        </tr>
                      </table>
                      
                      <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 20px 0;">Bây giờ bạn có thể sử dụng mật khẩu mới này để đăng nhập vào tất cả các dịch vụ của chúng tôi.</p>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#fff1f2;border-left:4px solid #f43f5e;border-radius:4px 8px 8px 4px;margin:20px 0 0 0;">
                        <tr>
                          <td style="padding:14px 18px;font-size:14px;line-height:1.5;color:#be123c;">
                            <strong>⚠️ Cảnh báo bảo mật:</strong> Nếu bạn không thực hiện yêu cầu thay đổi mật khẩu này, hãy liên hệ ngay với Quản trị viên để đóng băng tài khoản và bảo vệ thông tin.
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="background-color:#f8fafc;padding:32px;border-top:1px solid #e2e8f0;text-align:center;">
                      <p style="font-size:14px;color:#475569;margin:0 0 8px 0;font-weight:600;">Big Data Club (BDC) App</p>
                      <p style="font-size:12px;color:#64748b;line-height:1.5;margin:0;">Đây là email tự động từ hệ thống. Vui lòng không phản hồi trực tiếp email này.<br>&copy; 2026 Big Data Club. All rights reserved.</p>
                    </td>
                  </tr>
                </table>
              </div>
            </body>
            </html>
            """.formatted(name, LocalDateTime.now().format(DT_FORMAT));
    }

    public String buildForgotPasswordHtml(String name, String token) {
        String resetUrl = appUrl + "/confirm-password-change?token=" + token + "&type=reset";
        return """
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Đặt lại mật khẩu</title>
            </head>
            <body style="margin:0;padding:0;background-color:#f8fafc;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;">
              <div style="background-color:#f8fafc;padding:40px 10px;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 4px 12px rgba(0,0,0,0.03);margin:0 auto;">
                  <tr><td style="background:linear-gradient(90deg, #7c3aed, #4f46e5, #a78bfa);height:6px;line-height:6px;font-size:0px;padding:0;">&nbsp;</td></tr>
                  <tr>
                    <td align="center" style="padding:40px 32px 10px 32px;">
                      <table border="0" cellpadding="0" cellspacing="0">
                        <tr>
                          <td align="center" style="background-color:#f5f3ff;border-radius:12px;padding:12px 20px;font-weight:800;font-size:24px;color:#7c3aed;letter-spacing:1px;">
                            🔑
                          </td>
                        </tr>
                      </table>
                      <h1 style="font-size:22px;font-weight:700;color:#0f172a;margin:20px 0 0 0;letter-spacing:-0.5px;">Yêu cầu đặt lại mật khẩu</h1>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:20px 32px 30px 32px;">
                      <p style="font-size:16px;line-height:1.6;color:#334155;margin:0 0 16px 0;">Xin chào <strong style="color:#0f172a;">%s</strong>,</p>
                      <p style="font-size:15px;line-height:1.6;color:#475569;margin:0 0 24px 0;">Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Vui lòng click vào nút bên dưới để tiến hành tạo mật khẩu mới:</p>
                      
                      <table border="0" cellspacing="0" cellpadding="0" align="center" style="margin:30px auto;">
                        <tr>
                          <td align="center" style="border-radius:12px;background:linear-gradient(135deg, #7c3aed, #6366f1);box-shadow:0 4px 10px rgba(124, 58, 237, 0.25);">
                            <a href="%s" target="_blank" style="font-size:16px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;padding:14px 36px;border:1px solid transparent;display:inline-block;letter-spacing:0.5px;">Đặt lại mật khẩu</a>
                          </td>
                        </tr>
                      </table>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f5f3ff;border-left:4px solid #7c3aed;border-radius:4px 8px 8px 4px;margin:20px 0;">
                        <tr>
                          <td style="padding:14px 18px;font-size:14px;line-height:1.5;color:#6d28d9;">
                            💡 <strong>Lưu ý:</strong> Link đặt lại mật khẩu có hiệu lực trong vòng <strong>15 phút</strong> và chỉ sử dụng được duy nhất một lần.
                          </td>
                        </tr>
                      </table>
                      
                      <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color:#fff1f2;border-left:4px solid #f43f5e;border-radius:4px 8px 8px 4px;margin:20px 0 0 0;">
                        <tr>
                          <td style="padding:14px 18px;font-size:14px;line-height:1.5;color:#be123c;">
                            ⚠️ Nếu không phải bạn gửi yêu cầu này, vui lòng bỏ qua email. Tài khoản của bạn hiện vẫn được bảo mật an toàn.
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="background-color:#f8fafc;padding:32px;border-top:1px solid #e2e8f0;text-align:center;">
                      <p style="font-size:14px;color:#475569;margin:0 0 8px 0;font-weight:600;">Big Data Club (BDC) App</p>
                      <p style="font-size:12px;color:#64748b;line-height:1.5;margin:0;">Đây là email tự động từ hệ thống. Vui lòng không phản hồi trực tiếp email này.<br>&copy; 2026 Big Data Club. All rights reserved.</p>
                    </td>
                  </tr>
                </table>
              </div>
            </body>
            </html>
            """.formatted(name, resetUrl);
    }
}
