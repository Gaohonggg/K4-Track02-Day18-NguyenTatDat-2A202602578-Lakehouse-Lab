# Khai báo sử dụng AI

## Công cụ và phạm vi

Sử dụng OpenAI Codex để đọc yêu cầu repo, rà soát mã nguồn,
đề xuất và thực hiện sửa NB1/NB4 sau khi được người nộp xác nhận;
đưa lệnh thực thi. Chưa triển khai cloud hoặc chạy PoC bonus.

## Phân công thực hiện

- Người nộp tự chạy toàn bộ các lệnh tạo `.venv`, cài dependencies bằng uv,
  smoke test, pytest, sinh dữ liệu, chạy NB1/NB4, chuyển và thực thi tám `.ipynb`,
  sao chép bản nộp và chạy `scripts/run_all.py`.
- Codex sửa source được duyệt qua bởi tôi.
  Codex không thực thi notebook hoặc bộ tests thay người nộp trong quy trình này.
- Các cell mô phỏng MCP, embeddings và provenance là nội dung lab;
  chúng không gọi LLM thật, không triển khai MCP server và không chứng nhận quyền sử dụng dữ liệu.

## Bằng chứng và trách nhiệm

Số liệu trong bài được trích từ tám notebook có output đã lưu và logs thực thi.
Không tạo output giả, không thay output bằng số liệu dự kiến, không hạ ngưỡng để báo PASS.
Markdown phân tích được bổ sung sau khi đọc kết quả; code cells và execution outputs được giữ nguyên.

Người nộp cần đọc, chỉnh theo quan điểm của mình và tự giải thích được mã nguồn,
các phép đo, các giới hạn và mọi kết luận trước khi nộp.

Nguồn chính: README và các tài liệu trong `docs/`, source notebooks và output lần chạy trong repo cá nhân.
Nguồn bên ngoài cho bonus được liên kết tại [ARCHITECTURE.md](bonus/ARCHITECTURE.md).