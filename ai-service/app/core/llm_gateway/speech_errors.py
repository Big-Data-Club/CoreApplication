"""Safe speech diagnostics: never echo provider bodies, keys or narration."""
from app.core.llm_gateway.errors import AuthError, NoKeyAvailableError, NoModelAvailableError, ProviderError, RateLimitedError
from app.core.llm_gateway.crypto import KeyCryptoError


class SpeechProviderError(ProviderError):
    def __init__(self, code: str, *, provider: str = "speech", status_code: int | None = None, retryable: bool = False):
        self.code = code
        self.provider = provider
        super().__init__(f"{provider}: {code}" + (f" (HTTP {status_code})" if status_code else ""),
                         status_code=status_code, retryable=retryable)


def speech_failure_message(error: Exception, *, stage: str = "synthesis") -> str:
    if stage == "audio_processing":
        return "Đã nhận audio nhưng không xử lý được. Kiểm tra FFmpeg và định dạng audio trong log worker."
    if stage == "storage":
        return "Đã tạo audio nhưng không lưu được. Kiểm tra kết nối và quyền ghi MinIO của worker."
    if isinstance(error, NoModelAvailableError):
        return "Chưa có model giọng nói hoạt động trong task text_to_speech của Gateway."
    if isinstance(error, NoKeyAvailableError):
        return "Không có key hoạt động cho provider được gán task text_to_speech. Kiểm tra đúng provider, trạng thái key và cooldown."
    if isinstance(error, KeyCryptoError):
        return "Worker không giải mã được key. Kiểm tra AI_KEY_ENCRYPTION_SECRET của AI HTTP và worker có cùng giá trị."
    if isinstance(error, RateLimitedError):
        return "Dịch vụ giọng nói đang giới hạn tốc độ hoặc quota (HTTP 429). Chờ hết cooldown hoặc kiểm tra gói dịch vụ."
    if isinstance(error, AuthError):
        return f"Dịch vụ giọng nói từ chối key hoặc quyền API (HTTP {error.status_code}). Kiểm tra key của đúng provider và quyền của tổ chức."
    if isinstance(error, SpeechProviderError):
        name = {"runway": "Runway", "elevenlabs": "ElevenLabs"}.get(error.provider, "Dịch vụ giọng nói")
        messages = {
            "credits_required": f"{name} yêu cầu thanh toán hoặc không đủ credit. Thêm API key chưa đồng nghĩa tài khoản đã có credit.",
            "voice_required": f"{name} chưa cấu hình model.config.voice_id. ElevenLabs cần voice ID thực; Niki là preset của Runway.",
            "request_rejected": f"{name} từ chối cấu hình/request (HTTP {error.status_code}). Kiểm tra model, voice, ngôn ngữ và tham số; xem text_to_speech trong Gateway.",
            "not_found": f"{name} không tìm thấy endpoint, model hoặc voice (HTTP 404). Kiểm tra base URL và model/voice đã chọn.",
            "asset_download": f"{name} đã tạo tác vụ nhưng tải file audio không thành công. Kiểm tra mạng/URL audio trong worker; đây không phải lỗi API key.",
            "task_failed": f"{name} báo tác vụ tạo giọng thất bại. Xem trạng thái tác vụ và credit trong tài khoản provider.",
            "unsupported_adapter": "Task text_to_speech phải dùng provider adapter runway hoặc elevenlabs.",
            "invalid_speed": "Tốc độ giọng nói phải nằm trong khoảng 0.7–1.2.",
            "transport_failed": f"Không kết nối được {name}. Kiểm tra mạng, DNS và base URL của worker.",
            "timeout": f"{name} tạo giọng quá thời gian cho phép. Kiểm tra tác vụ và trạng thái dịch vụ trước khi thử lại.",
        }
        return messages.get(error.code, f"{name} không trả về audio hợp lệ. Kiểm tra log text_to_speech trong Gateway.")
    if isinstance(error, FileNotFoundError):
        return "Worker thiếu công cụ xử lý audio. Kiểm tra FFmpeg trong image đang chạy."
    if isinstance(error, TimeoutError):
        return "Tạo giọng quá thời gian cho phép. Kiểm tra trạng thái tác vụ trong log worker."
    return "Không hoàn tất được giọng neural. Xem Speech generation failed trong log worker để xác định bước lỗi."
