# Báo cáo cá nhân — Day 6 · Data Ingestion

**Học viên:** Nguyễn Gia Bảo · **MSSV:** 2A202603647 · **Lớp:** K5-L3A
**Corpus:** OpenStax *Principles of Microeconomics 3e*, Ch3, Ch4, Ch14 · **Chiến lược chọn:** C (đoạn văn + lọc theo chương)

> Mọi số liệu dưới đây lấy từ file trong repo, đường dẫn ghi tại chỗ. Lệnh tái lập nằm ở [README.md](../../README.md#bài-làm--cách-chạy-lại).

## Tóm tắt

- **Pipeline:**
  - 78 trang PDF đi qua PyMuPDF và được chuẩn hóa.
  - Ba chiến lược: A cửa sổ 500/50, B theo đoạn ≤1000, C = B + lọc `chapter`.
  - Embedding e5-base chạy local (768 chiều, 0 USD), lưu trong pgvector với exact cosine.
  - Nạp lại không trùng, đã kiểm chứng.
- **Quy trình chống rò rỉ:**
  - Benchmark 22 câu (16 dev / 6 test, 5 câu filter) được khóa trước khi chạy.
  - Chọn chiến lược trên dev bằng quy tắc chốt sẵn, rồi mới chạy test một lần.
  - Code chặn chạy test trước khi chọn.
- **Kết quả (Evidence Hit@3):** dev A 9/16, B 8/16, **C 9/16**; test A 2/6, B 4/6, **C 5/6**. C được chọn.
- **Phát hiện chính:**
  1. A trượt vì cửa sổ cắt đôi evidence.
  2. B trượt vì chunk dài bị pha loãng ngữ nghĩa. Thí nghiệm hậu kiểm B500 trên dev (13/16) ủng hộ giải thích này.
  3. Lọc theo chương là thay đổi có bằng chứng rõ nhất: các distractor khác chương được dự đoán trước, xuất hiện đúng như dự đoán, và filter sửa được (q13, q19).
- **Audit:**
  - Coherence: A 1.00/2, B/C 1.70/2.
  - Metadata đúng 54/54.
  - Grounding (sau kiểm duyệt): A 1.33, B 1.83, C 2.00.
  - Nhãn do LLM judge gán, học viên kiểm duyệt (chấp nhận 91, sửa 1).
- **Giới hạn chính:** mẫu nhỏ (một câu tương đương 6–17 điểm %), nhãn không phải chú thích độc lập, kết quả B500 chưa có test độc lập.

## Dữ liệu và pipeline

- **Chủ đề, nguồn, quyền, số trang và quy tắc tính trang:**
  - **Nguồn:** *Principles of Microeconomics 3e* (OpenStax, Rice University), bản PDF WEB ngày 20/04/2026, sha256 `65a1856f…4a583f`, truy cập 13/11/2026.
  - **Giấy phép:** CC BY-NC-SA 4.0, dùng phi thương mại và có ghi nguồn. Một phần Ch3 lấy từ Lumen Learning (CC BY 4.0).
  - **Số trang:** chọn 3 chương có khái niệm chồng lấn (cung cầu, thị trường lao động, giá trần/sàn), tổng **78 trang nội dung** trên 595 trang vật lý: Ch3 p59–89 (31), Ch4 p97–115 (19), Ch14 p335–362 (28).
  - **Quy tắc tính trang, áp dụng tự động từ bookmark của PDF:** từ trang mở đầu chương đến trang ngay trước "Key Terms". Như vậy loại phần thuật ngữ, tóm tắt, bài tập, bìa, mục lục, phụ lục, đáp án, tài liệu tham khảo và chỉ mục.
  - `page` luôn là **trang PDF vật lý, bắt đầu từ 1**. Số trang in = trang vật lý − 12.
  - Manifest: [data/manifest.csv](../../data/manifest.csv), [data/manifest_pages.csv](../../data/manifest_pages.csv), sinh bởi `scripts/build_manifest.py`. PDF không commit; `scripts/fetch_corpus.py` tải lại và kiểm tra sha256.
- **Chuẩn hóa, lỗi và giới hạn:**
  - **Trích xuất:** PyMuPDF theo block, vì pypdf làm mất ranh giới đoạn.
  - **Chuẩn hóa:** NFKC, đổi nháy cong và gạch dài sang ASCII, gộp khoảng trắng trong block, các block nối bằng `\n\n`. Header/footer bị bỏ theo tọa độ trên 75 trang; 3 trang còn lại là trang mở đầu chương, vốn không có header.
  - **Lỗi đã ghi:** 0 trang rỗng hoặc cần OCR. 52 block hình bị bỏ qua (giữ chú thích hình). 61 đoạn bị cắt giữa câu (B ghép lại). 40 trang kết thúc giữa câu (không ghép, vì chunk không vượt trang). 13 gạch nối do xuống dòng (không sửa, vì 3 trong số đó là gạch nối treo hợp lệ). Bảng 4.2 ở p101 bị xáo thứ tự ô.
  - Chi tiết: [starter/results/README.md](../../starter/results/README.md), [ingest_log.csv](../../starter/results/ingest_log.csv).
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - **Model:** `intfloat/multilingual-e5-base` qua sentence-transformers 6.3.0, chạy local trên CPU. 768 chiều, tối đa 512 token, tiền tố `query: ` và `passage: `, vector chuẩn hóa L2.
  - **Lý do không dùng MiniLM:** giới hạn 128 token (khoảng 600 ký tự) sẽ cắt ngầm chunk của B. Không chunk nào vượt 512 token (lớn nhất: A 150, B 277), và code từ chối nếu có chunk vượt.
  - **Vector store:** PostgreSQL 16.16 + pgvector 0.8.7 (Docker). Metric cosine `<=>`, **exact search** (không dùng index ANN, để filter không làm giảm recall).
  - **Lệnh chạy:** `python -m src.run ingest | evaluate --split dev | select | evaluate --split test`.
  - **Chi phí:** **0 USD**, không gọi API.
  - Phiên bản: [versions.txt](../../starter/results/versions.txt).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Mỗi chunk có `document_id`, `source`, `page` (int), `chapter` (int, **trường lọc**), `chapter_title`, `section` và `start_char`/`end_char` (vị trí chính xác trong trang).
  - **Nguồn giá trị:** chapter và section lấy từ **outline do nhà xuất bản nhúng trong PDF**, không tự đoán.
  - **Lý do chọn `chapter`:** 3 giá trị phân biệt được, và có nhiều cặp khái niệm xuất hiện ở hai chương với đáp án khác nhau.
  - **Lưu ý về `section`:** ở A, section lấy theo ký tự đầu của cửa sổ, nên có thể sai khi cửa sổ nằm vắt qua hai mục. Ở B, section chính xác vì chunk không bao giờ vắt qua hai mục.

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** cửa sổ 500 ký tự, overlap 50, trong phạm vi từng trang, không lọc → 521 chunk.
  - **B:** theo đoạn văn và heading, tối đa 1000 ký tự (mềm: heading có thể đứng trước một thân ≤1000), ghép 61 đoạn bị cắt, tách theo câu nếu một đoạn >1000, không lọc → 326 chunk.
  - **C:** **dùng lại đúng index B**. **Khác biệt duy nhất giữa B và C** là `WHERE chapter = N`, chỉ áp dụng cho 5 câu có filter.
  - Cả ba dùng cùng corpus, model, store, metric và bộ câu hỏi. Cấu hình nằm trong [src/config.py](../../starter/src/config.py) và [experiment_log.csv](../../artifacts/experiment_log.csv).
- **Bộ câu hỏi:** 22 câu tiếng Anh (cùng ngôn ngữ với corpus, để không trộn lỗi truy xuất xuyên ngôn ngữ), **16 dev / 6 test**.
  - **Loại câu:** dev có 5 trực tiếp, 4 diễn đạt lại, 4 điều kiện, 3 filter; test có 2, 1, 1, 2.
  - **Cách tách:** theo mục. Test chỉ lấy từ các mục 3.4, 4.2, 14.3, 14.5, mà không câu dev nào dùng.
  - **Câu có filter:** **5 câu** (q05, q09, q13 ở dev; q18, q19 ở test). Filter `{"chapter": N}` là **input giả định "người học đang học chương N"**, có trước khi truy xuất. Các distractor khác chương đã được **dự đoán và ghi lại trước khi chạy**.
  - **Kiểm chứng evidence:** `scripts/verify_benchmark.py` xác nhận 22/22 evidence có trên trang gold sau chuẩn hóa, filter không loại mất trang gold, và không câu hỏi nào trùng 8 từ liên tiếp với evidence. Có `alt_gold` khi nhiều trang cùng hợp lệ (q04: p71 hoặc p82).
  - Bộ câu hỏi được khóa ở commit `edf32b9` **trước mọi lần chạy**. Chi tiết: [benchmark/README.md](../../benchmark/README.md).
- **Tiêu chí chọn chiến lược (chốt trước khi xem test, chỉ dùng dev):**
  1. Hit@3 dev cao nhất, coi chênh ≤1 câu là hòa.
  2. Hit@1 dev.
  3. Ít chunk hơn.
  4. C thay B nếu Hit@3 trên các câu filter của dev không thấp hơn.

  Code từ chối chạy test khi chưa có `selection.json`. Lựa chọn C được commit ở `b073092`; test chạy **một lần** sau đó (`f81eec1`).

## Kết quả

Định nghĩa hit (chốt trước): chunk thuộc trang gold (hoặc `alt_gold`) **và** chứa trọn evidence sau chuẩn hóa. Evidence bị cắt qua hai chunk thì không tính là hit.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 8/16 | 9/16 | 521 | ingest 71.9 s (embed 70.2 s); truy vấn trung bình 57 ms | 0 USD |
| B | dev | 7/16 | 8/16 | 326 | ingest 61.4 s (embed 60.1 s); 45 ms | 0 USD |
| C | dev | 8/16 | 9/16 | 326 (index B) | không ingest thêm; 43 ms | 0 USD |
| A | test | 2/6 | 2/6 | 521 | 72 ms | 0 USD |
| B | test | 4/6 | 4/6 | 326 | 49 ms | 0 USD |
| **C** | test | 4/6 | **5/6** | 326 | 43 ms | 0 USD |

**Riêng các câu filter (Hit@3):**

| Split | A | B | C |
|---|---|---|---|
| dev | 0/3 | 0/3 | 1/3 |
| test | 0/2 | 1/2 | 2/2 |

- **Nạp lại cùng corpus:** 0 chunk embed lại, 0 dòng mới, `count(*) = count(DISTINCT chunk_id)`.
- **Tài liệu bị sửa** (mô phỏng p85 trong namespace riêng): 2 chunk cập nhật, 2 chunk cũ bị xóa, 5 giữ nguyên.
- Thời gian là một lần chạy trên CPU laptop, chỉ mang tính tham khảo. Thời gian truy vấn bao gồm cả việc mở kết nối DB cho mỗi truy vấn.

**Chỉ số phụ: Hit có tính bằng chứng tương đương.** GUIDE tính hit khi chunk chứa evidence đã ghi *"hoặc bằng chứng tương đương được người chấm xác nhận"*. Chỉ số chính ở trên dùng định nghĩa chặt, chốt trước khi chạy, và **không thay đổi**. Bảng dưới tính lại từ chính các trace, cộng thêm các câu tương đương trong [equivalent_evidence.jsonl](../../starter/results/audit/equivalent_evidence.jsonl):
- Các câu này được thêm **sau khi xem kết quả**: hiện chỉ có 1 câu cho q21 ở p348, phát hiện khi chấm grounding.
- Chúng chỉ được tính khi học viên xác nhận (`confirmed_by_student = "yes"`). Câu q21 được xác nhận qua bước kiểm duyệt: học viên chấp nhận grounding q21 B/C = 2, và ghi chú kiểm duyệt trích đúng câu này.
- Áp dụng như nhau cho mọi chiến lược.

<!-- EQUIV_TABLE_START -->
| Split | Strategy | Hit@1 chặt | Hit@3 chặt | Hit@1 + tương đương | Hit@3 + tương đương |
|---|---|---|---|---|---|
| dev | A | 8/16 | 9/16 | 8/16 | 9/16 |
| dev | B | 7/16 | 8/16 | 7/16 | 8/16 |
| dev | C | 8/16 | 9/16 | 8/16 | 9/16 |
| test | A | 2/6 | 2/6 | 2/6 | 2/6 |
| test | B | 4/6 | 4/6 | 4/6 | 5/6 |
| test | C | 4/6 | 5/6 | 4/6 | 6/6 |

_Bằng chứng tương đương đã được học viên xác nhận: ['q21']. Các ô thay đổi: ['test q21 B rank 2 p348', 'test q21 C rank 2 p348']. Sinh bởi `python -m scripts.equivalent_hits`._
<!-- EQUIV_TABLE_END -->

<!-- AUDIT_TABLE_START -->
| Strategy | Coherence /2 (0/1/2) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding /2 (0/1/2): LLM → **sau kiểm duyệt** |
|---|---|---|---|---|
| A | 1.00/2 (0/10/0) | 18/18 | 0/2 (không áp filter; chẩn đoán) | 1.33/2 (1/2/3) |
| B | 1.70/2 (0/3/7) | 18/18 | 0/2 (không áp filter; chẩn đoán) | 2.00/2 (0/0/6) → **1.83/2 (0/1/5)** |
| C (dùng chunk B) | 1.70/2 (0/3/7) | 18/18 | 2/2 | 2.00/2 (0/0/6) |

_Nguồn: nhãn LLM judge **đã được học viên kiểm duyệt** (chấp nhận hoặc sửa từng mục). Sinh bởi `python -m scripts.summarize_audit` từ `starter/results/audit/`._
<!-- AUDIT_TABLE_END -->

**Trace, nhãn audit và cách chọn mẫu:**
- **Trace đầy đủ** (question, filter, chunk_id, text, score, metadata, cờ hit): [traces/dev.jsonl](../../starter/results/traces/dev.jsonl), [traces/test.jsonl](../../starter/results/traces/test.jsonl). Chỉ số: [metrics_dev.csv](../../starter/results/metrics_dev.csv), [metrics_test.csv](../../starter/results/metrics_test.csv).
- **Quy trình gán nhãn: LLM gán nhãn, học viên kiểm duyệt** (*LLM-assisted annotation with human verification*). File: [starter/results/audit/](../../starter/results/audit/).
  1. **Gán nhãn:** LLM judge (Claude Sonnet 5.5, qua subagent của Claude Code, ngày 13/11/2026) chấm 92 mục (20 coherence, 54 metadata, 18 grounding) theo thang trong GUIDE.md mục 4 (coherence 0/1/2, grounding 0/1/2, metadata Y/N), kèm lý do từng mục. Cột `label_0_1_2`, `reason`, `manual_*` và `notes` trong các file CSV là đầu ra của LLM này.
  2. **Kiểm duyệt:** học viên xem xét toàn bộ 92 nhãn cùng lý do của LLM. Mỗi mục được quyết định là chấp nhận (`accept`, hoặc `audit_pass` với metadata) hay sửa (`modify`). Kết quả: **chấp nhận 91, sửa 1**. Mọi quyết định nằm trong [human_review.csv](../../starter/results/audit/human_review.csv), gồm các cột `llm_label`, `final_label`, `decision`, `reviewer_note`, `label_source` và `review_method`.
  3. **Nhãn cuối** = nhãn LLM, trừ mục học viên đã sửa. Bảng trên ghi cả trước và sau kiểm duyệt khi hai bên khác nhau. Script kiểm tra `llm_label` trong file kiểm duyệt khớp với file nhãn LLM, và quyết định `modify` phải đi kèm thay đổi nhãn cùng ghi chú.
  4. **Ghi chú kiểm duyệt** (`reviewer_note`, tiếng Việt) được **diễn đạt lại từ lý do của LLM**, như cột `review_method` ghi rõ. Chúng là sản phẩm của bước kiểm duyệt, **không phải chú thích độc lập**. Riêng ghi chú của mục bị sửa là lập luận của học viên.
- **Coherence:** 10 vị trí chốt trước, gồm mỗi trang thứ 8 trong 78 trang đã sắp xếp (p59, 67, 75, 83, 98, 106, 114, 341, 349, 357), vị trí là ký tự giữa trang. C dùng chung chunk với B nên dùng chung nhãn.
- **Metadata và grounding:** 6 câu test × top-3 × 3 chiến lược. Máy kiểm tra trước metadata: 54/54 bản ghi có text nằm đúng trang và chapter/section khớp manifest. Với metadata, người chấm LLM so từng bản ghi với `pages.jsonl` (text nằm đúng vị trí trên trang, chapter theo outline PDF, section theo vị trí heading trong trang) và với text PDF gốc qua PyMuPDF: **cả 54/54 bản ghi** được đối chiếu trực tiếp với trang PDF, kể cả các cửa sổ A nằm sát heading ở p82, p112, p341.
- **Phương pháp LLM judge:** coherence chỉ cho người chấm thấy `chunk_text` và thang điểm, không cho biết chiến lược hay kết quả truy xuất; grounding cho thấy câu hỏi, đáp án tham chiếu, evidence và top-3 text (không phải câu trả lời của LLM), và đánh giá bằng chứng tương đương trên trang khác vẫn được tính; cột proxy tự động `auto_evidence_hit3_proxy` không được sao chép, các chỗ lệch với proxy được ghi trong cột `reason`.
- **Kết quả kiểm duyệt** (sinh tự động từ `human_review.csv`):

<!-- REVIEW_START -->
| Phần | Mục đã kiểm duyệt | Chấp nhận nhãn LLM | Sửa |
|---|---|---|---|
| coherence | 20/20 | 20 | 0 |
| metadata | 54/54 | 54 | 0 |
| grounding | 18/18 | 17 | 1 |

Mục bị sửa: grounding q19 B: 2 → 1. Quyết định ghi trong file: {'accept': 37, 'audit_pass': 54, 'modify': 1}.

_Đây là **tỷ lệ chấp nhận khi kiểm duyệt**, không phải độ đồng thuận giữa hai người chấm độc lập: người kiểm duyệt đã thấy nhãn và lý do của LLM._
<!-- REVIEW_END -->

- **Mục bị sửa, grounding B q19 (2 → 1).** Theo ghi chú của học viên: đoạn ở p84 giải thích đúng nguyên lý giá trần làm lượng cầu vượt lượng cung và gây thiếu hụt. Nhưng đó là ví dụ kiểm soát tiền thuê nhà ở Ch3, không phải ví dụ thị trường thẻ tín dụng ở Ch4 mà câu hỏi hướng tới, nên bằng chứng chỉ hỗ trợ một phần. C lấy được p111 thuộc Ch4.
- **Cách đọc tỷ lệ chấp nhận 91/92:**
  - Đây **không phải độ đồng thuận giữa hai người chấm độc lập**, vì người kiểm duyệt đã thấy nhãn và lý do của LLM. Không tính Cohen's kappa.
  - Khoảng 64/92 mục gần như tất định: cả 10 chunk A bắt đầu giữa từ, và metadata đã được máy kiểm tra trước 54/54. Vì vậy tỷ lệ chấp nhận cao phần lớn phản ánh độ dễ của mục, chứ không chứng minh chất lượng nhãn.
  - Phần cần phán đoán thật là grounding và coherence của B, và chỗ sửa duy nhất nằm đúng ở nhóm này.
  - Rủi ro: thiên lệch tự động hóa (người kiểm duyệt có xu hướng chấp nhận đầu ra của máy).

## Phân tích và kết luận

**So sánh A–B (chỉ đổi cách chunk):**
- **Kết quả trái chiều giữa dev và test.** Dev: A 9/16 ≥ B 8/16. Test: B 4/6 > A 2/6. Hai chiến lược thất bại vì **hai cơ chế khác nhau**:
- **A trượt vì evidence bị cắt.** Trần lý thuyết của A trên dev chỉ là 12/16, vì 4 evidence bị cửa sổ 500 ký tự cắt đôi. Thực tế A trượt 4 câu dev (q08, q10, q11, q12) và 1 câu test (q20) dù **đã lấy đúng trang**. 53% chunk A bắt đầu giữa một từ.
- **B trượt vì pha loãng ngữ nghĩa.** Trần của B là 16/16, nhưng ở 5 câu dev (q01, q04, q05, q12, q14), B lấy đúng trang gold mà **sai chunk**. Chunk chứa evidence (khoảng 700–950 ký tự) xếp hạng thấp hơn một chunk khác cùng trang, vì câu evidence chỉ chiếm một phần nhỏ trong vector của chunk dài.
- **Biến số bị gộp:** A–B đổi cùng lúc *cấu trúc* và *kích thước* (trung vị 500 so với 732 ký tự). Vì vậy không tách được phần nào do cấu trúc, phần nào do kích thước.
- **Thiên lệch trong thiết kế:** evidence là câu trọn vẹn, nên về cấu trúc đã có lợi cho B.
- **Theo nhãn audit:**
  - **Coherence:** trung bình A 1,00/2 (10/10 chunk ở mức 1, đều bắt đầu giữa từ hoặc giữa câu) so với B 1,70/2 (7 chunk mức 2, 3 chunk mức 1 vì đầu đoạn nhắc tới ý phía trước).
  - **Grounding của A:** 1 nhãn 0 (q18: top-3 không nói gì về giá sàn và dư thừa) và 2 nhãn 1 (q19: mệnh đề điều kiện bị cắt giữa từ; q21: chỉ có gợi ý gián tiếp).
  - **Grounding của B:** LLM cho cả 6 câu mức 2. Sau kiểm duyệt, q19 hạ xuống mức 1, nên trung bình còn 1,83/2.
  - **Metadata:** không phát hiện lỗi nào ở 54/54 bản ghi. 10 bản ghi nằm sát heading (p82, p112, p341; gồm cửa sổ A và chunk B) vẫn có section đúng, vì cửa sổ nằm hẳn trước hoặc sau heading. Rủi ro sai section của A vì thế chưa xảy ra trong mẫu này.
- **Lưu ý:** ở q21, grounding của B/C là 2, vì chunk hạng 2 (p348) nêu rõ lượng lao động thuê ở mức lương công đoàn nhỏ hơn mức cân bằng. Dù vậy, Evidence Hit@3 chặt của q21 vẫn tính là trượt (xem chỉ số phụ "bằng chứng tương đương" ở phần Kết quả).

**Thí nghiệm hậu kiểm B500: tách *cấu trúc* khỏi *kích thước* (chỉ chạy trên dev, KHÔNG dùng để chọn chiến lược):**
- **Thiết kế:** thêm sau khi đã xem kết quả dev và test, để trả lời câu hỏi mà cặp A–B để ngỏ. B500 giống hệt B (theo đoạn và heading, ghép đoạn bị cắt) nhưng tối đa 500 ký tự. Kết quả: 628 chunk, trung vị 374 ký tự, tối đa 540, trần evidence dev 16/16. Code **từ chối chạy ablation trên test**, vì test đã dùng rồi. File: [traces/ablation_dev.jsonl](../../starter/results/traces/ablation_dev.jsonl), [metrics_ablation_dev.csv](../../starter/results/metrics_ablation_dev.csv).
- **Kết quả dev:**

  | Cấu hình | Hit@1 | Hit@3 | Chunk |
  |---|---|---|---|
  | A | 8/16 | 9/16 | 521 |
  | B | 7/16 | 8/16 | 326 |
  | **B500** | **10/16** | **13/16** | 628 |

  Khi chạy lại cùng lượt, A và B cho top-3 **giống hệt** lần chạy gốc, tức pipeline tất định.
- **Diễn giải:**
  - So với B, B500 cứu thêm 5 câu (q01, q03, q04, q12, q14) và không mất câu nào. Chính các câu B trượt vì "đúng trang, sai chunk" (q01, q04, q12, q14) giờ thành hit. Điều này ủng hộ giả thuyết **pha loãng ngữ nghĩa** ở chunk dài.
  - So với A, B500 hơn 4 câu, nhờ không cắt evidence (q08, q10, q11, q12 không còn trượt vì evidence bị cắt).
  - Vậy trên corpus này, **cấu trúc có ích khi kích thước nhỏ**. Cặp A–B gốc kém vì B quá dài, không phải vì chia theo đoạn.
- **Giới hạn:**
  - Đây là kết quả hậu kiểm trên dev: không có test độc lập, và mẫu chỉ 16 câu.
  - B500 có kích thước *nhỏ hơn hoặc bằng* A, chứ không bằng đúng A (trung vị 374 so với 500), nên vẫn còn một phần nhiễu do kích thước.
  - B500 vẫn trượt cả 3 câu filter dev. Bổ sung filter cho B500 là bước tiếp theo, chưa được kiểm chứng.
  - **Lựa chọn chính thức vẫn là C** theo quy tắc đã chốt trước.

**So sánh B–C (chỉ đổi filter):**
- C ≥ B ở mọi tập con: dev 9/16 so với 8/16, test 5/6 so với 4/6. Toàn bộ chênh lệch nằm ở các câu filter, vì C giống hệt B ở câu không có filter.
- **Grounding B và C:**
  - Trước kiểm duyệt (nhãn LLM), cả hai đều 6/6 mức 2, nên không có khác biệt.
  - Sau kiểm duyệt, B q19 chỉ được 1, vì evidence của B thuộc Ch3, ngoài ngữ cảnh Ch4 của câu hỏi. C q19 vẫn được 2, vì C lấy được p111 của Ch4. Kết quả: B 1,83/2, C 2,00/2.
  - Như vậy, khác biệt grounding giữa B và C nằm đúng ở câu filter mà C được thiết kế để sửa, khớp với chênh lệch Evidence Hit@3 trên q19.
- **Distractor dự đoán trước đã thực sự xuất hiện** ở q05 (A), q09 (A, B), q13 (A, B), q19 (A, B).
- Filter **không** cứu được q05 và q09: lỗi ở đó là xếp hạng **trong cùng chương**, không phải nhầm chương. Ở q09, C lấy p105 (lương tối thiểu *dưới* mức cân bằng) thay vì p104 (living wage *trên* mức cân bằng).

**Hai ví dụ sai cụ thể:**
1. **q19 (test, B), nhầm chương:** "What happens when a price ceiling is set below the equilibrium price?" với filter chương 4.
   - B (không lọc) xếp **p84, Ch3** (rent control: *"quantity demanded exceeds quantity supplied, and thus a shortage occurs"*) lên top-1. Đoạn này đúng về kinh tế học nhưng sai phạm vi; trang gold p111 (thẻ tín dụng, usury law) không có trong top-3.
   - C lọc `chapter=4` và lấy được p111 ở hạng 3, kèm evidence *"At the price ceiling (Rc), quantity demanded will exceed quantity supplied."*
2. **q12 (dev, B và C), pha loãng ngữ nghĩa:** "What is the first rule of labor markets?"
   - B/C top-1 là `micro3e-p0336-pb1000-004` (*"What is the labor market?…"*): đúng trang p336 nhưng sai chunk.
   - Chunk chứa định nghĩa (`…-005`, 946 ký tự) không vào top-3.
   - A cũng trượt câu này, nhưng vì lý do khác: cửa sổ A cắt đôi câu evidence (*"…nefits) for a worker than the value of their marginal productivity…"*).

Thêm một ví dụ: **q21 (test)** trượt Evidence Hit@3 ở cả 3 chiến lược. B/C lấy p348, nhưng top-1 là chunk về năng suất của công nhân công đoàn, và không chunk nào chứa nguyên câu evidence "hire less labor". Chunk hạng 2 (p348) có câu tương đương (Qd < Qe), nên grounding được 2 dù hit theo định nghĩa chặt là trượt. Khi tính cả bằng chứng tương đương đã xác nhận, q21 thành hit với B và C (test Hit@3: B 5/6, C 6/6). Đây là ví dụ về chỗ Hit@3 chặt đánh giá thấp chất lượng bằng chứng. Câu hỏi diễn đạt lại (paraphrase) vẫn là điểm yếu chung.

**Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
- **Chọn C theo quy tắc đã chốt:** hòa ở Hit@3 và Hit@1 trong ngưỡng ±1 câu → ít chunk hơn (326 so với 521) → thắng B trên câu filter.
- **Đánh đổi:**
  - So với A, C/B tốn ít tài nguyên hơn (ít hơn 37% chunk, embed nhanh hơn khoảng 14%, lưu ít hơn khoảng 10% ký tự vì không có overlap) và không cắt evidence. Đổi lại, chunk dài bị pha loãng ngữ nghĩa.
  - Filter chỉ có ích khi **ngữ cảnh người dùng đúng**. Trong smoke test (câu ngoài benchmark), lọc sai `chapter=14` đã loại mất câu trả lời tốt nhất ở Ch4.
- **Điều kiện áp dụng:** khi ứng dụng biết chắc phạm vi (người học đang ở chương nào) và tài liệu có các khái niệm lặp lại giữa các phạm vi. Không suy rộng ra ngoài corpus này.

**Hạn chế:**
- **Mẫu nhỏ:** 16 dev, 6 test, 5 câu filter. Một câu tương đương 6,25 điểm % trên dev và 16,7 điểm % trên test. Không chênh lệch nào ở đây có ý nghĩa thống kê.
- **Câu hỏi:** do tác giả viết khi đã biết trang gold, nên cách diễn đạt có thể vô tình thuận lợi cho truy xuất. q09 (dev) và q18 (test) cùng nói về giá sàn, nên có rò rỉ nhẹ (đã ghi lại).
- **Nhãn:**
  - Chỉ có một người gán nhãn chính là LLM judge. Học viên kiểm duyệt nhưng đã thấy nhãn và lý do của LLM, nên đây **không phải chú thích độc lập**: không đo được độ đồng thuận giữa hai người chấm, và có rủi ro thiên lệch tự động hóa.
  - Tỷ lệ chấp nhận 91/92 phần lớn đến từ các mục gần như tất định, nên không chứng minh được chất lượng nhãn.
  - Các trường hợp ranh giới phụ thuộc người chấm. Ví dụ B q19: LLM cho 2, người kiểm duyệt cho 1, vì evidence nằm ở chương khác với ngữ cảnh câu hỏi.
- **Đo thời gian:** một lần chạy, trên CPU, có tính cả thời gian mở kết nối DB.
- **Bỏ qua hình:** nội dung trong đồ thị không được trích. Câu nằm vắt qua hai trang bị cắt.

**Nếu làm lại hoặc mở rộng:**
1. **Xác nhận B500 trên bộ test mới.** Trên dev, B500 đã cho thấy tín hiệu mạnh (13/16 so với 8/16 của B). Bước tiếp theo là chốt trước cấu hình "B500 + filter chương" như một ứng viên, viết bộ test mới chưa ai xem, rồi chạy một lần.
2. Ghép câu vắt qua hai trang bằng chunk có `page_start`/`page_end`, kèm định nghĩa hit theo khoảng trang.
3. Thêm tiền tố ngữ cảnh (tên chương/mục) khi embed để giảm pha loãng; hoặc hybrid BM25 + dense cho các câu có từ khóa đặc thù như "first rule".
4. Mở rộng lên 50 câu trở lên. Cho hai người chấm làm **mù hoàn toàn**: không thấy nhãn hay tổng hợp của nhau, và không biết chunk thuộc chiến lược nào. Sau đó báo Cohen's kappa.

**Sử dụng AI:** dùng Claude Code (Claude Opus 5.5) để giải thích, viết code pipeline và soạn nháp báo cáo.
- **Cách kiểm tra:** evidence kiểm chứng tự động trên text đã chuẩn hóa; self-check chunk (offset chính xác, không mất ký tự); kiểm tra nạp lại và sửa tài liệu; đọc lại trace của từng ca trượt để xác nhận đó là lỗi truy xuất thật, không phải lỗi code đánh giá.
- **Nhãn coherence, metadata và grounding** do một LLM judge chấm (Claude Sonnet 5.5, qua subagent của Claude Code, ngày 13/11/2026) theo thang trong GUIDE.md mục 4, kèm lý do từng nhãn; phương pháp, đầu vào của người chấm và rủi ro được mô tả ở mục "Trace, nhãn audit và cách chọn mẫu". Metadata được LLM đối chiếu với `pages.jsonl` và với PDF (54/54 bản ghi). Học viên kiểm duyệt toàn bộ 92 nhãn (chấp nhận 91, sửa 1) và ghi quyết định vào `human_review.csv`. Ghi chú tiếng Việt trong file được diễn đạt lại từ lý do của LLM. Bảng nhãn và tỷ lệ chấp nhận do script tính, không ghi tay. Thí nghiệm hậu kiểm B500 và chỉ số "bằng chứng tương đương" do Claude Code đề xuất và chạy, sau khi đã có kết quả; cả hai được đánh dấu rõ là phân tích phụ.
