# BDC Hub · Kiến Trúc & Hướng Dẫn Vận Hành Virtual Labs Engine

> **Tài liệu Kỹ thuật chính thức (System Architecture & Operational Guide)**  
> **Áp dụng cho:** `lab-service` (Go/Gin), `frontend` (Next.js), PostgreSQL `lab_db`, và bộ Simulation Engine cho **Virtual STEM & Chemistry Labs**.

---

## 📌 1. Tổng quan Kiến trúc Virtual Labs

Hệ thống Virtual Labs của BDC Hub được thiết kế theo mô hình **Pluggable Multi-Domain Runtime Engine**, hỗ trợ cả bài lab lập trình (Code Sandbox/Docker/Kubernetes/Slurm) lẫn các lab thí nghiệm ảo tương tác trực tiếp trên trình duyệt (STEM 2.5D Simulation).

```
+-----------------------------------------------------------------------------------+
|                                  BDC Hub Frontend                                 |
|  +---------------------------+  +--------------------------+  +-----------------+ |
|  | Coding / Jupyter Sandbox  |  |  STEM Plant / Robot Stage|  | Chemistry 2.5D  | |
|  | (Monaco + Web Terminal)   |  |  (2.5D Physics Engine)   |  | Engine Stage    | |
|  +---------------------------+  +--------------------------+  +-----------------+ |
+---------------------------------------+-------------------------------------------+
                                        | HTTP / WebSocket
                                        v
+-----------------------------------------------------------------------------------+
|                             lab-service (Go / Gin API)                            |
|  - Lab Management & Publishing API                                                |
|  - Execution Runners (Local / K8s / Database / Simulation Spec)                    |
|  - Automated Grading & Submission Evaluator                                       |
+---------------------------------------+-------------------------------------------+
                                        | PostgreSQL
                                        v
+-----------------------------------------------------------------------------------+
|                             lab_db (PostgreSQL + JSONB)                           |
|  - labs (lab_type CHECK constraint)                                               |
|  - lab_versions (definition_snapshot JSONB)                                       |
|  - experiment_definitions (domain CHECK: PLANT, ROBOT, CHEMISTRY)                 |
+-----------------------------------------------------------------------------------+
```

### Các kiểu bài Lab được hỗ trợ (`supported_lab_types`)
| Kiểu Lab | Môi trường xử lý | Mô tả ngắn |
| :--- | :--- | :--- |
| `CODING` | Isolated Docker Container / Worker | Lab lập trình (Python, Go, Java, C++) có chấm tự động |
| `HPC` | Slurm Cluster | Lab tính toán hiệu năng cao |
| `JUPYTER` | JupyterHub Container | Notebook phân tích dữ liệu & AI |
| `DATABASE` | PostgreSQL / MySQL Isolated DB | Lab truy vấn CSDL SQL |
| `PLANT` | Browser-native 2.5D Canvas | Thí nghiệm sinh học / sinh trưởng cây trồng |
| `ROBOT` | Browser-native 2.5D Canvas | Thí nghiệm cơ học / điều khiển robot |
| **`CHEMISTRY`** | **Browser-native 2.5D Canvas & Hóa lý Engine** | **Thí nghiệm Hóa học ảo 2D/2.5D theo quy trình tính toán chuẩn** |

---

## 🧪 2. Chi Tiết Kiến Trúc Chemistry Virtual Labs (`CHEMISTRY`)

Lab Hóa học ảo được xây dựng với mục tiêu: **Không bao giờ hardcode kết quả hay đoán định**. Mọi hiện tượng (màu sắc, pH, nhiệt độ, khí, kết tủa) đều được tính toán tự động từ công thức Hóa lý thời gian thực.

