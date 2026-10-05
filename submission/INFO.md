# K4-Track02-Day18 — Thông tin bài nộp

| Trường | Giá trị |
|---|---|
| Họ tên | Nguyễn Tất Đạt |
| Họ tên không dấu trong tên repo | NguyenTatDat |
| MSSV | 2A202602578 |
| Mã bài | K4-Track02-Day18 |
| Repo cá nhân | [Gaohonggg/K4-Track02-Day18-NguyenTatDat-2A202602578-Lakehouse-Lab](https://github.com/Gaohonggg/K4-Track02-Day18-NguyenTatDat-2A202602578-Lakehouse-Lab) |
| Đường chạy | Lightweight cho cả NB1–NB8 |
| Môi trường | `.venv`, quản lý bằng uv 0.11.18 |
| Python | CPython 3.11.16 |
| Hệ điều hành | macOS 26.6.2, Apple silicon / arm64 |
| Ngày thực thi | 04/10/2026, Asia/Ho_Chi_Minh |

## Phiên bản thư viện thực chạy

`deltalake 1.6.6`, `pyiceberg 0.12.0`, `pyiceberg-core 0.10.1`,
`duckdb 1.5.6`, `polars 1.44.2`, `pyarrow 25.0.1`, `numpy 2.4.6`,
`jupyterlab 4.6.4`, `jupytext 1.19.5`, `pytest 9.1.1`.

Toàn bộ phiên bản packages được lưu cục bộ trong
`_lakehouse/logs/requirements.freeze.txt`; không đưa thư mục dữ liệu sinh ra vào bài nộp.
Đây là bản ghi môi trường macOS arm64 đã chạy; không khẳng định đã kiểm thử các nền tảng khác.

## Kết quả kiểm chứng

| Kiểm tra | Kết quả quan sát | Bằng chứng |
|---|---|---|
| Smoke test | 9/9 thành công | Log cục bộ `05_smoke.log` |
| Pytest trước khi sửa NB1/NB4 | 24/24 thành công | Log cục bộ `06_pytest_baseline.log` |
| Thực thi bằng kernel `.venv` | Đủ 8 `.ipynb`; mọi code cell có execution count; không có error output | [Notebooks đã lưu output](notebooks/) |
| Runner sau khi sửa NB1/NB4 | 8/8 PASS, 10.9 giây | Log cục bộ `14_run_all.log` |

Các log cục bộ nằm trong `_lakehouse/logs/`, đã được đối chiếu khi lập báo cáo;
không đính kèm bản sao trong bài nộp. Bằng chứng được nộp là notebook có output và screenshots.

Notebook trong `submission/notebooks/` lưu output của lần chạy bằng nbconvert.
Sau đó runner đã chạy lại mã `.py`; các bảng scratch hiện tại có thể thuộc lần chạy sau.
Số liệu trong [RESULTS.md](RESULTS.md) lấy từ output notebook đã lưu, không trộn timing giữa các lần chạy.

## Thay đổi so với đề bài

- NB1: in commit JSON; thay flag schema enforcement đặt sẵn bằng kiểm tra lỗi thực tế,
  đồng thời đối chiếu version, schema và toàn bộ ba dòng trước/sau lần ghi bị chặn.
- NB4: bổ sung coverage ngày–model, khóa duy nhất và kiểm tra giá trị Gold;
  tính lại sáu metrics của một nhóm từ Silver bằng Python để đối chiếu kết quả SQL.
- Giữ nguyên dữ liệu mẫu, cơ chế pipeline và các ngưỡng rubric; không bỏ assertion.
- Các notebook bài nộp có thêm Markdown giải thích dựa trên output đã thực thi;
  code cells và output gốc của lần chạy được giữ nguyên.

## Các thành phần bài nộp

- [RESULTS.md](RESULTS.md): bằng chứng và phân tích cả tám notebook.
- [REFLECTION.md](REFLECTION.md): reflection về small-file problem.
- [AI_USAGE.md](AI_USAGE.md): phạm vi hỗ trợ của AI và phân công thực thi.
- [screenshots/](screenshots/): ảnh kết quả thực tế của NB1–NB8.
- [bonus/ARCHITECTURE.md](bonus/ARCHITECTURE.md): brief bonus A về LLM observability;
  đã có thiết kế, alternatives, failure modes, cost math và MVP.
