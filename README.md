# Day 06 · Data Ingestion Engineering

## Bài làm — cách chạy lại

**Nguyễn Gia Bảo · 2A202603647 · K5-L3A.** Corpus: OpenStax *Principles of Microeconomics 3e*, Ch3/Ch4/Ch14 (78 trang nội dung, CC BY-NC-SA 4.0). Báo cáo: [report/individual/2A202603647_NguyenGiaBao.md](report/individual/2A202603647_NguyenGiaBao.md).

| Thành phần | Lựa chọn |
|---|---|
| Đọc PDF | PyMuPDF 2.1 (block = đoạn văn), chuẩn hóa NFKC |
| Embedding | `intfloat/multilingual-e5-base`, 768 chiều, chạy local trên CPU, 0 USD |
| Vector store | PostgreSQL 16 + pgvector 0.8.7 (Docker), cosine, exact search, filter `chapter` |
| Chiến lược | A fixed 500/50 · B theo đoạn ≤1000 · **C = B + lọc chương** (được chọn trên dev) |
| Benchmark | 22 câu (16 dev / 6 test, 5 câu filter), kiểm chứng tự động |

Yêu cầu: Docker, Python 3.13 (3.11–3.14). Chạy từ thư mục `starter/` (Windows PowerShell; macOS/Linux đổi lệnh kích hoạt venv và lệnh copy):

```bash
cd starter
python -m venv .venv
.venv\Scripts\Activate.ps1                     # macOS/Linux: source .venv/bin/activate
python -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
Copy-Item .env.example .env                    # macOS/Linux: cp .env.example .env
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py                  # Setup OK

python scripts/fetch_corpus.py                 # tải PDF, kiểm tra sha256
python scripts/build_manifest.py               # ../data/manifest*.csv từ outline PDF
python -m scripts.extract_pages                # data/processed/pages.jsonl + results/ingest_log.csv
python -m scripts.verify_benchmark             # kiểm chứng 22 evidence trên trang gold
python -m scripts.make_chunks                  # results/chunks/{A,B}.jsonl + chunk_stats.csv
python -m src.run ingest                       # embed + upsert A, B (chạy lại: 0 thay đổi)
python -m scripts.reingest_check               # kiểm tra tài liệu bị sửa
python -m src.run evaluate --split dev
python -m src.run select                       # áp tiêu chí đã chốt -> results/selection.json
python -m src.run evaluate --split test        # bị từ chối nếu chưa có selection.json
python -m scripts.make_audit_sheets            # phiếu chấm thủ công (không điền nhãn)
python -m scripts.summarize_audit              # tổng hợp nhãn -> bảng trong báo cáo
python -m src.run query --strategy C --chapter 4 "What is a usury law?"
```

Nếu `extract_pages` hoặc `make_chunks` được chạy lại, kết quả là tất định (cùng PDF sha256 → cùng text, cùng `chunk_id`). Lần ingest đầu mất khoảng 2 phút trên CPU, cộng thời gian tải model khoảng 1 GB.

| Thư mục | Nội dung |
|---|---|
| `starter/src/` | `ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py`, `config.py` |
| `starter/scripts/` | tải corpus, manifest, trích xuất, kiểm chứng benchmark, chunk, kiểm tra nạp lại, phiếu chấm |
| `data/` | manifest nguồn và trang (`starter/data/processed/pages.jsonl` là text đã chuẩn hóa, có ghi nguồn) |
| `benchmark/` | `questions.jsonl` và README (thiết kế, tiêu chí chọn và mẫu chấm đã chốt trước) |
| `artifacts/experiment_log.csv` | cấu hình, giả thuyết và Hit@1/Hit@3 của A/B/C |
| `starter/results/` | trace, metrics, thống kê chunk, log ingest, nhãn audit (xem README trong thư mục) |

Mốc commit chứng minh thứ tự làm việc: `48d9be9` khóa benchmark → `a0fa5d0` chọn chiến lược trên dev → `cc0ed58` chạy test một lần.

---

# Đề bài

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
