# Vietnamese AI Video Dubber

Công cụ tự động dịch phụ đề và lồng tiếng thuyết minh tiếng Việt cho video nước ngoài (chủ yếu tiếng Anh).

```text
video -> audio -> phụ đề gốc (Whisper) -> dịch sang Việt -> lồng tiếng (Edge-TTS / VieNeu-TTS) -> MP4 kèm phụ đề Việt
```

## Tính năng

- **Speech-to-Text**: Nhận diện giọng nói bằng Faster-Whisper (chạy offline, không tốn phí).
- **Dịch thuật**: 4 lựa chọn — Google Translate (miễn phí), Ollama Local LLM, HuggingFace Hy-MT2-7B GGUF (trực tiếp, không cần Ollama), hoặc EnViT5 offline (Transformers).
- **Thuyết minh AI (TTS)**: Edge-TTS (online, Microsoft Neural) hoặc VieNeu-TTS (offline, 23 giọng Việt).
- **Xử lý Video**: Tự động khớp timeline âm thanh (atempo), burn phụ đề hoặc mux soft sub bằng FFmpeg.
- **Không phụ thuộc API trả phí hay Supertonic ONNX cồng kềnh.**

## Yêu cầu hệ thống

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| Python | ✔ | ≥ 3.10 |
| [uv](https://docs.astral.sh/uv/) | ✔ | Quản lý package + môi trường ảo |
| [ffmpeg](https://ffmpeg.org/) | ✔ | Xử lý video/audio |
| GPU NVIDIA (CUDA) | ✖ | Khuyến khích — tăng tốc Whisper & EnViT5; không có thì chạy CPU (chậm hơn) |
| Internet | Chỉ giai đoạn setup | Cần khi cài đặt và tải model lần đầu; Google Translate cần mạng mỗi lần dùng |

Cài đặt nền tảng:

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows: tải ffmpeg tại https://ffmpeg.org/download.html
# rồi cài uv:  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Cài đặt và chạy

```bash
git clone <địa-chỉ-repo> vi-video-dubber
cd vi-video-dubber
uv sync --frozen               # cài đặt toàn bộ dependencies (bao gồm VieNeu-TTS)
uv run python app.py           # khởi động server
```

> Lưu ý: `uv sync --frozen` sử dụng lock file đã đóng gói sẵn, tránh lỗi phân giải `veneu` trên một số máy.

Mở trình duyệt: **http://127.0.0.1:8787**

Tải video lên, chọn tùy chọn (provider dịch, lồng tiếng, burn phụ đề) rồi bấm chạy. Kết quả nằm trong thư mục `jobs/<job-id>/`.

## Model dịch thuật — chọn cái nào?

Chọn "Translation provider" trong giao diện web trước khi tạo job:

| | Google Translate | Ollama (Hy-MT2-7B) | HuggingFace Hy-MT2-7B | EnViT5 |
|---|---|---|---|---|
| **Cần API key** | Không | Không | Không | Không |
| **Cần internet khi chạy** | Có | Không | Không | Không |
| **Cài đặt** | Không cần | Cài Ollama + pull model | Tự động (tải model lần đầu) | Tự động (tải model lần đầu) |
| **Dung lượng tải** | 0 | ~4.6 GB (qua Ollama) | ~4.6 GB | ~2.1 GB |
| **Chất lượng dịch** | Tốt | Tốt nhất (7B LLM) | Tốt nhất (7B LLM) | Khá (T5 base) |
| **Tốc độ** | Nhanh (online) | Chậm nhất (LLM lớn) | Chậm (LLM lớn) | Nhanh (T5, GPU) |
| **Phù hợp** | Máy luôn online | Máy offline, cần chất lượng cao | Máy offline, không muốn cài Ollama | Máy offline, cần tốc độ |

### 1. Google Translate (mặc định)

Không cần cài đặt gì — chỉ cần internet. Đây là lựa chọn nhanh nhất để bắt đầu.

### 2. Ollama — LLM cục bộ

```bash
# 1. Cài Ollama: https://ollama.com/download
# 2. Khởi động & tải model dịch Anh-Việt:
ollama serve &                        # hoặc chạy app Ollama
ollama pull hf.co/tencent/Hy-MT2-7B-GGUF:Q4_K_M
# 3. Restart app, chọn "Ollama local" trong giao diện
```

Biến môi trường (tùy chọn):

| Biến | Mặc định | Mô tả |
|---|---|---|
| `OLLAMA_MODEL` | `hf.co/tencent/Hy-MT2-7B-GGUF:Q4_K_M` | Model dùng để dịch |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Địa chỉ Ollama server |
| `OLLAMA_TRANSLATE_BATCH_SIZE` | `20` | Số dòng dịch mỗi lần gọi |

### 3. HuggingFace Hy-MT2-7B GGUF — trực tiếp, không cần Ollama

Chạy model dịch Anh-Việt `tencent/Hy-MT2-7B-GGUF` trực tiếp từ HuggingFace bằng Transformers (không cần Ollama server). Tải model tự động (~4.6 GB) vào lần dùng đầu:

```bash
# Chỉ cần chọn "HuggingFace Hy-MT2-7B (GGUF)" trong giao diện, lần đầu sẽ tải model
```

Biến môi trường (tùy chọn):

| Biến | Mặc định | Mô tả |
|---|---|---|
| `HF_TRANSLATE_MODEL` | `tencent/Hy-MT2-7B-GGUF` | Model GGUF trên HuggingFace |
| `HF_TRANSLATE_BATCH_SIZE` | `20` | Số dòng dịch mỗi lần gọi |

> Lưu ý: GPU có CUDA sẽ tải nhanh hơn; nếu chỉ có CPU, vẫn chạy được nhưng chậm hơn (model 7B là LLM lớn).

### 4. EnViT5 — offline Transformers

Chạy hoàn toàn offline bằng model `VietAI/envit5-translation`. Tải model tự động (~2.1 GB) vào lần dùng đầu — chạy GPU nếu có CUDA, ngược lại fallback CPU. Không cần cài đặt gì thêm:

```bash
# Chỉ cần chọn "EnViT5 (offline GPU)" trong giao diện, lần đầu sẽ tải model
```

Biến môi trường (tùy chọn):

| Biến | Mặc định | Mô tả |
|---|---|---|
| `ENVIT5_MODEL` | `VietAI/envit5-translation` | Tên model trên HuggingFace |
| `ENVIT5_BATCH_SIZE` | `20` | Số dòng dịch mỗi lần gọi |

> Lưu ý GPU: nếu `uv run python app.py` báo lỗi triton không biên dịch được CUDA, đặt `CC=/usr/bin/gcc` trước khi chạy. Code đã tự đặt fallback này khi dùng EnViT5.

## Cấu hình Whisper (nhận diện giọng nói)

Mặc định chạy CPU với int8 (không cần GPU). Với GPU, đặt biến môi trường:

```bash
WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16 uv run python app.py
```

| Biến | Mặc định | Mô tả |
|---|---|---|
| `WHISPER_DEVICE` | `cpu` | `cpu` hoặc `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8`/`float16`/`float32` |
| `WHISPER_BEAM_SIZE` | `1` | Beam search — cao hơn = chính xác hơn, chậm hơn |

Model Whisper mặc định là `small` (chọn trong giao diện). Lần đầu chạy sẽ tải từ HuggingFace.

## Cấu hình TTS (lồng tiếng)

Chọn "Engine lồng tiếng" trong giao diện web trước khi tạo job:

| | Edge-TTS | VieNeu-TTS |
|---|---|---|
| **Trạng thái** | Online (Microsoft) | **Offline** |
| **Voices** | 2 (Hoài My, Nam Minh) | **23** (3 miền Bắc/Trung/Nam) |
| **Audio** | 44.1 kHz | **48 kHz** |
| **Voice cloning** | ❌ | ✅ (3-8s clip) |
| **Emotion cues** | ❌ | ✅ `[cười]` `[thở dài]` `[hắng giọng]` |
| **Cài đặt** | Không cần | Tự động qua `uv sync` |
| **Model size** | 0 | ~900 MB (tải lần đầu) |
| **Phù hợp** | Máy luôn online | Máy offline, nhiều giọng, clone giọng |

### 1. Edge-TTS (mặc định)

Dùng Edge-TTS miễn phí, cần internet. Giọng mặc định: `vi-VN-HoaiMyNeural` (nữ) — có thể đổi trong giao diện; giọng `vi-VN-NamMinhNeural` (nam).

### 2. VieNeu-TTS (offline)

Chạy hoàn toàn offline bằng VieNeu-TTS v3 Turbo (48 kHz, 23 giọng). Tải model tự động (~900 MB) lần đầu tiên.

```bash
# Chỉ cần chọn "VieNeu-TTS (offline)" trong giao diện, lần đầu sẽ tải model
```

Biến môi trường (tùy chọn):

| Biến | Mặc định | Mô tả |
|---|---|---|
| (không cần) | — | `vieneu` package tự tải model từ HuggingFace |

> Lưu ý: model được tải từ HuggingFace lần đầu (~900 MB). Sau đó chạy offline hoàn toàn, không cần internet.

## API (dành cho tích hợp)

- `POST /api/jobs` — tạo job (multipart: `file` + form options)
- `GET /api/queue` — danh sách jobs
- `GET /api/jobs/{id}` — trạng thái job
- `DELETE /api/jobs/{id}` — xóa job (job đang chạy → 409)
- `GET /api/jobs/{id}/download/{kind}` — tải kết quả
- `GET /api/config` — cấu hình & kiểm tra Ollama

## Câu hỏi thường gặp

**Dịch bị sót dòng (giữ nguyên tiếng Anh)?**
Mỗi dòng lỗi sẽ xuất hiện "Cảnh báo" trong kết quả job. Nguyên nhân phổ biến: Google rate-limit (mạng chậm) hoặc Ollama hết context. Dòng lỗi sẽ tự dịch lại riêng lẻ; nếu vẫn lỗi thì giữ bản gốc tiếng Anh thay vì dịch sai.

**Muốn dùng model dịch hay hơn?**
Đổi `OLLAMA_MODEL` sang bản lớn hơn (ví dụ bản Q6_K hay full precision) — chậm hơn nhưng chất lượng tốt hơn.

**File quá lớn?**
Giới hạn upload 2 GB mỗi file, tối đa 50 jobs, file kết quả tự xóa sau 6 tiếng.