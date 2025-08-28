#!/bin/bash

# Tạo thư mục cấu hình nếu chưa có
mkdir -p ~/.streamlit/

# Tạo file cấu hình config.toml (bỏ qua cổng)
echo -e "[server]\nenableCORS = true\nenableXsrfProtection = false\nheadless = true\n" > ~/.streamlit/config.toml

# Chạy ứng dụng Streamlit và chỉ định đúng cổng
streamlit run app.py --server.port=$PORT
