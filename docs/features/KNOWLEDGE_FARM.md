# Nông trại kiến thức

Owner: Farm / Auth / Frontend maintainers. Implementation: `farm-service/`,
`auth-and-management-service/src/main/java/com/example/demo/service/farm/`,
`frontend/src/features/knowledge-farm/`.

## Phạm vi hiện tại

Game học tập tại `/knowledge-farm`, có mục trên sidebar. Sáu ô khởi đầu gồm
lúa, rau muống, hoa vạn thọ, gà mái, cá nước ngọt và ong mật. Sprite và ý tưởng
chọn ô/chăm sóc/nghỉ sau thu hoạch được chuyển từ source XanhMarket VuiVe do
người dùng cung cấp. Không có broker, đơn hàng, giao dịch, camera, IoT hoặc
kết nối nông trại thật. UI dùng React grid và sprite, không tải Phaser.

Mỗi loại có thông tin môi trường, quy trình chăm sóc thực tế, điều thú vị và
liên kết nguồn trong `farm-service/internal/farm/catalog.json`. Đây là kiến
thức nhập môn; đồng hồ game, một nút chăm sóc và tái sinh 40 giây không mô
phỏng đầy đủ quy trình sinh học thực tế.

1. Chọn ô, đọc thẻ kiến thức và chăm sóc miễn phí.
2. Server lưu thời điểm có thể thu hoạch; tải lại trang không làm mất tiến độ.
3. Khi sẵn sàng, chọn quiz hoặc flashcard nhập đáp án. Một challenge có hiệu
   lực 10 phút; mở lại không đổi câu đang còn hiệu lực.
4. Đáp án đúng mới thu hoạch. Sai thì giữ nguyên sản phẩm, hiển thị giải thích,
   khóa thử lại 30 giây và phát câu mới. Flashcard chấm sau chuẩn hóa Unicode,
   hoa/thường và khoảng trắng; không phải tự đánh dấu “đã nhớ”.
5. Đúng nhận 5 điểm, tối đa 100 điểm mỗi ngày UTC (đặt lại 07:00 Việt Nam).
   Đạt trần vẫn học và thu hoạch được nhưng không thêm điểm. Sau thu hoạch,
   ô nghỉ 40 giây, rồi cần chăm lại để bắt đầu lượt tiếp theo.

Ngân hàng 24 câu nền tảng (tin học/dữ liệu và kiến thức nông trại), được quản
lý ở server, không gọi AI theo lượt chơi. Câu thuộc loài khác không được chọn.
Hiện **chưa lấy câu từ khóa học LMS hoặc bộ flashcard cá nhân**; không ghi
điểm vào LMS và không tuyên bố đây là tiến độ hoàn thành khóa học. Mở rộng
ngân hàng bằng thay đổi versioned JSON và review nội dung; câu đang mở giữ
snapshot để không đổi đáp án khi deploy.

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
Answer trả `{correct,explanation,awarded,event_id?}`. Không trả đáp án hay giải
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

Production deploy tự gọi `scripts/bootstrap-knowledge-farm.py` trước rollout khi
chọn Farm. Không cần SSH chỉnh `.env` hay thêm mật khẩu Farm vào GitHub:

1. Đọc endpoint Auth đang dùng từ `bdc-config` và credentials trong
   `bdc-secrets`. Với Neon, Job dùng endpoint trực tiếp bỏ hậu tố `-pooler`;
   ứng dụng vẫn dùng host hiện có. Database mới tên **`gamefarm`**, cùng Neon
   project/branch/compute với Auth, không phải một project Neon khác.
2. Tạo role SQL riêng `gamefarm_app` và database nếu chưa có. Mật khẩu ngẫu
   nhiên và secret ký event được lưu trong `bdc-farm-secrets`, giữ nguyên khi
   retry. App Farm chỉ nhận credentials của role riêng, không nhận tài khoản
   quản trị Auth. Bootstrap là tác vụ quản trị triển khai, không phải API runtime.
3. Job PostgreSQL chạy migration inbox trong database Auth; sau đó đăng nhập
   bằng role Farm và chạy `farm-service/migrations/V*.sql` trong `gamefarm`.
   Mỗi database có ledger `farm_deploy_migrations`, checksum, transaction và
   advisory lock. Migration đã áp dụng không chạy lại; checksum khác thì dừng.
   Thêm file V002, V003... cho thay đổi tiếp theo, không sửa V001.
4. Chỉ sau khi hai schema sẵn sàng mới đặt `FARM_REWARDS_ENABLED=true`, tạo
   topic Kafka, rồi rollout Auth và Farm. Selector tự build cả hai khi mã Farm
   hoặc bootstrap thay đổi. Frontend vẫn build/deploy qua workflow submodule.

