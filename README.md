# FIM
Công cụ giám sát toàn vẹn tệp tin
Mô Tả:
- Sử dụng thư viện hashlib cùng thuật toán mã hóa SHA-256 để tính toán và đối chiếu mã băm của tệp tin
- Tích hợp thư viện watchdog nhằm theo dõi các sự kiện tạo, sửa đổi và xóa tệp tin theo thời gian thực
- Xây dựng cơ chế đối soát ngoại tuyến (offline sync) để phát hiện các thay đổi lén lút khi phần mềm không hoạt động
- Thiết kế giao diện người dùng (GUI) bằng tkinter cung cấp tính năng cấu hình, ghi nhật ký (log) chi tiết và cảnh báo
- Triển khai tính năng sao lưu vật lý và khôi phục dữ liệu về các mốc trạng thái an toàn trong quá khứ
- Cấu hình ứng dụng khởi động cùng Windows thông qua Registry
Luồng hoạt động:
- Tạo Baseline: quét thư mục mục tiêu, tính toán mã băm SHA-256 cho nội dung từng tệp tin và sao lưu vào file 'snapshots/files', tham chiếu nội dung file thông qua việc lưu thông tin ở file trực tiếp trong thư mục 'snapshots'.
- Lăng nghe sự kiện: mỗi khi có sự thay đổi của thư mục (tạo,sửa,xóa file) thì watchdog sẽ ngay lập tức phản hồi theo dạng thông báo popup của window dựa trên sự đối chiếu mã băm.