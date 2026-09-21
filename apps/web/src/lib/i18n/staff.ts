export type Locale = "en" | "vi";

export const translations = {
  en: {
    // Auth
    login: "Login",
    email: "Email",
    password: "Password",
    loginTitle: "Staff Sign In",
    loginSubtitle: "Internal knowledge assistant for bank staff",
    loginButton: "Sign In",
    loginError: "Invalid email or password",
    logout: "Logout",

    // Change password
    changePasswordTitle: "Change Password",
    changePasswordSubtitle: "You must change your password before continuing",
    currentPassword: "Current Password",
    newPassword: "New Password",
    confirmPassword: "Confirm Password",
    changePasswordButton: "Change Password",
    passwordMismatch: "Passwords do not match",
    passwordTooShort: "Password must be at least 6 characters",

    // Chat
    selectApp: "Select an assistant",
    selectAppSubtitle: "Choose an assistant from the sidebar to start",
    newChat: "+ New conversation",
    typeMessage: "Ask about a process, policy, product...",
    send: "Send",
    noApps: "No assistants available",
    startConversation: "Start a conversation with",
    connectionError: "Connection error.",
    noResponse: "No response received.",
    workflowError: "Workflow error",
    sources: "Sources",
    disclaimer: "Answers are generated from internal documents and must be verified against the original text before use.",
    suggestedTitle: "Try asking",

    // Theme
    darkMode: "Dark mode",
    lightMode: "Light mode",

    // General
    language: "Language",
    bankWide: "Bank-wide",
    unit: "Unit",
  },
  vi: {
    // Auth
    login: "Đăng nhập",
    email: "Email",
    password: "Mật khẩu",
    loginTitle: "Đăng nhập Cán bộ",
    loginSubtitle: "Trợ lý tri thức nội bộ dành cho cán bộ ngân hàng",
    loginButton: "Đăng nhập",
    loginError: "Email hoặc mật khẩu không đúng",
    logout: "Đăng xuất",

    // Change password
    changePasswordTitle: "Đổi mật khẩu",
    changePasswordSubtitle: "Bạn cần đổi mật khẩu trước khi tiếp tục",
    currentPassword: "Mật khẩu hiện tại",
    newPassword: "Mật khẩu mới",
    confirmPassword: "Xác nhận mật khẩu",
    changePasswordButton: "Đổi mật khẩu",
    passwordMismatch: "Mật khẩu không khớp",
    passwordTooShort: "Mật khẩu phải có ít nhất 6 ký tự",

    // Chat
    selectApp: "Chọn trợ lý",
    selectAppSubtitle: "Chọn một trợ lý ở menu bên trái để bắt đầu",
    newChat: "+ Hội thoại mới",
    typeMessage: "Hỏi về quy trình, quy định, sản phẩm...",
    send: "Gửi",
    noApps: "Chưa có trợ lý nào được công bố",
    startConversation: "Bắt đầu hội thoại với",
    connectionError: "Lỗi kết nối.",
    noResponse: "Không nhận được phản hồi.",
    workflowError: "Lỗi luồng xử lý",
    sources: "Nguồn trích dẫn",
    disclaimer: "Câu trả lời được tổng hợp từ văn bản nội bộ, cần đối chiếu với văn bản gốc trước khi áp dụng.",
    suggestedTitle: "Gợi ý câu hỏi",

    // Theme
    darkMode: "Chế độ tối",
    lightMode: "Chế độ sáng",

    // General
    language: "Ngôn ngữ",
    bankWide: "Toàn ngân hàng",
    unit: "Đơn vị",
  },
} as const;

export type TranslationKey = keyof typeof translations.en;
