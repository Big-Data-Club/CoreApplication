# BDC Hub - Kubernetes & K3s Operations Cheatsheet

Tài liệu tổng hợp các câu lệnh cần thiết để vận hành, kiểm tra, quản lý tài nguyên và xử lý sự cố trên K3s / Kubernetes Cluster cho dự án BDC Hub.

---

## 1. Quản lý Dịch vụ K3s (Systemd Service)

K3s chạy dưới dạng một `systemd` service trên Linux VM.

| Thao tác | Lệnh thực thi |
|---|---|
| Kiểm tra trạng thái K3s | `sudo systemctl status k3s` |
| Khởi động lại K3s | `sudo systemctl restart k3s` |
| Tắt K3s service | `sudo systemctl stop k3s` |
| Xem log khởi động K3s | `sudo journalctl -u k3s -f --no-pager` |
| Kiểm tra phiên bản K3s | `k3s --version` / `kubectl version` |

> [!NOTE]
> File cấu hình mặc định của K3s kubeconfig nằm tại `/etc/rancher/k3s/k3s.yaml`. Người dùng trong group `docker` hoặc có quyền `sudo` có thể tương tác với `kubectl`.

---

## 2. Quản lý Pods, Deployments & Workloads

### 2.1. Kiểm tra trạng thái & Tài nguyên (Inspection & Metrics)

```bash
# Xem danh sách tất cả Pods (kèm IP và Node đang chạy)
kubectl get pods -o wide

# Xem danh sách Pods trên tất cả Namespaces (bao gồm kube-system)
kubectl get pods -A

# Kiểm tra mức tiêu thụ CPU / RAM của các Node
kubectl top nodes

# Kiểm tra mức tiêu thụ CPU / RAM của từng Pod (sắp xếp theo RAM giảm dần)
kubectl top pods --sort-by=memory

# Kiểm tra mức tiêu thụ CPU / RAM của từng Pod (sắp xếp theo CPU giảm dần)
kubectl top pods --sort-by=cpu
```

### 2.2. Đọc Log & Debugging Pods

```bash
# Xem log thời gian thực (live tail) của Pod
kubectl logs -f <pod_name>

# Xem log của Container cụ thể trong Pod (nếu Pod có nhiều container)
kubectl logs -f <pod_name> -c <container_name>

# [RẤT QUAN TRỌNG] Xem log của Pod BỊ CHẾT TRƯỚC ĐÓ (ví dụ OOMKilled / CrashLoop)
kubectl logs <pod_name> --previous

# Kiểm tra chi tiết trạng thái Pod, lý do restart, lỗi OOMKilled hoặc Events
kubectl describe pod <pod_name>

# Truy cập trực tiếp vào Shell của Pod đang chạy (bắt bệnh bên trong container)
kubectl exec -it <pod_name> -- /bin/sh
```

### 2.3. Quản lý & Cập nhật Deployments

```bash
# Khởi động lại (Restart) một Deployment (Reload lại Pod mới)
kubectl rollout restart deployment <deployment_name>
# Ví dụ: kubectl rollout restart deployment ai-worker

# Kiểm tra tiến trình Rollout restart
kubectl rollout status deployment <deployment_name>

# Điều chỉnh số lượng Replicas (Scale up / Scale down)
kubectl scale deployment <deployment_name> --replicas=<number>
# Ví dụ: kubectl scale deployment ai-worker --replicas=1

# Tăng/giảm trực tiếp RAM / CPU Limits của Deployment (Apply tức thì)
kubectl set resources deployment <deployment_name> \
  --limits=memory=4Gi,cpu=2500m \
  --requests=memory=2.5Gi,cpu=1000m
```

---

## 3. Quản lý Configuration & Secrets

### 3.1. Secrets (`bdc-secrets`)

```bash
# Xem danh sách Secrets
kubectl get secrets

# Xem chi tiết cấu hình Base64 của bdc-secrets
kubectl get secret bdc-secrets -o yaml

# Giải mã (Decode) một key trong Secret từ Base64
echo -n "<encoded_base64_string>" | base64 -d

# Cập nhật / Patch trực tiếp một key Secret trên Cluster mà không cần apply file
kubectl patch secret bdc-secrets --type=json -p='[{"op": "add", "path": "/data/<KEY_NAME>", "value": "<BASE64_VALUE>"}]'

# Tạo Fernet Encryption Key mới và patch vào Secret AI_KEY_ENCRYPTION_SECRET
KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
kubectl patch secret bdc-secrets --type=json -p="[{\"op\": \"add\", \"path\": \"/data/AI_KEY_ENCRYPTION_SECRET\", \"value\": \"$(echo -n $KEY | base64 -w0)\"}]"
```

### 3.2. ConfigMaps (`bdc-config`)

