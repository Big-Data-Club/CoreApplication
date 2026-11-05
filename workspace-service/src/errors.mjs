export class HttpError extends Error {
  constructor(status, message, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}
export function assert(condition, status, message, code) {
  if (!condition) throw new HttpError(status, message, code);
}
