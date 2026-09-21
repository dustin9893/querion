# 🚀 Hướng dẫn Setup MSB Knowledge Assistant trên Windows

> Dành cho developer mới. Hướng dẫn từng bước từ A-Z, không bỏ sót bước nào.

---

## 📋 Bạn cần cài những gì?

Trước khi bắt đầu, máy tính của bạn cần có các phần mềm sau. Nếu chưa có, hãy cài theo thứ tự bên dưới.

| Phần mềm | Phiên bản tối thiểu | Để làm gì? |
|-----------|---------------------|------------|
| Git | 2.40+ | Quản lý source code |
| Docker Desktop | 4.20+ | Chạy database, Redis, MinIO |
| Python | 3.11+ | Chạy Backend API + Worker |
| Node.js | 18+ (LTS) | Chạy Frontend Web |
| VS Code | Mới nhất | Viết code |

---

## BƯỚC 1: Cài Git

### 1.1 Download
- Vào https://git-scm.com/download/win
- Click nút **"Click here to download"** → file `.exe` sẽ tải về

### 1.2 Cài đặt
- Mở file `.exe` vừa tải
- Nhấn **Next** liên tục, giữ nguyên mọi cài đặt mặc định
- Ở bước **"Adjusting your PATH environment"** → chọn **"Git from the command line and also from 3rd-party software"** (đây là mặc định)
- Nhấn **Install** → đợi xong → nhấn **Finish**

### 1.3 Kiểm tra
- Nhấn phím `Windows` → gõ **"PowerShell"** → mở **Windows PowerShell**
- Gõ lệnh:
```powershell
git --version
```
- Nếu thấy `git version 2.x.x` → ✅ thành công

> 💡 **PowerShell là gì?** Đó là chương trình để gõ lệnh trên Windows. Bạn sẽ dùng nó rất nhiều. Mỗi khi tài liệu này nói "mở terminal", nghĩa là mở PowerShell.

---

## BƯỚC 2: Cài Docker Desktop

### 2.1 Tại sao cần Docker?
Querion cần 3 dịch vụ nền:
- **PostgreSQL** — database lưu trữ dữ liệu
- **Redis** — hàng đợi cho background jobs
- **MinIO** — lưu trữ file upload (giống AWS S3 nhưng chạy local)

Docker giúp bạn chạy cả 3 dịch vụ này bằng **1 lệnh duy nhất**, không cần cài từng cái.

### 2.2 Download
- Vào https://www.docker.com/products/docker-desktop/
- Click **"Download for Windows"**

### 2.3 Cài đặt
- Mở file `.exe` vừa tải
- ✅ Tick chọn **"Use WSL 2 instead of Hyper-V"** (rất quan trọng!)
- Nhấn **OK** → đợi cài xong
- **Restart máy tính** khi được yêu cầu

### 2.4 Sau khi restart
- Docker Desktop sẽ tự mở (hoặc bạn mở từ Start Menu)
- Đợi cho đến khi **icon Docker ở góc phải dưới taskbar** (hình con cá voi) chuyển sang **màu xanh lá** và hiện "Docker Desktop is running"
- Nếu nó yêu cầu đăng nhập → bạn có thể bỏ qua (skip), không cần tài khoản Docker

### 2.5 Kiểm tra
Mở PowerShell mới:
```powershell
docker --version
```
Nếu thấy `Docker version 24.x.x` hoặc `27.x.x` → ✅ thành công

```powershell
docker compose version
```
Nếu thấy `Docker Compose version v2.x.x` → ✅ thành công

> ⚠️ **Nếu gặp lỗi**: Đảm bảo Docker Desktop đang chạy (icon cá voi xanh ở taskbar).

---

## BƯỚC 3: Cài Python

### 3.1 Download
- Vào https://www.python.org/downloads/
- Click nút vàng lớn **"Download Python 3.1x.x"**

### 3.2 Cài đặt

> ⚠️⚠️⚠️ **CỰC KỲ QUAN TRỌNG** ⚠️⚠️⚠️

Ở màn hình cài đặt đầu tiên:
- ✅ **PHẢI TICK** chọn **"Add python.exe to PATH"** ở phía dưới cùng
- Sau đó mới nhấn **"Install Now"**