```mermaid
graph TD
    A[Giảng viên] -->|Dùng No-Code Builder UI| B[ChemistryLabBuilder.tsx]
    B -->|Tạo Spec JSON| C[lab-service API]
    C -->|Lưu vào PostgreSQL| D[(lab_versions.definition_snapshot)]
    
    E[Học viên] -->|Mở Bài Lab Hóa| F[ChemistryCanvasStage.tsx]
    F -->|Đổ / Nhỏ hóa chất| G[ChemistryEngine.ts]
    
    subgraph Calculation Core
        G -->|1. Stoichiometry| H[Bảo toàn Số mol & Thể tích]
        G -->|2. Acid-Base Equilibrium| I[Tính pH & Đường cong Chuẩn độ]
        G -->|3. Indicator Engine| J[Nội suy màu sắc HSL/RGB]
        G -->|4. Thermochemistry| K[Nhiệt phản ứng Delta H -> Delta T]
        G -->|5. Phase Change| L[Khí sủi bọt & Kết tủa Ksp]
    end
    
    Calculation Core -->|Cập nhật Trạng thái Dung dịch| F
    F -->|Hiển thị Đồ thị pH| M[TitrationCurveWidget.tsx]
    F -->|Đánh giá Tiêu chí| N[Tự động Chấm điểm Submission]
```

---

### 📄 2.1 Cấu trúc Định dạng JSON Spec (`ChemistryLabSpec`)

Mọi bài lab hóa học được mô tả đầy đủ qua JSON Spec mà **giảng viên có thể tùy chỉnh 100% qua UI**:

```typescript
export interface ChemistryLabSpec {
  labType: "CHEMISTRY";
  title: string;
  description?: string;
  workspace: {
    viewMode: "2D" | "2.5D";
    benchWidth: number;
    benchHeight: number;
  };
  substances: Substance[];       // Danh mục hóa chất & chỉ thị màu
  equipments: EquipmentItem[];   // Dụng cụ trên bàn thí nghiệm
  reactions: ReactionRule[];     // Quy tắc phản ứng hóa học
  evaluationCriteria: EvaluationStep[]; // Các bước tiêu chí chấm điểm
}
```

#### Chi tiết trường dữ liệu chính:
1. **`Substance` (Hóa chất & Dung dịch):**
   - `id`, `name`, `formula` (Công thức hóa học, ví dụ `HCl`, `NaOH`, `Phenolphthalein`).
   - `state`: `"liquid"` | `"solid"` | `"gas"` | `"indicator"`.
   - `concentrationM`: Nồng độ mol ($C_M$).
   - `initialPh`: Giá trị pH ban đầu của hóa chất nguyên chất.
   - `indicatorRanges`: Dải đổi màu chỉ thị theo pH (ví dụ: Phenolphthalein từ pH $0 \to 8.2$ trong suốt, $8.2 \to 10.0$ màu hồng nhạt $\text{RGBA}(255, 105, 180, 0.7)$).

2. **`EquipmentItem` (Dụng cụ thủy tinh & Đo lường):**
   - `type`: `"burette"` | `"erlenmeyer_flask"` | `"beaker"` | `"dropper"` | `"ph_meter"` | `"thermometer"`.
   - `capacityMl`: Dung tích tối đa (mL).
   - `initialVolumeMl`: Thể tích hóa chất nạp sẵn ban đầu.
   - `filledSubstanceId`: ID hóa chất được nạp sẵn.
   - `x`, `y`: Tọa độ vị trí trên bàn thí nghiệm 2.5D.

3. **`ReactionRule` (Quy tắc Phản ứng Hóa học):**
   - `equation`: Phương trình hóa học (ví dụ: `HCl + NaOH -> NaCl + H2O`).
   - `reactants`: Mảng chất tham gia & hệ số tỉ lượng ($aA + bB$).
   - `products`: Mảng sản phẩm & hệ số tỉ lượng ($cC + dD$).
   - `heatOfReactionKjPerMol`: Nhiệt phản ứng $\Delta H$ (Âm: Tỏa nhiệt, Dương: Thu nhiệt).
   - `precipitateSubstanceId`: ID chất kết tủa nếu có.
   - `gasSubstanceId`: ID chất khí bay ra nếu có.

4. **`EvaluationStep` (Tiêu chí Chấm điểm Tự động):**
   - `targetEquipmentId`: Dụng cụ mục tiêu cần kiểm tra (ví dụ: bình tam giác `flask_1`).
   - `targetPhMin`, `targetPhMax`: Khoảng pH cần đạt tại điểm tương đương (ví dụ: $8.2 \to 9.5$).
   - `targetVolumeDispensedMl`, `toleranceMl`: Thể tích chuẩn độ mục tiêu (ví dụ: $25.0 \pm 0.3 \text{ mL}$).

---

