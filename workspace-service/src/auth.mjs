import { jwtVerify } from "jose";
import { HttpError } from "./errors.mjs";

export function jwtIdentity(secret) {
  if (!secret || Buffer.byteLength(secret) < 32)
    throw new Error("JWT_SECRET must contain at least 32 bytes");
  const key = new TextEncoder().encode(secret);
  return async (request) => {
    const token = /^Bearer ([^\s]+)$/.exec(
      request.headers.authorization || "",
    )?.[1];
    if (!token) throw new HttpError(401, "Vui lòng đăng nhập.", "unauthorized");
    try {
      const { payload } = await jwtVerify(token, key, {
        algorithms: ["HS256", "HS384", "HS512"],
        requiredClaims: ["exp", "iat"],
      });
      const id = String(payload.user_id || "");
      const email = String(payload.email || payload.sub || "").toLowerCase();
      if (
        !/^[1-9][0-9]{0,18}$/.test(id) ||
        !email.includes("@") ||
        !Array.isArray(payload.roles) ||
        !payload.roles.length
      )
        throw Error("Invalid identity");
      return {
        id,
        email,
        name: email.split("@")[0],
        expiresAt: Number(payload.exp) * 1000,
      };
    } catch {
      throw new HttpError(401, "Phiên đăng nhập đã hết hạn.", "unauthorized");
    }
  };
}