Nếu bạn quên tick, Python sẽ không nhận được từ terminal và tất cả các bước sau sẽ lỗi!

### 3.3 Kiểm tra
Đóng PowerShell cũ, mở PowerShell **mới** (quan trọng!):
```powershell
python --version
```
Nếu thấy `Python 3.11.x` hoặc `3.12.x` → ✅ thành công

```powershell
pip --version
```
Nếu thấy `pip 24.x.x from ...` → ✅ thành công

> ❌ **Nếu gõ `python` mà mở Microsoft Store**: vào Settings → Apps → App execution aliases → tắt "App Installer python.exe" và "App Installer python3.exe"

---

## BƯỚC 4: Cài Node.js

### 4.1 Download
- Vào https://nodejs.org/
- Click nút **LTS** (Long Term Support) — **KHÔNG** chọn Current

### 4.2 Cài đặt
- Mở file `.msi` vừa tải
- Nhấn **Next** liên tục, giữ nguyên mặc định
- Nhấn **Install** → đợi xong

### 4.3 Kiểm tra
Đóng PowerShell cũ, mở PowerShell **mới**:
```powershell
node --version
```
→ `v18.x.x` hoặc `v20.x.x` → ✅

```powershell
npm --version
```
→ `9.x.x` hoặc `10.x.x` → ✅

---

## BƯỚC 5: Cài VS Code

### 5.1 Download
- Vào https://code.visualstudio.com/
- Click **"Download for Windows"**
- Cài bình thường, giữ mặc định

### 5.2 Cài Extensions (tuỳ chọn nhưng khuyến nghị)
Mở VS Code → nhấn `Ctrl+Shift+X` (mở Extensions) → tìm và cài:
1. **Python** (của Microsoft)
2. **ESLint**
3. **Prettier - Code formatter**

---

## BƯỚC 6: Clone source code

### 6.1 Mở PowerShell

Nhấn `Windows` → gõ "PowerShell" → mở **Windows PowerShell**

### 6.2 Tạo thư mục và clone

```powershell
# Di chuyển đến Desktop (hoặc nơi bạn muốn lưu code)
cd ~\Desktop

# Clone repository (thay URL bằng URL thực tế của Git repo)
git clone <GIT_REPO_URL> querion
```

> 💡 **`<GIT_REPO_URL>` là gì?** Đây là link Git của project, ví dụ:
> `https://gitlab.com/your-team/querion.git` hoặc `git@gitlab.com:your-team/querion.git`
> Hỏi team leader để lấy URL này.

```powershell
# Vào thư mục project
cd querion
```

### 6.3 Mở project trong VS Code

```powershell
code .
```

Lệnh này sẽ mở VS Code với toàn bộ project. Từ giờ bạn có thể dùng **Terminal tích hợp** trong VS Code (nhấn `` Ctrl+` `` để mở).

---

## BƯỚC 7: Khởi động Infrastructure (Database + Redis + MinIO)

### 7.1 Chuẩn bị file cấu hình

Trong VS Code, mở terminal (`` Ctrl+` ``):

```powershell
cd infra\docker
```

Copy file cấu hình mẫu:
```powershell
copy .env.example .env
```

> 💡 File `.env` chứa username, password của database, Redis, MinIO. Giá trị mặc định dùng cho development, không cần thay đổi.

### 7.2 Khởi động

```powershell
docker compose up -d
```

> 💡 **Lệnh này làm gì?**
> - Tải về "image" (bản cài đặt) của PostgreSQL, Redis, MinIO từ internet (lần đầu sẽ mất 2-5 phút)
> - Tạo và chạy 3 container (giống như 3 máy tính ảo nhỏ)
> - `-d` nghĩa là chạy nền (không chiếm terminal)

### 7.3 Kiểm tra

Đợi khoảng 30 giây, rồi gõ:
```powershell
docker compose ps
```

Bạn sẽ thấy bảng như thế này:
```
NAME                STATUS
querion-postgres    running (healthy)
querion-redis       running (healthy)
querion-minio       running (healthy)
querion-minio-init  exited (0)          ← đây là bình thường, nó chỉ chạy 1 lần
```

> ✅ Tất cả phải là **healthy**. Nếu là **starting**, đợi thêm 30 giây rồi chạy lại `docker compose ps`.

