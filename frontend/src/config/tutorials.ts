import { TutorialStep } from '@/components/ui/TutorialGuide';

// Tutorial cho Dashboard Page
export const dashboardTutorial: TutorialStep[] = [
  {
    targetId: 'dashboard-header',
    title: 'Chào mừng bạn!',
    description: 'Đây là trang Dashboard của bạn, nơi hiển thị thông tin tổng quan về CLB và các hoạt động.',
    position: 'bottom',
  },
  {
    targetId: 'stats-cards',
    title: 'Thống kê',
    description: 'Xem các thống kê quan trọng như số sự kiện, thành viên, và các hoạt động đang diễn ra.',
    position: 'bottom',
  },
  {
    targetId: 'announcements-section',
    title: 'Thông báo',
    description: 'Tất cả thông báo quan trọng từ CLB sẽ được hiển thị ở đây. Quản trị viên có thể thêm/sửa/xóa thông báo.',
    position: 'bottom',
  },
  {
    targetId: 'events-section',
    title: 'Sự kiện',
    description: 'Xem danh sách các sự kiện sắp tới và đang diễn ra. Bấm "Xem tất cả" để xem thêm chi tiết.',
    position: 'bottom',
  },
];

// Tutorial cho Events Page
export const eventsTutorial: TutorialStep[] = [
  {
    targetId: 'events-header',
    title: 'Trang quản lý sự kiện',
    description: 'Quản lý tất cả các sự kiện của CLB ở đây.',
    position: 'bottom',
  },
  {
    targetId: 'events-search-filter',
    title: 'Tìm kiếm & Lọc',
    description: 'Sử dụng các bộ lọc để tìm kiếm sự kiện theo từ khóa, trạng thái hoặc sắp xếp theo ngày tạo.',
    position: 'bottom',
  },
  {
    targetId: 'events-add-button',
    title: 'Thêm sự kiện',
    description: 'Bấm nút này để tạo một sự kiện mới (chỉ quản trị viên).',
    position: 'left',
  },
  {
    targetId: 'events-grid',
    title: 'Danh sách sự kiện',
    description: 'Xem các sự kiện dưới dạng thẻ. Bấm trên mỗi thẻ để xem chi tiết, chỉnh sửa hoặc xóa.',
    position: 'top',
  },
];

// Tutorial cho Tasks Page
export const tasksTutorial: TutorialStep[] = [
  {
    targetId: 'tasks-header',
    title: 'Bảng công việc Kanban',
    description: 'Quản lý các công việc của bạn bằng hệ thống Kanban. Kéo thả để di chuyển công việc giữa các cột.',
    position: 'bottom',
  },
  {
    targetId: 'tasks-columns',
    title: 'Các cột trạng thái',
    description: 'Mỗi cột đại diện cho một trạng thái: TODO, In Progress, Done, Cancel. Kéo thả công việc để thay đổi trạng thái.',
    position: 'bottom',
  },
  {
    targetId: 'tasks-add-button',
    title: 'Thêm công việc',
    description: 'Bấm nút "+" trên mỗi cột để tạo công việc mới trong cột đó.',
    position: 'left',
  },
];

// Tutorial cho Users Page
export const usersTutorial: TutorialStep[] = [
  {
    targetId: 'users-header',
    title: 'Quản lý thành viên',
    description: 'Xem danh sách tất cả thành viên của CLB.',
    position: 'bottom',
  },
  {
    targetId: 'users-search',
    title: 'Tìm kiếm thành viên',
    description: 'Tìm kiếm thành viên theo tên hoặc email.',
    position: 'bottom',
  },
  {
    targetId: 'users-table',
    title: 'Bảng thành viên',
    description: 'Xem thông tin chi tiết về từng thành viên: tên, email, vai trò, điểm, trạng thái.',
    position: 'top',
  },
];

// Tutorial cho Leaderboard Page
export const leaderboardTutorial: TutorialStep[] = [
  {
    targetId: 'leaderboard-header',
    title: 'Bảng xếp hạng',
    description: 'Xem bảng xếp hạng các thành viên theo điểm tích lũy.',
    position: 'bottom',
  },
  {
    targetId: 'leaderboard-filters',
    title: 'Bộ lọc thời gian',
    description: 'Chọn khoảng thời gian để xem bảng xếp hạng: Hôm nay, Tuần này, Tháng này, hoặc Tất cả.',
    position: 'bottom',
  },
  {
    targetId: 'leaderboard-podium',
    title: 'Top 5 champions',
    description: 'Xem 5 thành viên hàng đầu với điểm cao nhất.',
    position: 'bottom',
  },
];

// Tutorial cho MyAccount Page
export const myAccountTutorial: TutorialStep[] = [
  {
    targetId: 'myaccount-header',
    title: 'Tài khoản của bạn',
    description: 'Quản lý thông tin cá nhân và bảo mật tài khoản của bạn.',
    position: 'bottom',
  },
  {
    targetId: 'myaccount-profile-tab',
    title: 'Tab Hồ sơ',
    description: 'Cập nhật thông tin cá nhân như tên, email, đội, ảnh đại diện của bạn.',
    position: 'bottom',
  },
  {
    targetId: 'myaccount-password-tab',
    title: 'Tab Đổi mật khẩu',
    description: 'Thay đổi mật khẩu của bạn để bảo mật tài khoản.',
    position: 'bottom',
  },
];

// Tutorial cho Hackathon Page
export const hackathonTutorial: TutorialStep[] = [
  {
    targetId: 'hackathon-hero',
    title: 'BDC Data Hackathon 2025',
    description: 'Chào mừng bạn tới trang hackathon. Xem thông tin về cuộc thi và đăng ký tham gia.',
    position: 'bottom',
  },
  {
    targetId: 'hackathon-info',
    title: 'Thông tin cuộc thi',
    description: 'Xem ngày thi, địa điểm, và tổng giải thưởng của cuộc thi.',
    position: 'bottom',
  },
  {
    targetId: 'hackathon-timeline-r2',
    title: 'Lịch trình Vòng 2',
    description: 'Xem lịch trình chi tiết của vòng thi on-site. Progress bar sẽ hiển thị tiến độ cuộc thi.',
    position: 'top',
  },
  {
    targetId: 'hackathon-timeline-r3',
    title: 'Lịch trình Vòng 3',
    description: 'Xem lịch trình của vòng chung kết với các hoạt động và thời gian.',
    position: 'top',
  },
  {
    targetId: 'hackathon-register',
    title: 'Đăng ký',
    description: 'Bấm nút "ĐĂNG KÝ NGAY" để đăng ký tham gia hackathon.',
    position: 'top',
  },
];

export const tutorialConfig = {
  dashboard: dashboardTutorial,
  events: eventsTutorial,
  tasks: tasksTutorial,
  users: usersTutorial,
  leaderboard: leaderboardTutorial,
  myaccount: myAccountTutorial,
  hackathon: hackathonTutorial,
};