```bash
# Xem chi tiết ConfigMap đang áp dụng
kubectl get configmap bdc-config -o yaml

# Apply lại ConfigMap sau khi chỉnh sửa trong file repository
kubectl apply -f k3s/base/configmap.yaml
```

---

## 4. Dọn dẹp & Tối ưu Dung lượng Ổ đĩa (Disk Cleanup)

Khi ổ đĩa server bị đầy (`df -h /` > 80%), thực hiện quy trình dọn dẹp sau:

### 4.1. Chẩn đoán dung lượng ổ đĩa

```bash
# Kiểm tra tổng quan dung lượng ổ đĩa
df -h /

# Kiểm tra dung lượng các thư mục chính
sudo du -sh /var /home /tmp /usr /root 2>/dev/null | sort -h

# Kiểm tra dung lượng các ổ đĩa ảo PVC (Postgres, Qdrant, Neo4j, MinIO cache)
sudo du -sh /var/lib/rancher/k3s/storage/* 2>/dev/null | sort -h
```

### 4.2. Các lệnh dọn dẹp an toàn (Giải phóng 5GB - 15GB)

```bash
# 1. Dọn dẹp Container Images rác/cũ của K3s (containerd)
sudo k3s crictl rmi --prune

# 2. Xóa log hệ thống cũ (thu gọn journalctl log về tối đa 100MB)
sudo journalctl --vacuum-size=100M
sudo journalctl --vacuum-time=3d

# 3. Dọn dẹp bộ nhớ đệm gói cài đặt APT
sudo apt-get clean && sudo apt-get autoremove -y

# 4. Xóa thư mục rác Docker cũ (nếu từng cài Docker và hiện đã bị bỏ)
sudo rm -rf /var/lib/docker

# 5. Dọn dẹp thư mục tạm /tmp
sudo rm -rf /tmp/*
```

---

## 5. Xử lý sự cố thường gặp (Troubleshooting Playbook)

### 🚨 Case 1: Pod bị `OOMKilled` (Exit Code 137)
- **Dấu hiệu**: Pod restart liên tục (`RESTARTS > 0`), trạng thái `Running` nhưng bị crash giữa chừng.
- **Kiểm tra**:
  ```bash
  kubectl describe pod <pod_name> | grep -A 5 "Last State"
  ```
  Nếu thấy `Reason: OOMKilled` và `Exit Code: 137` -> Pod bị hạ do hết RAM.
- **Xử lý**:
  Tăng `limits.memory` trong file `k3s/base/<service>-deployment.yaml` hoặc chạy lệnh patch RAM trực tiếp:
  ```bash
  kubectl set resources deployment <service_name> --limits=memory=4Gi --requests=memory=2.5Gi
  ```

### 🚨 Case 2: Pod bị `CrashLoopBackOff`
- **Dấu hiệu**: Pod khởi động lên bị ngắt ngay lập tức và K8s thử khởi động lại theo lũy thừa thời gian.
- **Kiểm tra**:
  ```bash
  # Đọc log lỗi trước khi crash
  kubectl logs <pod_name> --previous
  
  # Xem lý do thất bại trong Events
  kubectl describe pod <pod_name>
  ```
- **Nguyên nhân phổ biến**: Thiếu Secret/Biến môi trường, sai cấu hình DB connection, hoặc DB chưa sẵn sàng.

### 🚨 Case 3: Pod bị `ImagePullBackOff` hoặc `ErrImagePull`
- **Kiểm tra**:
  ```bash
  kubectl describe pod <pod_name> | grep -A 10 "Events:"
  ```
- **Nguyên nhân**: Sai tên Docker image, tag image không tồn tại trên Docker Hub (`phucnhan2809/bdc-...`), hoặc lỗi mạng không pull được ảnh.

### 🚨 Case 4: Pod ở trạng thái `Pending`
- **Kiểm tra**: `kubectl describe pod <pod_name>`
- **Nguyên nhân**:
  1. Node hết CPU/RAM khả dụng để cấp phát theo `requests`.
  2. Unbound PVC (Persistent Volume Claim chưa được gán thành công).

---

## 6. Tổng hợp Lệnh 1-Liner Hữu ích (Quick One-Liners)

```bash
# Xem log của tất cả Pods thuộc app ai-worker
kubectl logs -l app=ai-worker --tail=100 -f

# Tìm tất cả Pods đang không ở trạng thái Running
kubectl get pods -A | grep -v "Running" | grep -v "Completed"

# Sắp xếp danh sách Pods theo số lần Restarts (nhiều nhất lên đầu)
kubectl get pods --sort-by='.status.containerStatuses[0].restartCount'

# Apply toàn bộ k3s base manifests
kubectl apply -k k3s/base/

# Apply overlay Serverless k3s
kubectl apply -k k3s/overlays/serverless/
```