### 7.4 Kiểm tra MinIO bằng browser (tuỳ chọn)
- Mở browser → vào http://localhost:9001
- Đăng nhập: Username = `minioadmin`, Password = `minioadmin_secret`
- Bạn sẽ thấy giao diện quản lý file storage

---

## BƯỚC 8: Setup Backend API (FastAPI)

### 8.1 Mở terminal mới trong VS Code

Trong VS Code, nhấn nút **+** ở góc phải trên của panel Terminal để tạo terminal mới.

### 8.2 Di chuyển vào thư mục API

```powershell
cd apps\api
```

### 8.3 Tạo Virtual Environment

> 💡 **Virtual Environment là gì?** Nó tạo một "phòng cách ly" cho Python của project này, tránh xung đột với các project Python khác trên máy bạn.

```powershell
python -m venv venv
```

Lệnh này tạo thư mục `venv/` — đợi vài giây.

### 8.4 Kích hoạt Virtual Environment

```powershell
.\venv\Scripts\Activate.ps1
```

Nếu thành công, bạn sẽ thấy `(venv)` xuất hiện ở đầu dòng lệnh:
```
(venv) PS C:\Users\TenBan\Desktop\querion\apps\api>
```

> ⚠️ **Nếu gặp lỗi đỏ** kiểu "running scripts is disabled":
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Gõ `Y` để xác nhận, rồi thử lại lệnh Activate.

> ⚠️ **QUAN TRỌNG**: Mỗi lần mở terminal mới để chạy API, bạn PHẢI kích hoạt lại venv bằng lệnh `.\venv\Scripts\Activate.ps1`. Nếu không thấy `(venv)` ở đầu dòng → venv chưa active → sẽ lỗi!

### 8.5 Cài đặt dependencies

```powershell
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

> 💡 Lệnh này đọc file `pyproject.toml` và cài tất cả thư viện cần thiết. Lần đầu sẽ mất 2-3 phút.
> Dòng thứ hai tải mô hình spaCy nhỏ (~12 MB) cho **Microsoft Presidio** — bộ che thông tin cá nhân (PII). Thiếu nó API vẫn chạy nhưng dùng regex dự phòng.

Nếu gặp lỗi liên quan **psycopg2** hoặc **C compiler**:
```powershell
pip install psycopg2-binary
# rồi chạy lại
pip install -e ".[dev]"
```

### 8.6 Tạo file cấu hình

Tạo file mới `apps/api/.env` (có thể tạo bằng VS Code: chuột phải → New File → đặt tên `.env`):

```ini
# Database
DATABASE_URL=postgresql+asyncpg://querion:querion_secret@localhost:5432/querion

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO (file storage)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin_secret
MINIO_BUCKET=querion-docs
MINIO_USE_SSL=false

# Auth
JWT_SECRET=querion-dev-secret-change-in-production

# Encryption (dùng cho mã hoá API key của AI providers)
ENCRYPTION_KEY=your-32-char-encryption-key-here!

# Super Admin (tài khoản admin tạo tự động lần đầu)
SUPER_ADMIN_EMAIL=admin@querion.io
SUPER_ADMIN_PASSWORD=admin123
SUPER_ADMIN_NAME=Super Admin
```

### 8.7 Chạy Database Migrations

> 💡 **Migration là gì?** Nó tạo các bảng (table) trong database. Mỗi file migration tạo thêm bảng hoặc cột mới.

```powershell
alembic upgrade head
```

Kết quả mong đợi:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, ...
...
INFO  [alembic.runtime.migration] Running upgrade 0011 -> 0012, ...
```

> ❌ **Nếu lỗi "Connection refused"**: Docker PostgreSQL chưa chạy. Quay lại Bước 7, kiểm tra `docker compose ps`.