Điều kiện ban đầu: cluster đã có `bdc-config`, `bdc-secrets`, Kafka; tài khoản
DB trong `bdc-secrets` có quyền quản lý role/database và migrate schema Auth.
Role mặc định Neon (`neondb_owner`, thành viên `neon_superuser`) có quyền
CREATEDB/CREATEROLE; xem [Neon roles](https://neon.com/docs/manage/roles).
Nếu tài khoản hiện tại đã bị giới hạn, quản trị viên phải provision quyền/tài
khoản qua kho secret được duyệt trước; CI không tự nâng quyền. Database đã có
owner khác hoặc URL Farm trỏ database/host khác sẽ bị từ chối, không tự di
chuyển dữ liệu. Không xóa `bdc-farm-secrets` để retry vì có event đang dùng
secret cũ. Nếu bootstrap lỗi, log chỉ báo giai đoạn, không in SQL/password.

### Chạy CI/CD

Push **frontend trước**, sau đó push parent `main` với submodule pointer mới.
Parent workflow tự build/test/bootstrap/rollout khi diff chọn Farm. Không coi
workflow xanh không chọn service là đã deploy. Chạy lại image đã build bằng
GitHub CLI từ repo parent (thay tag bằng SHA/tag đã tồn tại cho cả hai image):

```bash
gh workflow run production.yml --ref main \
  -f image_tag=YOUR_PUBLISHED_TAG \
  -f services=auth-service,farm-service
gh run list --workflow production.yml --limit 3
# Dùng ID vừa hiển thị:
gh run watch RUN_ID --exit-status
```

### Chạy end-to-end trên server khi cần

Dùng checkout đúng release và kubeconfig có quyền quản trị namespace. Không
cần copy mật khẩu từ Neon ra terminal. Hai image `bdc-backend` và `bdc-farm`
phải đã được CI publish cùng tag; lệnh này không build image trên server.

```bash
cd /path/to/CoreApplication
git pull --ff-only origin main
export KUBECONFIG=/path/to/authorized/kubeconfig
export DEPLOY_NAMESPACE=default
export REGISTRY_NAMESPACE=YOUR_DOCKERHUB_NAMESPACE
export IMAGE_TAG=YOUR_PUBLISHED_TAG
export SERVICES=auth-service,farm-service
bash scripts/deploy-production.sh
kubectl -n "$DEPLOY_NAMESPACE" rollout status deployment/auth-service --timeout=12m
kubectl -n "$DEPLOY_NAMESPACE" rollout status deployment/farm-service --timeout=12m
kubectl -n "$DEPLOY_NAMESPACE" wait --for=condition=complete job/farm-reward-topic-v1 --timeout=180s
kubectl -n "$DEPLOY_NAMESPACE" port-forward service/farm-service 8087:8087
```

Ở terminal thứ hai, `curl --fail http://127.0.0.1:8087/ready`. Deploy frontend
qua pipeline riêng với server env `FARM_SERVICE_URL=http://farm-service:8087`
(khi frontend trong cùng namespace). Đăng nhập bằng tài khoản thử, mở
`/knowledge-farm`, chăm sóc → chờ trưởng thành → trả lời đúng → thu hoạch.
Kiểm tra tổng điểm tăng đúng 5 sau khi consumer xử lý; kiểm tra log Auth/Farm
và consumer lag nếu điểm chưa về. Không dùng browser smoke mock để chứng minh
kết nối production.

Deploy script dùng DB operation lock hiện có và dừng trước rollout nếu
bootstrap lỗi. Job lỗi được giữ tối đa một giờ, tên Job có trong CI log;
`kubectl logs -n default job/FARM_BOOTSTRAP_JOB_NAME` cho biết giai đoạn lỗi.
ConfigMap SQL của Job lỗi không chứa secret; xóa bằng
`kubectl delete configmap -n default FARM_BOOTSTRAP_JOB_NAME` sau điều tra.
Database/migrations đã commit không bị rollback khi image rollout thất bại.
Base Kustomize không tự chạy script: dùng deploy script/pipeline cho lần đầu.

Kiểm tra bootstrap độc lập bằng `bash scripts/test-farm-bootstrap.sh`: 7 unit
checks và PostgreSQL tạm kiểm tra provision, retry, role không phải superuser,
và từ chối checksum sai. Test không kết nối Neon production.

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

```bash
cd farm-service && go test -race ./...
# Từ repo root: PostgreSQL tạm, Go integration, toàn bộ mvn test bằng Java 21
bash scripts/test-knowledge-farm.sh
# Trong frontend:
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
