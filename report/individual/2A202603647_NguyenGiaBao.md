# Báo cáo cá nhân — Day 6 · Data Ingestion

**Học viên:** Nguyễn Gia Bảo · **MSSV:** 2A202603647 · **Lớp:** K5-L3A
**Corpus:** OpenStax *Principles of Microeconomics 3e*, Ch3, Ch4, Ch14 · **Chiến lược chọn:** C (đoạn văn + lọc theo chương)

> Mọi số liệu dưới đây lấy từ file trong repo, đường dẫn ghi tại chỗ. Lệnh tái lập nằm ở [README.md](../../README.md#bài-làm--cách-chạy-lại).

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

<!-- AUDIT_TABLE_START -->
| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding 0/1/2 và trung bình /2 |
|---|---|---|---|---|
| A | 1.00/2 (n=10; 0/1/2 = 0/10/0) | 18/18 | 0/2 (filter not applied; diagnostic) | 1.33/2 (n=6; 0/1/2 = 1/2/3) |
| B | 1.70/2 (n=10; 0/1/2 = 0/3/7) | 18/18 | 0/2 (filter not applied; diagnostic) | 2.00/2 (n=6; 0/1/2 = 0/0/6) |
| C (dùng chunk B) | 1.70/2 (n=10; 0/1/2 = 0/3/7) | 18/18 | 2/2 | 2.00/2 (n=6; 0/1/2 = 0/0/6) |

_Bảng do `python -m scripts.summarize_audit` sinh từ nhãn trong `starter/results/audit/` (người chấm và phương pháp: xem mục ngay dưới)._
<!-- AUDIT_TABLE_END -->

**Trace, nhãn thủ công và cách chọn mẫu:**
- **Trace đầy đủ** (question, filter, chunk_id, text, score, metadata, cờ hit): [traces/dev.jsonl](../../starter/results/traces/dev.jsonl), [traces/test.jsonl](../../starter/results/traces/test.jsonl). Chỉ số: [metrics_dev.csv](../../starter/results/metrics_dev.csv), [metrics_test.csv](../../starter/results/metrics_test.csv).
- **Nhãn (coherence, metadata, grounding):** [starter/results/audit/](../../starter/results/audit/). **Các nhãn này do một LLM làm người chấm (Claude Sonnet 5.5, qua subagent của Claude Code, ngày 13/11/2026), không phải do học viên tự chấm.** Người chấm theo thang trong GUIDE.md mục 4 (coherence 0/1/2, grounding 0/1/2, metadata Y/N) và ghi lý do cho từng nhãn. Cột `label_0_1_2`, `reason`, `manual_*` và `notes` trong các file CSV là đầu ra của LLM này.
- **Coherence:** 10 vị trí chốt trước, gồm mỗi trang thứ 8 trong 78 trang đã sắp xếp (p59, 67, 75, 83, 98, 106, 114, 341, 349, 357), vị trí là ký tự giữa trang. C dùng chung chunk với B nên dùng chung nhãn.
- **Metadata và grounding:** 6 câu test × top-3 × 3 chiến lược. Máy kiểm tra trước metadata: 54/54 bản ghi có text nằm đúng trang và chapter/section khớp manifest. Với metadata, người chấm LLM so từng bản ghi với `pages.jsonl` (text nằm đúng vị trí trên trang, chapter theo outline PDF, section theo vị trí heading trong trang) và với text PDF gốc qua PyMuPDF: **cả 54/54 bản ghi** được đối chiếu trực tiếp với trang PDF, kể cả các cửa sổ A nằm sát heading ở p82, p112, p341.
- **Phương pháp LLM judge:** coherence chỉ cho người chấm thấy `chunk_text` và thang điểm, không cho biết chiến lược hay kết quả truy xuất; grounding cho thấy câu hỏi, đáp án tham chiếu, evidence và top-3 text (không phải câu trả lời của LLM), và đánh giá bằng chứng tương đương trên trang khác vẫn được tính; cột proxy tự động `auto_evidence_hit3_proxy` không được sao chép, các chỗ lệch với proxy được ghi trong cột `reason`.
- **Rủi ro:** thiên lệch của LLM judge (có thể quá dễ dãi hoặc không nhất quán), chỉ một người chấm, không đo được độ đồng thuận giữa người chấm, và không có người thứ hai kiểm tra.
- **Học viên xem xét lại nhãn:** _(chưa / đã — ghi số nhãn đã sửa)_

## Phân tích và kết luận

**So sánh A–B (chỉ đổi cách chunk):**
- **Kết quả trái chiều giữa dev và test.** Dev: A 9/16 ≥ B 8/16. Test: B 4/6 > A 2/6. Hai chiến lược thất bại vì **hai cơ chế khác nhau**:
- **A trượt vì evidence bị cắt.** Trần lý thuyết của A trên dev chỉ là 12/16, vì 4 evidence bị cửa sổ 500 ký tự cắt đôi. Thực tế A trượt 4 câu dev (q08, q10, q11, q12) và 1 câu test (q20) dù **đã lấy đúng trang**. 53% chunk A bắt đầu giữa một từ.
- **B trượt vì pha loãng ngữ nghĩa.** Trần của B là 16/16, nhưng ở 5 câu dev (q01, q04, q05, q12, q14), B lấy đúng trang gold mà **sai chunk**. Chunk chứa evidence (khoảng 700–950 ký tự) xếp hạng thấp hơn một chunk khác cùng trang, vì câu evidence chỉ chiếm một phần nhỏ trong vector của chunk dài.
- **Biến số bị gộp:** A–B đổi cùng lúc *cấu trúc* và *kích thước* (trung vị 500 so với 732 ký tự). Vì vậy không tách được phần nào do cấu trúc, phần nào do kích thước.
- **Thiên lệch trong thiết kế:** evidence là câu trọn vẹn, nên về cấu trúc đã có lợi cho B.
- **Theo nhãn audit (LLM judge):** coherence trung bình A 1,00/2 (10/10 chunk ở mức 1, đều bắt đầu giữa từ hoặc giữa câu) so với B 1,70/2 (7 chunk mức 2, 3 chunk mức 1 vì thiếu ngữ cảnh ở đầu đoạn). Grounding A có 1 nhãn 0 (q18, top-3 không nói gì về giá sàn/dư thừa) và 2 nhãn 1 (q19 do mệnh đề điều kiện bị cắt giữa từ; q21 chỉ có gợi ý gián tiếp về mất việc), còn B toàn nhãn 2. Metadata không phát hiện lỗi nào ở 54/54 bản ghi; riêng 10 bản ghi nằm sát heading (p82, p112, p341; gồm các cửa sổ A và chunk B) có section đúng vì cửa sổ nằm hẳn trước hoặc sau heading, nên rủi ro sai section của A chưa xảy ra trong mẫu này.
- **Lưu ý:** ở q21 grounding của B/C là 2 vì chunk hạng 2 (p348) nêu rõ lượng lao động thuê ở mức lương công đoàn nhỏ hơn mức cân bằng, dù Evidence Hit@3 của q21 vẫn là trượt (các con số Hit giữ nguyên).

**So sánh B–C (chỉ đổi filter):**
- C ≥ B ở mọi tập con: dev 9/16 so với 8/16, test 5/6 so với 4/6. Toàn bộ chênh lệch nằm ở các câu filter, vì C giống hệt B ở câu không có filter.
- **Nhãn grounding B và C đều là 6/6 mức 2 (trung bình 2,00/2), nên theo nhãn không có khác biệt grounding giữa B và C; khác biệt chỉ nằm ở Evidence Hit@3 tự động (q19).**
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

Thêm một ví dụ: **q21 (test)** trượt Evidence Hit@3 ở cả 3 chiến lược. B/C lấy p348, nhưng top-1 là chunk về năng suất của công nhân công đoàn, và không chunk nào chứa nguyên câu evidence "hire less labor". Chunk hạng 2 (p348) có câu tương đương (Qd < Qe), nên grounding được 2 dù hit theo định nghĩa chặt là trượt. Đây là ví dụ về chỗ Hit@3 tự động đánh giá thấp chất lượng bằng chứng. Câu hỏi diễn đạt lại (paraphrase) vẫn là điểm yếu chung.

**Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
- **Chọn C theo quy tắc đã chốt:** hòa ở Hit@3 và Hit@1 trong ngưỡng ±1 câu → ít chunk hơn (326 so với 521) → thắng B trên câu filter.
- **Đánh đổi:**
  - So với A, C/B tốn ít tài nguyên hơn (ít hơn 37% chunk, embed nhanh hơn khoảng 14%, lưu ít hơn khoảng 10% ký tự vì không có overlap) và không cắt evidence. Đổi lại, chunk dài bị pha loãng ngữ nghĩa.
  - Filter chỉ có ích khi **ngữ cảnh người dùng đúng**. Trong smoke test (câu ngoài benchmark), lọc sai `chapter=14` đã loại mất câu trả lời tốt nhất ở Ch4.
- **Điều kiện áp dụng:** khi ứng dụng biết chắc phạm vi (người học đang ở chương nào) và tài liệu có các khái niệm lặp lại giữa các phạm vi. Không suy rộng ra ngoài corpus này.

**Hạn chế:**
- **Mẫu nhỏ:** 16 dev, 6 test, 5 câu filter. Một câu tương đương 6,25 điểm % trên dev và 16,7 điểm % trên test. Không chênh lệch nào ở đây có ý nghĩa thống kê.
- **Câu hỏi:** do tác giả viết khi đã biết trang gold, nên cách diễn đạt có thể vô tình thuận lợi cho truy xuất. q09 (dev) và q18 (test) cùng nói về giá sàn, nên có rò rỉ nhẹ (đã ghi lại).
- **Nhãn:** do một LLM judge (Claude Sonnet 5.5) chấm, chỉ một người chấm, không đo được độ đồng thuận giữa người chấm; nhãn chưa được người thật xem xét trừ khi học viên điền dòng "Học viên xem xét lại nhãn" ở trên. Bảng nhãn có thể lệch theo thiên lệch của LLM judge (ví dụ cho điểm grounding 2 khi bằng chứng tương đương nằm ở trang khác).
- **Đo thời gian:** một lần chạy, trên CPU, có tính cả thời gian mở kết nối DB.
- **Bỏ qua hình:** nội dung trong đồ thị không được trích. Câu nằm vắt qua hai trang bị cắt.

**Nếu làm lại hoặc mở rộng:**
1. Thêm cấu hình **B500**: theo đoạn nhưng tối đa 500 ký tự, để tách riêng ảnh hưởng của *cấu trúc* và *kích thước*. Thí nghiệm này phải chạy trên bộ test mới; nếu chạy trên test hiện tại thì phải ghi rõ là phân tích hậu kiểm.
2. Ghép câu vắt qua hai trang bằng chunk có `page_start`/`page_end`, kèm định nghĩa hit theo khoảng trang.
3. Thêm tiền tố ngữ cảnh (tên chương/mục) khi embed để giảm pha loãng; hoặc hybrid BM25 + dense cho các câu có từ khóa đặc thù như "first rule".
4. Mở rộng lên 50 câu trở lên và có người chấm thứ hai để đo độ đồng thuận.

**Sử dụng AI:** dùng Claude Code (Claude Opus 5.5) để giải thích, viết code pipeline và soạn nháp báo cáo.
- **Cách kiểm tra:** evidence kiểm chứng tự động trên text đã chuẩn hóa; self-check chunk (offset chính xác, không mất ký tự); kiểm tra nạp lại và sửa tài liệu; đọc lại trace của từng ca trượt để xác nhận đó là lỗi truy xuất thật, không phải lỗi code đánh giá.
- **Nhãn coherence, metadata và grounding** do một LLM judge chấm (Claude Sonnet 5.5, qua subagent của Claude Code, ngày 13/11/2026) theo thang trong GUIDE.md mục 4, kèm lý do từng nhãn; phương pháp, đầu vào của người chấm và rủi ro được mô tả ở mục "Trace, nhãn thủ công và cách chọn mẫu". Metadata được đối chiếu với `pages.jsonl` và với PDF (54/54 bản ghi). Học viên cần xem xét lại nhãn; trạng thái xem xét ghi ở mục đó.