### 8.8 Khởi động API Server

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Kết quả mong đợi:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Started reloader process
```

> 💡 `--reload` nghĩa là server tự restart khi bạn sửa code Python. Rất tiện khi develop!

### 8.9 Kiểm tra

Mở browser → vào:
- http://localhost:8000/health → phải thấy text `ok` hoặc JSON status
- http://localhost:8000/docs → phải thấy giao diện Swagger API docs

> ✅ **GIỮ TERMINAL NÀY CHẠY.** Đừng đóng, đừng nhấn `Ctrl+C`. API cần luôn chạy.

---

## BƯỚC 9: Setup Frontend Web (Next.js)

### 9.1 Mở terminal MỚI

Trong VS Code, nhấn nút **+** ở panel Terminal để tạo terminal mới.

> ⚠️ **KHÔNG** gõ vào terminal đang chạy API! Tạo terminal MỚI.

### 9.2 Di chuyển + cài dependencies

```powershell
cd apps\web

npm install
```

> 💡 Lần đầu sẽ mất 1-2 phút, tải về hàng nghìn packages.

### 9.3 Tạo file cấu hình

Tạo file mới `apps/web/.env.local`:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> 💡 Dòng này cho frontend biết backend API đang chạy ở đâu.

### 9.4 Khởi động Frontend

```powershell
npm run dev
```

Kết quả mong đợi:
```
  ▲ Next.js 14.x.x
  - Local:   http://localhost:3000
  ✓ Ready
```

### 9.5 Kiểm tra

Mở browser → vào http://localhost:3000

Bạn sẽ thấy **trang đăng nhập** (login page). Đăng nhập bằng:
- **Email**: `admin@querion.io`
- **Password**: `admin123`

> ✅ Nếu đăng nhập thành công và thấy giao diện chính → **Frontend hoạt động!**

> ✅ **GIỮ TERMINAL NÀY CHẠY.**

---

## BƯỚC 10: Setup Worker (Background Jobs)

### 10.1 Worker làm gì?

Khi admin upload tài liệu (PDF, Word) vào dataset, Worker sẽ:
1. Đọc file từ MinIO
2. Trích xuất text
3. Chia nhỏ thành chunks
4. Tạo embeddings (vector) bằng AI
5. Lưu vào database để tìm kiếm

### 10.2 Mở terminal MỚI và setup

```powershell
cd apps\worker

# Tạo virtual environment riêng cho worker
python -m venv venv

# Kích hoạt
.\venv\Scripts\Activate.ps1

# Cài dependencies
pip install -r requirements.txt
```

### 10.3 Tạo file cấu hình

Tạo file `apps/worker/.env`:

```ini
# Worker dùng psycopg2 (sync), KHÔNG có +asyncpg
DATABASE_URL=postgresql://querion:querion_secret@localhost:5432/querion

REDIS_URL=redis://localhost:6379/0

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin_secret
MINIO_BUCKET=querion-docs

# ENCRYPTION_KEY phải GIỐNG với file .env của API
ENCRYPTION_KEY=your-32-char-encryption-key-here!
```

> ⚠️ `DATABASE_URL` ở đây **KHÔNG** có `+asyncpg`. Worker dùng driver khác (sync) so với API (async).

### 10.4 Khởi động Worker

```powershell
python -m worker.main
```

Kết quả mong đợi:
```
Worker started, listening for jobs...
```

> ✅ **GIỮ TERMINAL NÀY CHẠY.**

---

## ✅ HOÀN TẤT! Kiểm tra tổng thể

Lúc này bạn phải có **4 terminal** đang chạy:

| Terminal | Vị trí | Lệnh đang chạy | Port |
|----------|--------|-----------------|------|
| 1 | `infra/docker` | `docker compose up -d` (đã chạy xong) | 5432, 6379, 9000 |
| 2 | `apps/api` | `uvicorn app.main:app --reload --port 8000` | 8000 |
| 3 | `apps/web` | `npm run dev` | 3000 |
| 4 | `apps/worker` | `python -m worker.main` | — |

Mở browser kiểm tra:
- http://localhost:3000 → Web UI ✅
- http://localhost:8000/docs → API Docs ✅
- http://localhost:9001 → MinIO Console ✅

---

## 🔄 Hàng ngày khi bật máy

Mỗi lần bật máy và muốn code, làm theo thứ tự:

### 1. Mở Docker Desktop
- Click icon Docker Desktop từ Start Menu
- Đợi icon cá voi ở taskbar chuyển xanh

### 2. Khởi động database
```powershell
cd ~\Desktop\querion\infra\docker
docker compose up -d
```

### 3. Khởi động API (terminal 1)
```powershell
cd ~\Desktop\querion\apps\api
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