### 🧮 2.2 Thuật toán Tính toán Hóa lý thời gian thực (`ChemistryEngine.ts`)

#### A. Cân bằng Tỉ lượng & Tự động Tiêu thụ Chất tham gia
Khi nhỏ một thể tích $\Delta V$ hóa chất $B$ vào dụng cụ chứa hóa chất $A$:
$$\Delta n_B = C_B \cdot \Delta V$$
Hệ thống tự động tìm phản ứng phù hợp và xác định mức độ phản ứng tối đa:
$$\xi = \min\left(\frac{n_A}{a}, \frac{n_B}{b}\right)$$
- Số mol còn lại của chất tham gia: $n_{A, final} = n_A - a\xi, \quad n_{B, final} = n_B - b\xi$
- Số mol sản phẩm tạo thành: $n_C = n_{C, init} + c\xi, \quad n_D = n_{D, init} + d\xi$
- Thể tích tổng mới: $V_{\text{total}} = V_{\text{cũ}} + \Delta V$

#### B. Thuật toán Tính pH
- **Pha trộn Acid mạnh ($\text{H}^+$) và Bazo mạnh ($\text{OH}^-$):**
  $$\Delta n = n_{\text{H}^+} - n_{\text{OH}^-}$$
  - Nếu $\Delta n > 0$ (Dư Acid): $[\text{H}^+] = \frac{\Delta n}{V_{\text{total}}} \implies \text{pH} = -\log_{10}[\text{H}^+]$
  - Nếu $\Delta n < 0$ (Dư Bazo): $[\text{OH}^-] = \frac{-\Delta n}{V_{\text{total}}} \implies \text{pOH} = -\log_{10}[\text{OH}^-] \implies \text{pH} = 14.0 - \text{pOH}$
  - Nếu $\Delta n = 0$ (Trung hòa hoàn toàn): $\text{pH} = 7.0$

#### C. Thuật toán Nội suy Màu sắc Dung dịch (Color Interpolation)
Nếu trong dung dịch có chứa chất chỉ thị (Indicator):
Hệ thống lấy dải `indicatorRanges` và tính toán màu dung dịch thời gian thực theo công thức HSL/RGB:
$$\text{Color}_{\text{active}} = \text{Interpolate}(\text{Range}_{\text{lower}}, \text{Range}_{\text{upper}}, \text{pH})$$

#### D. Thuật toán Nhiệt Hóa học & Hiện tượng Vật lý
- **Nhiệt độ dung dịch:**
  $$Q = -\Delta H \cdot \xi \implies \Delta T = \frac{Q}{m_{\text{dung dịch}} \cdot c_{\text{nước}}} \quad (c_{\text{nước}} = 4.184 \text{ J/g}\cdot^\circ\text{C})$$
- **Thể tích khí thoát ra (STP):**
  $$V_{\text{khí}} = n_{\text{khí}} \cdot 24.79 \text{ Lít}$$
- **Kết tủa & Độ đục:**
  $$m_{\text{kết tủa}} = n_{\text{kết tủa}} \cdot M_{\text{molar}}$$

---

### 🎨 2.3 Sân khấu 2.5D Tương tác (`ChemistryCanvasStage.tsx`)

- **Burette Controller:**
  - Van buret xoay góc $90^\circ$ khi mở.
  - Tốc độ nhỏ giọt điều chỉnh từ $1 \to 20 \text{ giọt/giây}$.
  - Hạt giọt nước (drip particle) rơi với animation vật lý.
- **Dụng cụ Thủy tinh (Glassware Graphics):**
  - Hiệu ứng khúc xạ ánh sáng trên thành thủy tinh (specular highlights).
  - Mặt cong dung dịch (meniscus) dâng/hạ động theo thể tích.
- **Đồ thị Chuẩn độ pH thời gian thực (`TitrationCurveWidget.tsx`):**
  - Cập nhật từng điểm dữ liệu $(V_{\text{nhỏ}}, \text{pH})$ lên SVG Graph.
  - Hiển thị đường gióng mốc tương đương ($V_{\text{eq}} = 25.0 \text{ mL}$).

---

### 🛠️ 2.4 Bộ công cụ No-Code cho Giảng viên (`ChemistryLabBuilder.tsx`)

