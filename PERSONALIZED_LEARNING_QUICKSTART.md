# Personalized Learning Engine - Quick Start Guide

## 🚀 Khởi động nhanh trong 10 phút

### Bước 1: Khởi động Backend (2 phút)

```bash
# Terminal 1: LMS Service
cd lms-service
go run cmd/api/main.go
# Đợi thấy: "Starting LMS server on port 3000"

# Terminal 2: Personalize Service  
cd personalize-service
python main.py
# Đợi thấy: "Learning event worker started"

# Terminal 3: Recommender Service
cd recommender-service
uvicorn app.main:app --reload
# Đợi thấy: "Application startup complete"
```

### Bước 2: Khởi động Frontend (1 phút)

```bash
# Terminal 4: Frontend
cd frontend
npm run dev
# Mở browser: http://localhost:3000
```

### Bước 3: Test thử (5 phút)

1. **Login** vào hệ thống với tài khoản student
2. **Navigate** đến `/lms/student`
3. **Xem** personalized learning components:
   - Gợi ý học tập hôm nay
   - Kỹ năng của tôi
4. **Navigate** đến `/lms/student/discover`
5. **Xem** khóa học được gợi ý dựa trên skills
6. **Take a quiz** và submit answers
7. **Refresh** dashboard để xem skill progress update

### Bước 4: Kiểm tra Events (2 phút)

```bash
# Mở DevTools → Network → Filter "personalized"
# Take a quiz và submit answer
# Sẽ thấy POST request đến /personalized-learning/events

# Check Kafka consumer logs
# Sẽ thấy: "Processing learning event: answer_submitted"

# Check database
psql -U postgres -d lms_db -c "SELECT COUNT(*) FROM learning_events;"
# Sẽ thấy số events tăng lên
```

## 📦 Các Component Chính

### Frontend Components (3 components)
- `PersonalizedLearningDashboard` - Gợi ý học hôm nay
- `SkillMasteryOverview` - Tổng quan kỹ năng
- `PersonalizedCourseDiscovery` - Khám phá khóa học

### Backend APIs (5 endpoints)
- `POST /events` - Track learning events
- `GET /students/:id/skills/overview` - Skill overview
- `GET /students/:id/recommendations/daily` - Daily plan
- `GET /students/:id/recommendations/discover-courses` - Course suggestions
- `GET /students/:id/trajectory` - Learning history

## 🎨 Design Features

✅ No emojis (dùng lucide-react icons)  
✅ Dark mode support  
✅ Tailwind CSS theme compliance  
✅ Smooth animations  
✅ Responsive design  

## 📊 Data Flow

```
Quiz Answer → LMS API → Kafka → Personalize Service → Skill Update → Frontend Display
   (1s)         (100ms)    (10ms)      (200ms)          (100ms)         (refresh)
```

## 🔧 Troubleshooting Nhanh

### Components không hiển thị?
→ Check browser console, verify user logged in

### Events không tracked?
→ Check Network tab, verify Kafka consumer running

### Slow performance?
→ Check Redis cache, verify database indexes

## 📖 Chi Tiết Hơn

- Backend: `docs/PERSONALIZED_LEARNING_INTEGRATION.md`
- Frontend: `FRONTEND_PERSONALIZED_LEARNING_GUIDE.md`
- Deployment: `DEPLOYMENT_CHECKLIST.md`
- Summary: `PERSONALIZED_LEARNING_SUMMARY.md`

## 🎯 Next Steps

1. Create or import a competency framework, then map course content and questions to its competencies. V016 intentionally seeds no subject-specific data.
2. Test với real users
3. Monitor metrics
4. Iterate based on feedback

**Happy Learning! 🚀**