### 4. Khởi động Web (terminal 2)
```powershell
cd ~\Desktop\querion\apps\web
npm run dev
```

### 5. Khởi động Worker (terminal 3)
```powershell
cd ~\Desktop\querion\apps\worker
.\venv\Scripts\Activate.ps1
python -m worker.main
```

### 6. Pull code mới (nếu có người khác push)
```powershell
cd ~\Desktop\querion
git pull origin main
```

Sau khi pull:
- Nếu thay đổi **Python dependencies**: `cd apps\api && pip install -e .`
- Nếu thay đổi **Node dependencies**: `cd apps\web && npm install`
- Nếu có **migration mới**: `cd apps\api && alembic upgrade head` (phải activate venv trước)

---

## 🔒 Tài khoản mặc định

| Loại | Email | Password | URL đăng nhập |
|------|-------|----------|---------------|
| Admin | admin@querion.io | admin123 | http://localhost:3000/login |
| Cán bộ | rm.an@msb-demo.vn *(hoặc admin tạo ở Quản trị → Cán bộ)* | demo123 | http://localhost:3000/staff/login |

> 💡 Cán bộ mới phải đổi mật khẩu ở lần đăng nhập đầu tiên.

---

## 🛑 Xử lý lỗi thường gặp

### Lỗi 1: "Docker daemon is not running"
**Nguyên nhân**: Docker Desktop chưa mở
**Cách sửa**: Mở Docker Desktop từ Start Menu, đợi icon xanh

### Lỗi 2: "running scripts is disabled on this system"
**Nguyên nhân**: Windows chặn chạy script PowerShell
**Cách sửa**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Gõ `Y` rồi Enter

### Lỗi 3: "python" mở Microsoft Store
**Nguyên nhân**: Windows alias trỏ sai
**Cách sửa**: Settings → Apps → Advanced app settings → App execution aliases → tắt cả 2 mục "python.exe"

### Lỗi 4: "Port 8000 already in use"
**Nguyên nhân**: API đang chạy ở terminal khác
**Cách sửa**:
```powershell
# Tìm process
netstat -aon | findstr :8000
# Kết quả: ... LISTENING  12345
# Kill theo PID (số cuối)
taskkill /PID 12345 /F
```

### Lỗi 5: "ModuleNotFoundError: No module named 'app'"
**Nguyên nhân**: venv chưa active hoặc chưa cài dependencies
**Cách sửa**:
```powershell
# 1. Kích hoạt venv (kiểm tra có (venv) ở đầu dòng không)
.\venv\Scripts\Activate.ps1
# 2. Cài lại
pip install -e ".[dev]"
```

### Lỗi 6: "Connection refused" khi chạy migrations
**Nguyên nhân**: Database chưa chạy
**Cách sửa**:
```powershell
cd infra\docker
docker compose ps
# Nếu postgres không running:
docker compose up -d
# Đợi 30 giây rồi thử lại
```

### Lỗi 7: Frontend hiển thị trang trắng hoặc lỗi fetch
**Nguyên nhân**: Thiếu file `.env.local` hoặc API chưa chạy
**Cách sửa**:
1. Kiểm tra file `apps/web/.env.local` có dòng `NEXT_PUBLIC_API_URL=http://localhost:8000`
2. Kiểm tra API đang chạy ở terminal khác (http://localhost:8000/health)

### Lỗi 8: "error during connect: Get http://%2F%2F.%2Fpipe%2Fdocker_engine"
**Nguyên nhân**: Docker Desktop chưa khởi động hoàn tất
**Cách sửa**: Đợi 1-2 phút cho Docker Desktop khởi động xong (icon xanh)

---

## 🛟 Cần hỗ trợ?

1. Đọc kỹ thông báo lỗi — thường nó nói rõ vấn đề
2. Google message lỗi — thêm "Windows" vào từ khoá
3. Hỏi team lead hoặc đồng nghiệp

> 💡 **Mẹo quan trọng**: Khi gặp lỗi, **copy toàn bộ dòng lỗi** (text màu đỏ) rồi paste vào Google hoặc StackOverflow. Đừng chỉ đọc mà không search!
