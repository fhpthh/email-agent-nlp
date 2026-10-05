from pathlib import Path

# Danh sách tất cả các file cần tạo
files = [
    "docker-compose.yml",
    "requirements.txt",
    ".env.example",
    "scripts/schema.sql",
    "src/emailagent/__init__.py",
    "src/emailagent/config.py",
    "src/emailagent/domain/__init__.py",
    "src/emailagent/domain/models.py",
    "src/emailagent/ports/__init__.py",
    "src/emailagent/ports/provider.py",
    "src/emailagent/ports/llm.py",
    "src/emailagent/api/__init__.py",
    "src/emailagent/api/main.py",
]

base_dir = Path("email-agent")

for file_path in files:
    full_path = base_dir / file_path
    # Tạo thư mục cha nếu chưa tồn tại
    full_path.parent.mkdir(parents=True, exist_ok=True)
    # Tạo file rỗng
    full_path.touch(exist_ok=True)

print(f" Đã khởi tạo cấu trúc thư mục tại: {base_dir.resolve()}")