| Strategy | Coherence /2 (0/1/2) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding /2 (0/1/2): LLM → **sau kiểm duyệt** |
|---|---|---|---|---|
| A | 1.00/2 (0/10/0) | 18/18 | 0/2 (không áp filter; chẩn đoán) | 1.33/2 (1/2/3) |
| B | 1.70/2 (0/3/7) | 18/18 | 0/2 (không áp filter; chẩn đoán) | 2.00/2 (0/0/6) → **1.83/2 (0/1/5)** |
| C (dùng chunk B) | 1.70/2 (0/3/7) | 18/18 | 2/2 | 2.00/2 (0/0/6) |

_Nguồn: nhãn LLM judge **đã được học viên kiểm duyệt** (chấp nhận hoặc sửa từng mục). Sinh bởi `python -m scripts.summarize_audit` từ `starter/results/audit/`._

| Phần | Mục đã kiểm duyệt | Chấp nhận nhãn LLM | Sửa |
|---|---|---|---|
| coherence | 20/20 | 20 | 0 |
| metadata | 54/54 | 54 | 0 |
| grounding | 18/18 | 17 | 1 |

Mục bị sửa: grounding q19 B: 2 → 1. Quyết định ghi trong file: {'accept': 37, 'audit_pass': 54, 'modify': 1}.

_Đây là **tỷ lệ chấp nhận khi kiểm duyệt**, không phải độ đồng thuận giữa hai người chấm độc lập: người kiểm duyệt đã thấy nhãn và lý do của LLM._
