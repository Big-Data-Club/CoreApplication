"use client";

import React, { useState, useEffect } from "react";
import {
  User,
  Mail,
  Shield,
  Users,
  Tag,
  Camera,
  Save,
  Lock,
  Eye,
  EyeOff,
  Loader2,
  AlertCircle,
  CheckCircle,
  Send,
} from "lucide-react";
import { userService, UserResponse, UpdateProfileRequest } from "@/services/userService";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useUser } from "@/store/UserContext";
import Image from "next/image";
import TutorialGuide from '@/components/ui/TutorialGuide';
import { tutorialConfig } from '@/config/tutorials';

const MyAccountPage: React.FC = () => {
  const { user: currentUser, saveUser } = useCurrentUser();
  const { user } = useUser();
  const [activeTab, setActiveTab] = useState<"profile" | "password">("profile");
  const [loading, setLoading] = useState(false);
  const [fetchingUser, setFetchingUser] = useState(true);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Profile state
  const [profile, setProfile] = useState<UpdateProfileRequest>({
    name: "",
    email: "",
    team: "",
    type: "",
  });
  const [fullUserData, setFullUserData] = useState<UserResponse | null>(null);
  const [profilePictureFile, setProfilePictureFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");

  // Password state
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  });

  // Fetch user data
  useEffect(() => {
    const fetchUserData = async () => {
      if (!currentUser?.id && !user?.id) return;

      try {
        setFetchingUser(true);
        let userData;
        if (currentUser)
            userData = await userService.getById(currentUser.id);
        else if (user) userData = await userService.getById(user?.id);
        setFullUserData(userData);
        if (!userData) throw new Error("Not found user");
        setProfile({
          name: userData.name,
          email: userData.email,
          team: userData.team,
          type: userData.type,
        });
        if (userData.profilePicture) {
          setPreviewUrl(userData.profilePicture);
        }
      } catch (error: any) {
        console.error("Failed to fetch user data:", error);
        setMessage({ type: "error", text: "Failed to load user data" });
      } finally {
        setFetchingUser(false);
      }
    };

    fetchUserData();
  }, [currentUser, user, currentUser?.id, user?.id]);

  // Handle profile picture change
  const handleProfilePictureChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setProfilePictureFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewUrl(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  // Handle profile update
  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUser?.id && !user?.id) return;

    setLoading(true);
    setMessage(null);

    try {
      let pictureUrl = fullUserData?.profilePicture;
      if (profilePictureFile) {
        if (currentUser)
            pictureUrl = await userService.uploadProfilePicture(currentUser.id, profilePictureFile);
        else if (user)
            pictureUrl = await userService.uploadProfilePicture(user.id, profilePictureFile);
      }

      let updatedUser
      if (currentUser)
        updatedUser = await userService.updateProfile(currentUser.id, {
            ...profile,
            profilePicture: pictureUrl,
        });
      else if(user)
        updatedUser = await userService.updateProfile(user?.id, {
            ...profile,
            profilePicture: pictureUrl,
        });
      else throw new Error("Not found user");

      setFullUserData(updatedUser);
      saveUser({
        id: updatedUser.id,
        name: updatedUser.name,
        email: updatedUser.email,
        role: updatedUser.role,
      });

      setMessage({ type: "success", text: "Profile updated successfully!" });
      setProfilePictureFile(null);
    } catch (error: any) {
      setMessage({ type: "error", text: error.message || "Failed to update profile" });
    } finally {
      setLoading(false);
    }
  };

  // Validate password strength
  const validatePassword = (password: string) => {
    if (password.length < 8) {
      return "Password must be at least 8 characters";
    }
    
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasDigit = /[0-9]/.test(password);
    
    if (!hasUpper || !hasLower || !hasDigit) {
      return "Password must contain at least 1 uppercase letter, 1 lowercase letter, and 1 number";
    }
    
    return null;
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUser?.email && !user?.email) {
      setMessage({ type: "error", text: "User email not found" });
      return;
    }

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setMessage({ type: "error", text: "New passwords do not match" });
      return;
    }

    const passwordError = validatePassword(passwordForm.newPassword);
    if (passwordError) {
      setMessage({ type: "error", text: passwordError });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      const email = currentUser?.email || user?.email;
      if (!email) throw new Error("Email not found");

      const response = await userService.requestPasswordChange({
        email: email,
        currentPassword: passwordForm.currentPassword,
        newPassword: passwordForm.newPassword,
      });

      setMessage({ 
        type: "success", 
        text: response.message || "Confirmation email has been sent! Please check your inbox to complete password change." 
      });
      
      // Reset form
      setPasswordForm({
        currentPassword: "",
        newPassword: "",
        confirmPassword: "",
      });
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || error.message || "Failed to request password change";
      setMessage({ type: "error", text: errorMessage });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => setMessage(null), 10000);
      return () => clearTimeout(timer);
    }
  }, [message]);

  if (fetchingUser) {
    return (
      <div className="min-h-screen bg-gray-50 p-6 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-600">Loading account...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-transparent p-4 sm:p-6 lg:p-8" id="myaccount-page">
      <div className="max-w-4xl mx-auto" id="myaccount-header">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">My Account</h1>
          <p className="text-gray-600 mt-2">Manage your profile and account settings</p>
        </div>

        {/* Message Alert */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-lg flex items-start gap-3 ${
              message.type === "success"
                ? "bg-green-50 border border-green-200 text-green-800"
                : "bg-red-50 border border-red-200 text-red-800"
            }`}
          >
            {message.type === "success" ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <p className="font-medium">{message.text}</p>
              {message.type === "success" && message.text.includes("email") && (
                <p className="text-sm mt-1 opacity-90">
                  Check your email inbox and click the confirmation link to complete the password change.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-4 mb-6 border-b border-gray-200" id="myaccount-tabs">
          <button
            onClick={() => setActiveTab("profile")}
            className={`px-6 py-3 font-medium transition-colors relative ${
              activeTab === "profile"
                ? "text-blue-600 border-b-2 border-blue-600"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <User className="w-4 h-4 inline-block mr-2" />
            Profile
          </button>
          <button
            onClick={() => setActiveTab("password")}
            className={`px-6 py-3 font-medium transition-colors relative ${
              activeTab === "password"
                ? "text-blue-600 border-b-2 border-blue-600"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            <Lock className="w-4 h-4 inline-block mr-2" />
            Password
          </button>
        </div>

        {/* Profile Tab */}
        {activeTab === "profile" && (
          <div className="bg-white rounded-xl shadow-sm p-6" id="myaccount-profile-tab">
            <form onSubmit={handleUpdateProfile}>
              {/* Profile Picture */}
              <div className="flex items-center gap-6 mb-8 pb-8 border-b border-gray-200">
                <div className="relative">
                  <div className="w-24 h-24 rounded-full bg-gray-200 overflow-hidden">
                    {previewUrl ? (
                      <Image
                        src={previewUrl}
                        alt="Profile"
                        className="w-full h-full object-cover"
                        width={32}
                        height={32}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-400">
                        <User className="w-12 h-12" />
                      </div>
                    )}
                  </div>
                  <label
                    htmlFor="profilePicture"
                    className="absolute bottom-0 right-0 bg-blue-500 text-white p-2 rounded-full cursor-pointer hover:bg-blue-600 transition-colors"
                  >
                    <Camera className="w-4 h-4" />
                    <input
                      id="profilePicture"
                      type="file"
                      accept="image/*"
                      onChange={handleProfilePictureChange}
                      className="hidden"
                    />
                  </label>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">{fullUserData?.name}</h3>
                  <p className="text-gray-600">{fullUserData?.email}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    <Shield className="w-3 h-3 inline-block mr-1" />
                    {fullUserData?.role}
                  </p>
                </div>
              </div>

              {/* Form Fields */}
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <User className="w-4 h-4 inline-block mr-2" />
                    Full Name
                  </label>
                  <input
                    type="text"
                    value={profile.name}
                    onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <Mail className="w-4 h-4 inline-block mr-2" />
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={profile.email}
                    onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <Tag className="w-4 h-4 inline-block mr-2" />
                    MSSV
                  </label>
                  <input
                    type="text"
                    value={fullUserData?.code || ""}
                    className="w-full px-4 py-3 border border-gray-200 rounded-lg text-gray-600 bg-gray-50"
                    disabled
                  />
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      <Users className="w-4 h-4 inline-block mr-2" />
                      Team
                    </label>
                    <input
                      type="text"
                      value={profile.team}
                      className="w-full px-4 py-3 border border-gray-200 rounded-lg bg-gray-50 text-gray-600"
                      disabled
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      <Tag className="w-4 h-4 inline-block mr-2" />
                      Sinh viên
                    </label>
                    <input
                      type="text"
                      value={profile.type}
                      className="w-full px-4 py-3 border border-gray-200 rounded-lg text-gray-600 bg-gray-50"
                      disabled
                    />
                  </div>
                </div>
              </div>

              {/* Submit Button */}
              <div className="mt-8">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <Save className="w-5 h-5" />
                      Save Changes
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Password Tab - UPDATED */}
        {activeTab === "password" && (
          <div className="bg-white rounded-xl shadow-sm p-6" id="myaccount-password-tab">
            {/* Info Box */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex gap-3">
                <Send className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-medium text-blue-900 mb-1">Email Verification Required</h4>
                  <p className="text-sm text-blue-800">
                    For security reasons, we will send a confirmation email to verify your password change. 
                    You will need to click the link in the email to complete the process.
                  </p>
                </div>
              </div>
            </div>

            <form onSubmit={handleChangePassword}>
              <div className="space-y-6">
                {/* Current Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Current Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.current ? "text" : "password"}
                      value={passwordForm.currentPassword}
                      onChange={(e) =>
                        setPasswordForm({ ...passwordForm, currentPassword: e.target.value })
                      }
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-12"
                      required
                      placeholder="Enter your current password"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowPasswords({ ...showPasswords, current: !showPasswords.current })
                      }
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showPasswords.current ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>

                {/* New Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    New Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.new ? "text" : "password"}
                      value={passwordForm.newPassword}
                      onChange={(e) =>
                        setPasswordForm({ ...passwordForm, newPassword: e.target.value })
                      }
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-12"
                      required
                      minLength={8}
                      placeholder="Enter your new password"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowPasswords({ ...showPasswords, new: !showPasswords.new })
                      }
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showPasswords.new ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Password must be at least 8 characters and include uppercase, lowercase, and numbers
                  </p>
                </div>

                {/* Confirm Password */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Confirm New Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPasswords.confirm ? "text" : "password"}
                      value={passwordForm.confirmPassword}
                      onChange={(e) =>
                        setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })
                      }
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent pr-12"
                      required
                      placeholder="Confirm your new password"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })
                      }
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                      {showPasswords.confirm ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Submit Button */}
              <div className="mt-8">
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Sending Confirmation Email...
                    </>
                  ) : (
                    <>
                      <Send className="w-5 h-5" />
                      Request Password Change
                    </>
                  )}
                </button>
              </div>

              {/* Additional Info */}
              <div className="mt-6 p-4 bg-gray-50 border border-gray-200 rounded-lg">
                <p className="text-sm text-gray-600">
                  <strong>How it works:</strong>
                </p>
                <ol className="text-sm text-gray-600 mt-2 ml-4 space-y-1 list-decimal">
                  <li>Enter your current password and new password</li>
                  <li>Click Request Password Change</li>
                  <li>Check your email for a confirmation link</li>
                  <li>Click the link to complete the password change</li>
                </ol>
              </div>
            </form>
          </div>
        )}

        {/* Account Stats */}
        <div className="mt-8 bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">Account Statistics</h3>
          <div className="grid grid-cols-3 gap-6">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">
                {fullUserData?.totalScore || 0}
              </div>
              <div className="text-sm text-gray-600 mt-1">Total Score</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">
                {fullUserData?.active ? "Active" : "Inactive"}
              </div>
              <div className="text-sm text-gray-600 mt-1">Status</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">
                {fullUserData?.team || "N/A"}
              </div>
              <div className="text-sm text-gray-600 mt-1">Team</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tutorial Guide Component */}
      <TutorialGuide 
        steps={tutorialConfig.myaccount}
        onComplete={() => {}}
      />
    </div>
  );
};

export default MyAccountPage;