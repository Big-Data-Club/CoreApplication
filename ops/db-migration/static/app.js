const byId = (id) => document.getElementById(id);
const phases = {queued: 'Đã tạo Job', preflight: 'Kiểm tra điều kiện chuyển', preparing: 'Chép cấu trúc database',
  replicating: 'Chép dữ liệu và đồng bộ thay đổi', quiescing: 'Tạm dừng các service ghi DB',
  draining: 'Chờ thay đổi cuối cùng và đồng bộ sequence', cutover: 'Cập nhật kết nối DB',
  rolling_out: 'Khởi động và kiểm tra service', succeeded: 'Đã chuyển DB thành công',
  failed_source_active: 'Chuyển thất bại — hệ thống dùng DB nguồn', recovery_required: 'Cần người vận hành phục hồi'};
let pending = false;
let selectedProfiles = [];
async function api(path, options) {
  const response = await fetch(`api/${path}`, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không đọc được trạng thái');
  return data;
}
async function refresh() {
  try {
    const s = await api('status');
    byId('phase').textContent = phases[s.phase] || 'Chưa có lượt chuyển';
    byId('progress').textContent = s.tables_total ? `${s.tables_ready}/${s.tables_total} bảng đã chép · Chênh lệch WAL: ${s.lag_bytes ?? '…'} byte` : '';
    byId('details').textContent = s.job ? `Job: ${s.job} · Cập nhật: ${s.updated_at}` : '';
    if (s.error) byId('error').textContent = `${s.error}${s.sqlstate ? ` (SQLSTATE ${s.sqlstate})` : ''}`;
    const terminal = ['succeeded', 'failed_source_active'].includes(s.phase);
    byId('recovery').textContent = s.phase === 'recovery_required' || (s.job_failed && !terminal)
      ? 'Job đã dừng và giữ khóa chuyển DB. Kiểm tra K3s và hướng dẫn phục hồi trước khi tiếp tục.' : '';
    byId('start').disabled = pending || !selectedProfiles.length || (!!s.phase && !terminal);
  } catch (error) { byId('error').textContent = error.message; byId('start').disabled = true; }
}
byId('start').addEventListener('click', async () => {
  pending = true;
  byId('start').disabled = true;
  byId('error').textContent = '';
  // Preserve the request ID after ambiguous network errors; reload/retry cannot
  // create a second Job for the same click.
  const profile = byId('profile').value;
  const key = `db-migration-request:${profile}`;
  const requestId = sessionStorage.getItem(key) || crypto.randomUUID();
  sessionStorage.setItem(key, requestId);
  try {
    await api('runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({profile, request_id: requestId})});
    sessionStorage.removeItem(key);
  } catch (error) { byId('error').textContent = error.message; }
  pending = false;
  await refresh();
});
(async () => {
  try {
    selectedProfiles = await api('profiles');
    for (const profile of selectedProfiles) {
      const option = document.createElement('option'); option.value = profile.id; option.textContent = profile.label;
      byId('profile').appendChild(option);
    }
    byId('profile').disabled = !selectedProfiles.length;
    byId('profile-note').textContent = selectedProfiles.length ? 'Kết nối nguồn và đích được lưu trong Kubernetes Secret.' : 'Chưa có luồng chuyển được bật. Người vận hành cần cấu hình nguồn, đích và danh sách service.';
    await refresh();
    setInterval(refresh, 4000);
  } catch (error) { byId('error').textContent = error.message; }
})();
