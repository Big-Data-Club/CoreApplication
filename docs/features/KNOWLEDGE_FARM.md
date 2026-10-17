# Nông trại kiến thức

Owner: Farm / Auth / Frontend maintainers. Implementation: `farm-service/`,
`auth-and-management-service/src/main/java/com/example/demo/service/farm/`,
`frontend/src/features/knowledge-farm/`.

## Phạm vi hiện tại

Game học tập tại `/knowledge-farm`, có mục trên sidebar. Bản đồ khởi đầu có
lúa, hoa và gà; cửa hàng cho trồng/nuôi thêm các loài khác. Sprite và ý tưởng
chọn ô/chăm sóc/nghỉ sau thu hoạch được chuyển từ source XanhMarket VuiVe do
người dùng cung cấp. Không có broker, đơn hàng, giao dịch, camera, IoT hoặc
kết nối nông trại thật. UI dùng bản đồ Phaser và sprite pixel art.
HUD, thao tác chăm sóc, cửa hàng, kho và bán hàng nằm trong một khung game;
nút `ⓘ` mở sổ tay pixel chứa kiến thức loài, mục tiêu và hướng dẫn điều khiển.

Mỗi loại có thông tin môi trường, quy trình chăm sóc thực tế, điều thú vị và
liên kết nguồn trong `farm-service/internal/farm/catalog.json`. Đây là kiến
thức nhập môn; đồng hồ game, thao tác chăm sóc và tái sinh 40 giây không mô
phỏng đầy đủ quy trình sinh học thực tế.

1. Chọn cây hoặc vật nuôi trên bản đồ, dùng thao tác hiện cạnh bản đồ;
   nhấn `ⓘ` để đọc kiến thức và quy trình chăm sóc thực tế.
2. Server lưu thời điểm có thể thu hoạch; tải lại trang không làm mất tiến độ.
3. Khi sẵn sàng, chọn quiz hoặc flashcard nhập đáp án. Một challenge có hiệu
   lực 10 phút; mở lại không đổi câu đang còn hiệu lực.
4. Đáp án đúng mới thu hoạch. Sai thì giữ nguyên sản phẩm, hiển thị đáp án đúng và giải thích,
   khóa thử lại 30 giây và phát câu mới. Flashcard chấm sau chuẩn hóa Unicode,
   hoa/thường và khoảng trắng; không phải tự đánh dấu “đã nhớ”.
5. Đúng nhận 5 điểm, tối đa 100 điểm mỗi ngày UTC (đặt lại 07:00 Việt Nam).
   Đạt trần vẫn học và thu hoạch được nhưng không thêm điểm. Sau thu hoạch,
   ô nghỉ 40 giây, rồi cần chăm lại để bắt đầu lượt tiếp theo.

Game lấy quiz một đáp án từ question bank đã duyệt của khóa học học viên đã
được chấp nhận, hoặc flashcard đang hoạt động của chính học viên qua LMS. Nếu
không có nội dung phù hợp, game báo thiếu câu hỏi; không lấy câu của khóa học
khác hoặc tự tạo đáp án. Farm giữ snapshot của câu đã mở để đáp án không đổi
giữa lượt. Bộ câu hỏi nội bộ cũ chỉ còn dùng cho API sáu ô legacy và test.

## Ranh giới và API

- Farm sở hữu database riêng, gồm `farm_states`, `farm_answers`, `farm_outbox`.
- Auth sở hữu `users.total_score` (Java `User.totalScore`) và inbox
  `farm_score_receipts`. Không tạo một trường `score` mới cạnh trường hiện tại.
- Browser chỉ gọi Next.js BFF `/api/farm`; BFF lấy access token từ session,
  kiểm tra Origin khi POST, giới hạn body 4 KiB và chỉ proxy các route cho phép.
- Farm xác thực chữ ký HMAC JWT, expiration, `user_id > 0`, access-token roles;
  refresh token không có roles bị từ chối. Không nhận user ID hay điểm từ client.

| Farm route | Method | Body |
|---|---|---|
| `/api/v1/farm` | GET | — |
| `/api/v1/farm/plots/{1..6}/care` | POST | `{}` |
| `/api/v1/farm/plots/{1..6}/challenge` | POST | `{"kind":"quiz"}` hoặc `flashcard` |
| `/api/v1/farm/plots/{1..6}/answer` | POST | `{"challenge_id":"uuid","answer":"0"}`; quiz dùng index dạng chuỗi, flashcard dùng text |

GET và care/challenge trả `{state,catalog,server_time,pending_events,daily_limit,reward}`.
Answer trả `{correct,correct_answer,explanation,awarded,event_id?}`. Không trả đáp án hay giải
thích của challenge đang mở. Request trùng challenge trả lại kết quả đã lưu.
Các mã lỗi: 400 payload, 401 phiên, 404 route/ô, 409 trạng thái/hết hạn,
503 lỗi phụ thuộc. `/health` là liveness; `/ready` kiểm tra database.

