# Reflection — Small-file problem

Tôi chọn anti-pattern ingest liên tục nhưng thiếu maintenance. Với LLM observability,
mỗi micro-batch có thể ghi đúng dữ liệu nhưng tạo quá nhiều file nhỏ. Query phải mở
nhiều file và xử lý metadata, làm tăng latency lẫn chi phí request.

NB2 giảm từ 200 xuống 55 file; Z-order giúp chỉ một file có khoảng `user_id`
chứa giá trị cần tìm. NB6 giảm từ 200 xuống 11 file sau compaction và đạt skip rate
90% sau clustering. Đây là bằng chứng rằng bố trí dữ liệu và bảo trì ảnh hưởng trực tiếp
đến hiệu quả truy vấn.

Tôi sẽ theo dõi số file, kích thước file và bytes scan; điều chỉnh batching,
compaction và clustering theo workload. Retention phải bảo vệ reader và khả năng
rollback; orphan cleanup cần kiểm tra tham chiếu và tuổi file. Xóa snapshot khỏi
metadata chưa đồng nghĩa đã thu hồi storage.

Codex hỗ trợ coding, sửa kiểm tra NB1/NB4; tôi tự chạy các lệnh.
Phạm vi chi tiết: [AI_USAGE.md](AI_USAGE.md).