Giảng viên truy cập giao diện thiết lập bài Lab mà **không cần viết code**:
1. **Khai báo Hóa chất:** Chọn nồng độ $C_M$, pH ban đầu, chọn màu sắc/chỉ thị.
2. **Khai báo Dụng cụ:** Chọn Buret/Bình tam giác/Cốc, chọn hóa chất nạp sẵn.
3. **Khai báo Phản ứng:** Nhập phương trình hóa học, hệ số tỉ lượng và nhiệt tỏa ra.
4. **Tiêu chuẩn Chấm điểm:** Nhập thể tích mốc (ví dụ: $25.0 \text{ mL}$) và dải pH đạt điểm tối đa.

---

## 🗄️ 3. Quản lý Cơ sở Dữ liệu & Migration (`lab_db`)

### File Migration `V004__chemistry_lab_support.sql`
Mở rộng các ràng buộc kiểm tra SQL (`CHECK` constraint) để chấp nhận kiểu bài lab `CHEMISTRY`:

```sql
-- 1. Mở rộng ràng buộc bảng labs
ALTER TABLE labs DROP CONSTRAINT IF EXISTS labs_lab_type_check;
ALTER TABLE labs ADD CONSTRAINT labs_lab_type_check CHECK (lab_type IN (
    'CODING', 'HPC', 'JUPYTER', 'WORKSPACE', 'DATABASE', 'CUSTOM',
    'PLANT', 'ROBOT', 'CHEMISTRY'
));

-- 2. Mở rộng ràng buộc bảng experiment_definitions
ALTER TABLE experiment_definitions DROP CONSTRAINT IF EXISTS experiment_definitions_domain_check;
ALTER TABLE experiment_definitions ADD CONSTRAINT experiment_definitions_domain_check CHECK (domain IN (
    'PLANT', 'ROBOT', 'CHEMISTRY'
));
```

### Lưu trữ dữ liệu JSONB
Toàn bộ Spec của bài Lab Hóa học được đóng gói dạng JSON và lưu trữ vào cột `definition_snapshot` (dạng `JSONB`) của bảng `lab_versions`. Điều này giúp:
- **Tốc độ truy vấn cực nhanh:** Truy xuất toàn bộ bài lab chỉ trong 1 câu SQL `SELECT`.
- **An toàn tuyệt đối:** Không làm thay đổi cấu trúc bảng CSDL hiện có.

---

## 📁 4. Danh Sách File Code Đã Triển Khai

| Path File | Vai trò / Chức năng |
| :--- | :--- |
| [`frontend/src/types/chemistry.ts`](file:///home/phucnhan/codespace/bdc/CoreApplication/frontend/src/types/chemistry.ts) | Định nghĩa các TypeScript Data Types & Interfaces cho Hóa học |
| [`frontend/src/services/chemistryEngine.ts`](file:///home/phucnhan/codespace/bdc/CoreApplication/frontend/src/services/chemistryEngine.ts) | Engine tính toán Hóa lý chuẩn xác (Bảo toàn khối lượng, pH, Nhiệt, Chỉ thị màu) |
| [`frontend/src/components/labs/chemistry/TitrationCurveWidget.tsx`](file:///home/phucnhan/codespace/bdc/CoreApplication/frontend/src/components/labs/chemistry/TitrationCurveWidget.tsx) | Widget vẽ đồ thị chuẩn độ pH thời gian thực |
| [`frontend/src/components/labs/chemistry/ChemistryCanvasStage.tsx`](file:///home/phucnhan/codespace/bdc/CoreApplication/frontend/src/components/labs/chemistry/ChemistryCanvasStage.tsx) | Component Sân khấu Thí nghiệm Hóa 2.5D tương tác (buret, bình tam giác, van nhỏ giọt) |
| [`frontend/src/components/labs/chemistry/ChemistryLabBuilder.tsx`](file:///home/phucnhan/codespace/bdc/CoreApplication/frontend/src/components/labs/chemistry/ChemistryLabBuilder.tsx) | Bộ công cụ No-Code Builder cho Giảng viên tự cấu hình bài Lab |
| [`lab-service/migrations/V004__chemistry_lab_support.sql`](file:///home/phucnhan/codespace/bdc/CoreApplication/lab-service/migrations/V004__chemistry_lab_support.sql) | Script Migration CSDL Postgres bổ sung kiểu `CHEMISTRY` |