## Điểm bất đồng bộ

```mermaid
sequenceDiagram
    participant UI as Frontend BFF
    participant Farm as Farm service
    participant DB as Farm PostgreSQL
    participant K as Kafka
    participant Auth as Java Auth
    participant ADB as Auth PostgreSQL
    UI->>Farm: Trả lời challenge
    Farm->>DB: Lock farm; chấm; lưu thu hoạch + receipt + outbox
    DB-->>Farm: Commit
    Farm-->>UI: Kết quả và điểm được thưởng
    Farm->>K: Outbox worker gửi sự kiện đã ký
    K->>Auth: farm.harvest.reward.v1
    Auth->>ADB: Inbox unique + cộng users.total_score trong một transaction
    ADB-->>Auth: Commit
    Auth-->>K: Commit offset
```

Chi tiết contract ở [Data Platform](../DATA_PLATFORM.md#knowledge-farm-rewards).
Khóa farm theo user làm cho nhiều tab/replica không thể thu hoạch trùng.
Outbox worker dùng `FOR UPDATE SKIP LOCKED`, broker acknowledgement trước
khi đánh dấu published. Kafka hỏng không làm mất lượt thu hoạch. Java nhận
trùng sẽ không cộng lại; DB lỗi làm rollback cả inbox và điểm, rồi retry.
Cộng điểm task cũng đổi sang SQL increment, và User dùng dynamic update để
một cập nhật hồ sơ đồng thời không ghi đè số điểm cũ.

`earned` là điểm được farm trao, không phải tổng điểm tài khoản.
`pending_events` là số sự kiện chưa được broker xác nhận, **không** phải ACK
cộng điểm từ Java. UI không tuyên bố “đã đồng bộ” khi mới publish.
BFF `/api/farm/score` đọc tổng chính thức từ Auth `/api/users/{session.user.id}`,
chỉ trả `total_score`. UI cập nhật mỗi 15 giây; lỗi đọc tổng điểm không chặn
chơi game. Độ trễ phụ thuộc broker/consumer và chu kỳ tải lại.

## Câu hỏi LMS và thống kê

Farm gọi `GET /api/v1/internal/farm/question` của LMS bằng `X-API-Secret`
(`AI_SERVICE_SECRET` sẵn có), chỉ từ mạng dịch vụ. LMS tự kiểm tra enrollment
`ACCEPTED`, khóa học `PUBLISHED`, và với flashcard chỉ lấy thẻ của học viên.
Endpoint nội bộ trả đáp án cho Farm để chấm trên server; browser chỉ thấy bản
challenge đã lược đáp án. Không mở route nội bộ qua Next.js BFF.

Mỗi câu đã trả lời, đúng hoặc sai, được ghi vào `game_learning_outbox` trong
cùng transaction với `farm_answers`. Worker Farm gửi
`POST /api/v1/internal/farm/attempt` với `challenge_id` ổn định. LMS ghi
`farm_learning_attempts`, `micro_lesson_interactions` và cập nhật
`knowledge_node_mastery` trong một transaction; `challenge_id` là khóa chống
đếm trùng. Quiz góp mẫu `mini_quiz_score`; flashcard góp mẫu engagement và
điểm đúng/sai trong interaction log. Câu không có `node_id` vẫn được ghi vào
log theo khóa học nhưng không góp heatmap theo node. Đây là thống kê luyện
tập, không tự đánh dấu bài học/quiz chính thức đã hoàn thành.

LMS V019 được áp dụng bằng migration cộng thêm khi LMS khởi động, có advisory
lock cho nhiều replica. Farm V003 được áp dụng bởi schema cộng thêm lúc Farm
khởi động. Rollout LMS trước Farm để endpoint và bảng đã sẵn sàng; nếu LMS
tạm lỗi, outbox Farm giữ lượt trả lời và gửi lại. Không thêm GitHub Secret:
Farm dùng `AI_SERVICE_SECRET` hiện có và `LMS_SERVICE_URL` trong ConfigMap.

## Chạy local

Chuẩn bị `.env` ngoài Git: JWT giống Auth, `FARM_EVENT_SECRET` ngẫu nhiên ít
nhất 32 byte, `FARM_POSTGRES_PASSWORD` riêng, `FARM_REWARDS_ENABLED=true`.
Không tái sử dụng mật khẩu production. Các biến mẫu có trong `.env.example`.

```bash
docker compose --profile farm up -d --build postgres-farm farm-topic farm-service backend frontend
```

Profile `farm` tránh bắt các môi trường chưa cấu hình phải chạy game. Auth
mặc định không bật consumer. Local Hibernate `ddl-auto=update` tạo inbox từ
entity; môi trường schema quản lý thủ công phải áp dụng migration trước.
Compose serverless dùng `FARM_DATABASE_URL` trỏ database riêng qua TLS, không
trỏ database LMS/Auth. Password trong URL cần URL-encode. Compose local dùng
PG* variables nên password không phải ghép vào URL.

## Rollout K3s

Database **`gamefarm`** và migration SQL đã được quản trị viên tạo/chạy trước.
Rollout chỉ đồng bộ cấu hình kết nối vào Kubernetes, không tạo DB/role hay
chạy migration Job. Không cần SSH chỉnh `.env` hoặc tạo Secret trên server.

`scripts/sync-farm-config.py` tự tạo/cập nhật `bdc-farm-secrets` khi deploy Farm:

- Mặc định lấy host từ `bdc-config`, user/password hiện có trong `bdc-secrets`,
  tạo connection URL với database `gamefarm` và TLS theo cấu hình hiện tại.
  Cách này dành cho gamefarm dùng chung tài khoản Neon với các service khác;
  tài khoản đó cần có quyền truy cập schema gamefarm đã tạo.
- Nếu dùng tài khoản riêng, đặt GitHub Actions Secret **`FARM_DATABASE_URL`**
  trong repo parent hoặc environment **`production`**. Giá trị là PostgreSQL
  connection string của database gamefarm, password đã URL-encode. Pipeline
  tự đồng bộ Secret này xuống cluster. Không đưa giá trị vào Git hoặc log.
- URL đã cấu hình riêng được giữ khi GitHub Secret không được cung cấp. URL
  ở chế độ dùng chung được cập nhật theo host/credentials runtime mỗi lần deploy.
- Secret ký reward được sinh lần đầu, giữ nguyên ở các lần sau; Auth và Farm
  cùng nhận secret này. `FARM_REWARDS_ENABLED=true` bật consumer vì migration
  inbox Auth đã được thực hiện trước. Không xóa secret để chạy lại.
- Deployment được gắn revision của cấu hình để reload biến môi trường khi
  Secret thay đổi, kể cả deploy lại cùng image tag.

### Thao tác trên GitHub, không cần SSH

Nếu dùng cùng tài khoản Neon hiện tại: **không cần thêm biến hay secret**.
Nếu dùng tài khoản riêng: vào repository parent → Settings → Secrets and
variables → Actions (hoặc Environments → production) → thêm Secret
`FARM_DATABASE_URL` với connection string database `gamefarm`.

Push frontend trước nếu có thay đổi submodule, rồi push parent `main`.
Pipeline tự build Auth/Farm, sync cấu hình, tạo topic và rollout cả hai khi
diff chọn Farm. Để dùng lại image đã publish, vào Actions → **Build and deploy
production** → Run workflow, chọn branch `main`, nhập:

- `image_tag`: tag đã publish cho cả `bdc-backend` và `bdc-farm`.
- `services`: `auth-service,farm-service`.

Có thể thao tác tương đương từ máy cá nhân bằng GitHub CLI:

```bash
gh workflow run production.yml --ref main \
  -f image_tag=YOUR_PUBLISHED_TAG \
  -f services=auth-service,farm-service
gh run list --workflow production.yml --limit 3
gh run watch RUN_ID --exit-status
```

Đổi GitHub Secret không tự kích hoạt deployment: cần Run workflow như trên.
Frontend deploy theo pipeline submodule, dùng server env
`FARM_SERVICE_URL=http://farm-service:8087` khi cùng namespace (đã có trong
shared ConfigMap). Kiểm tra giao diện `/knowledge-farm`, thu hoạch đúng một
câu và chờ điểm Auth tăng 5. CI chờ readiness Farm; schema inbox Auth phải
đúng migration để consumer xử lý điểm thành công.

Kiểm tra sync bằng
`python3 -m unittest discover -s scripts/tests -p 'test_sync_farm_config.py'`.
Test bao gồm encode mật khẩu, giữ secret ký event, cập nhật credentials dùng
chung, URL riêng, chặn URL sai DB và không tạo Job/SQL khi sync cấu hình.

## Vận hành và khôi phục

- Theo dõi count/tuổi bản ghi `farm_outbox` chưa published, Kafka consumer lag,
  log `reward publication deferred`, lỗi consumer và probe database.
- Topic giữ 30 ngày theo manifest. Giữ bản ghi outbox published và inbox để
  audit/replay; chưa có job tự xóa. Lập kế hoạch retention/backup trước khi
  lưu lượng tăng; không xóa inbox nếu còn khả năng replay sự kiện tương ứng.
- Consumer retry vô hạn, kể cả sự kiện sai chữ ký/schema hoặc user thiếu.
  Partition sẽ dừng tại sự kiện lỗi, không âm thầm bỏ điểm. Điều tra và sửa
  cấu hình/user/producer; chỉ quyết định bỏ sự kiện dưới quy trình vận hành
  có audit. Dữ liệu inbox và score rollback cùng nhau khi user chưa tồn tại.
- Nếu mất Kafka sau khi outbox đã published: khôi phục broker hoặc replay
  **cùng event ID và payload đã ký** từ outbox; không tạo event ID mới.
- Xoay event secret phải phối hợp: dừng cấp reward, drain backlog, thay hai
  phía cùng lúc rồi tiếp tục. Một secret mới không xác minh được event cũ.
- Rollback code: tắt producer/consumer, giữ nguyên database, outbox, inbox,
  topic và điểm đã cộng. Không hoàn tác điểm bằng cách xóa receipt.
- Event chỉ có user ID, harvest ID, delta, thời gian, chữ ký; không có email,
  nội dung câu trả lời hoặc JWT. Topic không dùng cho Lakehouse mặc định.

## Kiểm thử

### Tương tác và năng lực phục vụ

Frontend giữ Phaser scene trong một khung hình; HUD/cửa hàng là React component
riêng. Đồng hồ câu hỏi chỉ render dialog, bắt côn trùng được cập nhật lạc quan
rồi đối chiếu lại với server, và scene chỉ dựng lại vật thể khi thuộc tính hiển
thị thay đổi. Game state tự đồng bộ mỗi 30 giây, thông tin điểm/LMS mỗi 60 giây;
tab ẩn ngừng polling và tab hiện lại sẽ tải ngay. Các thao tác ghi luôn tải lại
trạng thái sau phản hồi, nên không cần chờ lần polling kế tiếp.

Backend khóa một farm trong một transaction để tránh bán/thu hoạch trùng; các
farm khác nhau chạy song song. Outbox LMS được claim bằng `SKIP LOCKED` với
lease 30 giây, sau đó giải phóng kết nối DB trước khi gọi LMS. Reward Kafka
và LMS dùng ID ổn định để retry an toàn. Không tăng pool vô hạn: tổng số kết
nối của mọi replica phải nằm dưới giới hạn Neon, và số replica cần dựa trên
pool wait, API p95, thời gian transaction, backlog outbox và tỷ lệ lỗi.

Chưa có kết quả load test cho mức user đồng thời cụ thể. Chỉ đo tải trên môi
trường cô lập theo [runbook](../teams/DEVOPS_RUNBOOK.md), với tài khoản thử
nghiệm và giới hạn kết nối rõ ràng; sau khi có số đo, ưu tiên tách read
projection/cache cho `/game/state` vì hiện request đọc vẫn chạy tick trong
transaction ghi.

```bash
cd farm-service && go test -race ./...
# Từ repo root: PostgreSQL tạm, Go integration, toàn bộ mvn test bằng Java 21
bash scripts/test-knowledge-farm.sh
# Trong frontend:
npm run format:knowledge-farm:check
npm run lint
npx tsc --noEmit
node tests/knowledge-farm/bff.test.cjs
npm run build
```

Test integration bao gồm nhiều request cùng challenge, cross-user, lỗi broker,
replay outbox, contract chữ ký Go/Java, Java inbox trùng và rollback khi thiếu
user. Một test dùng broker Kafka thật và listener factory production để gửi
trùng 5 lần, xác nhận chỉ cộng +5. Script Docker chỉ dùng database tạm; không dùng credential ứng dụng.
Nguồn .env thật không được mount vào các container test.

### Verification recorded on 2026-10-17

- Go: 8 tests passed with PostgreSQL integration and race detection; `go vet`
  passed. HTTP auth/validation and cross-user challenge rejection covered.
- Java 21: `mvn test` passed 7 tests, including a real Kafka broker, concurrent
  duplicate delivery, canonical score increment and transactional rollback.
- Frontend: 5 BFF tests passed; TypeScript and production build passed.
  Follow-up fix converted browser smoke to ESM: full `pnpm lint` now reports
  0 errors / 431 existing warnings, including the smoke script.
- Browser smoke on the production build: quiz and recall harvest, desktop and
  mobile learner navigation, species learning cards, light/dark presentation,
  scroll reachability and no horizontal overflow/page errors. UI smoke uses
  synthetic session/API fixtures, not a production account.
- Both Compose variants, Kustomize rendering, shell syntax and diff whitespace
  checks passed. No production rollout or live-account test was performed.

The optional browser script is `frontend/tests/knowledge-farm/smoke.mjs`.
It requires a local production Next server on `FARM_SMOKE_URL`, a dedicated
`NEXTAUTH_SECRET` matching `FARM_SMOKE_SECRET`, and Playwright Chromium.
Screenshots are written only to `/tmp/knowledge-farm-*.png`. Never point it
at production or provide a production session secret.
