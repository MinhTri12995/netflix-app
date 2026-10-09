document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.getElementById('accountDetailsDialog');
  const content = document.getElementById('accountDetailsContent');
  document.getElementById('closeDetails')?.addEventListener('click', () => dialog.close());
  document.querySelectorAll('.account-details-btn').forEach(button => button.addEventListener('click', async () => {
    content.textContent = 'Đang tải...';
    dialog.showModal();
    try {
      const response = await fetch(button.dataset.detailsUrl, {headers: {'Accept':'application/json'}});
      if (!response.ok || response.redirected) throw new Error('unavailable');
      const data = await response.json();
      content.replaceChildren();
      const title = document.createElement('h3'); title.textContent = 'Mã đang sử dụng tài khoản'; content.append(title);
      const codes = document.createElement('p'); codes.textContent = data.codes.join(' · ') || 'Không có mã liên quan.'; content.append(codes);
      const history = document.createElement('h3'); history.textContent = '20 sự kiện gần nhất'; content.append(history);
      if (!data.events.length) {const empty = document.createElement('p');empty.textContent = 'Chưa có lịch sử đổi được lưu.';content.append(empty);}
      data.events.forEach(event => {const row = document.createElement('p');row.textContent = [event.created_at,event.type,event.code,event.actor].filter(Boolean).join(' · ');content.append(row);});
    } catch {content.textContent = 'Không thể tải dữ liệu. Hãy thử lại sau.';}
  }));
  document.querySelectorAll('form[action$="/check"]').forEach(form => form.addEventListener('submit', () => {
    const button = form.querySelector('button'); button.disabled = true; button.textContent = 'Đang kiểm tra...';
  }));
});
