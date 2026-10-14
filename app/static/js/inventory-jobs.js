(() => {
  const panel = document.getElementById('inventory-progress');
  if (!panel) return;
  const labels = {full_scan: 'Check All', payment_scan: 'Kiểm tra thanh toán', missing_plans: 'Cập nhật gói còn thiếu', duplicates: 'Lọc trùng', import: 'Kiểm tra & nhập kho', cleanup: 'Recheck & dọn tài khoản lỗi'};
  const results = {LIVE:'Hoạt động', DIE:'Cần kiểm tra', UNKNOWN:'Chưa xác định', ERROR:'Lỗi xử lý', MISSING:'Không còn tài khoản', CHANGED:'Thông tin đã thay đổi', KEPT:'Giữ lại', DELETED:'Đã xóa', PROTECTED:'Giữ tài khoản còn code'};
  let selected = null, timer = null;
  let generation = 0;
  function node(tag, value) { const el=document.createElement(tag); el.textContent=value; return el; }
  async function refresh() {
    clearTimeout(timer);
    const currentGeneration = generation;
    try {
      const response = await fetch('/admin/jobs/progress' + (selected ? '?id='+encodeURIComponent(selected) : ''), {cache:'no-store'});
      if (!response.ok || response.redirected) throw new Error('unavailable');
      const data = await response.json();
      if (currentGeneration !== generation) return;
      if (!data.run) { document.getElementById('job-status').textContent='Chưa có tác vụ. Chọn Check All để bắt đầu.'; return; }
      const run=data.run, active=run.status==='running';
      if(run.kind==='import') {
        document.getElementById('scanProgressArea').style.display='block';
        document.getElementById('scanStatusText').textContent=active?'Đang kiểm tra & nhập kho trên máy chủ':'Đã hoàn tất kiểm tra & nhập kho';
        document.getElementById('scanCountText').textContent=data.processed+' / '+run.total;
        document.getElementById('scanProgressBar').style.width=(run.total ? Math.min(100,100*data.processed/run.total) : 100)+'%';
        document.getElementById('scanLiveCount').textContent=data.counts.LIVE||0;
        document.getElementById('scanDieCount').textContent=data.counts.DIE||0;
        document.getElementById('scanErrorCount').textContent=(data.counts.UNKNOWN||0)+(data.counts.ERROR||0);
        document.getElementById('scanActionArea').style.display=active?'none':'block';
      }
      document.getElementById('job-status').textContent=(labels[run.kind]||run.kind)+' — '+(active?'Đang chạy':'Đã hoàn tất')+' · '+data.processed+'/'+run.total+' tài khoản';
      const bar=document.getElementById('job-progress'); bar.max=Math.max(1,run.total); bar.value=run.total ? data.processed : 1;
      document.getElementById('job-message').textContent=active ? 'Đang kiểm tra: '+(data.processing.join(', ')||'Chờ nhận việc. Tác vụ tiếp tục sau khi tải lại trang.') : 'Kết quả đã lưu. Tải lại bảng kho để xem số liệu mới.';
      document.getElementById('job-counts').textContent=Object.entries(data.counts).map(([k,v])=>(results[k]||k)+': '+v).join(' · ');
      const rows=document.getElementById('job-results'); rows.replaceChildren();
      data.recent.forEach(item=> { const tr=document.createElement('tr'); tr.append(node('td',item.email),node('td',results[item.result]||item.result),node('td',item.plan||'Giữ gói hiện tại')); rows.append(tr); });
      const history=document.getElementById('job-history'); history.replaceChildren();
      data.history.forEach(item=> { const button=node('button',(labels[item.kind]||item.kind)+' · '+item.total+' · '+(item.status==='running'?'Đang chạy':'Hoàn tất')+' · '+item.created_at); button.type='button'; button.addEventListener('click',()=>{selected=item.id;generation++;refresh();}); history.append(button); });
    } catch (err) {
      if(currentGeneration===generation) document.getElementById('job-message').textContent='Chưa kết nối được máy chủ. Tiến trình đã lưu sẽ được tải lại tự động.';
    } finally { if(currentGeneration===generation) timer = setTimeout(refresh, 4000); }
  }
  window.addEventListener('inventory-job-created', event=>{selected=event.detail.id;generation++;refresh();});
  refresh();
})();
