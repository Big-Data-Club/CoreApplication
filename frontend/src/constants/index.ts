export const defaultValues = {
  title: "",
  aspectRatio: "",
  color: "",
  prompt: "",
  publicId: "",
};

export const creditFee = -1;

// API Configuration
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000/apiv1";

// Cookie names
export const AUTH_COOKIE_NAME = "authToken";

// Local storage keys
export const USER_STORAGE_KEY = "currentUser";