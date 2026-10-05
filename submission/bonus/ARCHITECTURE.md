# Bonus A — Lakehouse cho LLM observability ở quy mô 1B requests/ngày

**Nguyễn Tất Đạt · 2A202602578 · K4-Track02-Day18**  
Architecture brief cá nhân · 04/10/2026 · Thiết kế đề xuất, chưa triển khai cloud.

## 1. Problem statement

Hệ thống ghi một tỷ request/response mỗi ngày, trung bình 5 KB/request,
tương đương 5 TB raw/ngày. Dashboard cost và latency theo tenant phải cập nhật
trong năm phút. Nội dung prompt/response phục vụ incident review được giữ bảy ngày;
sau đó chỉ giữ aggregates một năm. PII phải được redaction trước khi người dùng đọc.
Storage có cap 5,000 USD/tháng.

Khó khăn nằm ở retries, ingest liên tục, metadata/file nhỏ, kiểm soát tenant và
các bản sao payload trong lịch sử. Chọn format nhanh chưa đủ: pipeline phải có
idempotency, retention đo được và phép tính chi phí bao gồm file chưa thu hồi.
Thiết kế chọn Delta trên S3, Spark micro-batch và Glue Data Catalog; dashboard đọc
Gold, incident service đọc dữ liệu đã redaction với quyền riêng.

### Giả định cần chốt khi design review

- 100,000 tenants, ba model; peak bằng 3× average. Đơn vị decimal: 1 TB=1,000 GB.
- Average: `1e9/86,400≈11,574 requests/s`, `5 TB/86,400≈57.9 MB/s`;
  peak khoảng 34,722 requests/s và 173.6 MB/s, trước compression.
- "Nội dung đầy đủ" là nội dung sau redaction, không giữ nguyên PII hoặc kho đảo token.
  Nếu bắt buộc khôi phục PII nguyên văn, phải thay đổi yêu cầu governance và threat model.
- Horizon đọc payload là 168 giờ, theo timestamp UTC. Physical purge có SLO tối đa
  một giờ sau expiry. Nếu đề yêu cầu tuyệt đối không tồn tại byte payload sau đúng
  168 giờ, thiết kế này **chưa đáp ứng**; đó là điều kiện phải giải quyết trước production,
  không tự coi SLO purge là tương đương hard deadline.
- Một region, không replicate payload sang region khác; storage cap và compute budget là hai khoản riêng.

### Một architecture diagram

```text
API request/response
       |
       v
Privacy gateway: redact + tenant token + policy_version (fail closed)
       |
       v
Kafka: sanitized events, bounded replay <=24h
       |
       v
Spark micro-batch <=60s + durable checkpoint
       |
       v
BRONZE Delta: sanitized payload, UTC date/hour, expiry_at, 7d
       |
       v
SILVER Delta: typed metrics, dedup request_id, payload logical key, 7d
       |
       v
GOLD Delta: tenant/model/5min + daily aggregates, 365d
       |                                     |
       v                                     v
Dashboard API: tenant-scoped cache       Incident API -> Silver/Bronze

Glue Catalog + IAM/Lake Formation -> registered tables + access policies
Maintenance -> compact, Z-order, checkpoints, guarded purge/orphan sweep
Audit -> reader identity, run_id, source offsets, table versions, expiry log
```

Diagram áp dụng medallion, ACID/idempotency, clustering, catalog/governance,
version provenance và retention/FinOps vào các đường ingest/query cụ thể.

<div style="break-after: page;"></div>

## 2. Các quyết định và alternatives bị loại

| Quyết định chọn | Alternative bị loại 1 | Alternative bị loại 2 |
|---|---|---|
| **Delta + Spark**, single writer owner cho mỗi bảng; MERGE Silver/Gold và version audit. Workload chính là retries và thay đổi aggregates. | **Parquet thuần:** không có transaction log để commit nguyên tử hoặc xử lý retry MERGE nhất quán; phải tự xây protocol. | **Iceberg cho bản đầu:** có catalog/schema evolution tốt, nhưng yêu cầu hiện tại chưa cần đa engine hoặc partition evolution; thêm cơ chế commit/maintenance phải kiểm thử mà không giải quyết thêm constraint bắt buộc. Chọn lại nếu multi-engine thành yêu cầu. |
| **Glue Data Catalog**, IAM ở object layer và Lake Formation cho đường đọc được hỗ trợ; schema registration được kiểm soát qua deployment. | **SQLite SqlCatalog của lab:** phù hợp local nhưng không là service quản trị shared production cho 100K tenants. | **Self-host Hive Metastore:** team phải vận hành DB/HA/backup; trong scope AWS một region, lợi ích portability chưa bù chi phí vận hành. |
| **Bronze/Silver partition theo UTC date/hour**, Z-order tenant/request trong partition đã ổn định; target files 256 MB. Gold partition theo ngày, cluster tenant/model. | **Partition tenant_id:** 100K tenant tạo quá nhiều partition/file nhỏ, làm tăng listing và planning. | **Chỉ partition model:** ba partition rất lớn; query incident theo thời gian không có time pruning và khó expiry theo tuổi. |
| **Payload chỉ nằm ở Bronze Parquet**, Silver lưu metrics khoảng 500 B/request và logical key; dùng ZSTD nếu engine benchmark xác nhận lợi ích, target compression 4×. | **Sao chép full payload vào Silver:** gần gấp đôi working set và thêm bề mặt redaction/purge; metrics query không cần body. | **Một S3 object cho mỗi request:** ở 1B/ngày, request charges và inventory khổng lồ; random access thuận tiện không bù được chi phí. Không dùng physical file offset làm payload key vì compaction đổi file. |
| **S3 Standard cho cửa sổ payload bảy ngày và Gold một năm**, delete thay vì archive body; chỉ compact phần mới, không rewrite toàn bộ bảy ngày hàng ngày. | **Standard-IA cho payload:** minimum duration 30 ngày không hợp cửa sổ bảy ngày, còn thêm retrieval charges. | **Glacier cho payload hết hạn:** vẫn giữ nội dung sau thời hạn, trái với mục tiêu chỉ giữ aggregates; restore còn tăng incident latency. |
| **Privacy gateway trước Bronze/broker**, tenant-scoped API, least privilege, audit và expiry-aware read; quarantine chỉ sanitized metadata. | **Redact ở Gold:** Bronze, broker hoặc incident query vẫn có thể lộ PII trước khi xử lý. | **Chỉ mã hóa S3:** encryption không ngăn principal có quyền decrypt đọc PII; không thay thế redaction/tenant authorization. |

AWS có tài liệu cho Delta read/write và registration qua Glue Catalog; hỗ trợ engine
thực tế phải được pin và kiểm thử, không suy ra từ delta-rs local.
[AWS Glue Delta integration](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-delta-lake.html).
S3 Standard-IA có minimum duration 30 ngày; đây là lý do loại tier đó cho payload.
[S3 pricing](https://aws.amazon.com/s3/pricing/).

<div style="break-after: page;"></div>

## 3. Data contracts, freshness và retention

**Ingest contract.** Event mang `tenant_id`, `request_id`, `event_ts_utc`,
`schema_version`, `redaction_policy_version`, token counts, latency, status và
sanitized body. Privacy gateway dùng detectors được version hóa; regex đơn lẻ không
đủ cho free text. Nếu detector timeout hoặc schema lạ, không đẩy raw body vào broker,
DLQ hoặc logs; chỉ lưu ID, error code và retry signal. Không ghi prompt vào task logs.

**Retry contract.** Key là `(tenant_id, request_id)`; retries không tạo request mới.
Silver chọn revision theo sequence/source offset có thứ tự xác định. Writer commit
batch với run_id và source-offset range; retry dùng lại batch identity. Watermark
24h là giả định lateness, không phải bằng chứng exactly-once end-to-end. Event quá
late phải qua reconciliation trước khi Gold được công bố lại.

**Gold contract.** Key `(tenant_id, model, window_start_utc)`, window năm phút.
Trigger ingest tối đa 60s; budget p95 end-to-end 300s gồm queue, Silver và Gold.
Micro-batch retry không cộng lại token/cost: recompute các window bị ảnh hưởng từ
Silver và MERGE thay kết quả. Daily p50/p95 tính từ Silver của ngày đó trước expiry;
không lấy trung bình các p95 của window. Pricing version được pin vào run để cost
không đổi ngầm khi bảng giá thay đổi. Dashboard trả last_successful_update và staleness.

**Query contract.** Dashboard chỉ đọc Gold, cache theo tenant/model/time range.
Incident service bắt buộc cả tenant và UTC time predicate; kiểm tra quyền tại API và
storage role. Không cấp analyst raw S3 credentials hoặc quyền arbitrary time travel
trên payload. Authorization của catalog không thay thế chặn direct object access.

**Retention contract.** Read API từ chối event đã quá 168h, kể cả khi client pin
version cũ. Purger mỗi 15 phút: xác nhận final Gold, lấy lease độc quyền cho expired
partition, chờ/hủy readers và writers, transactionally delete expired rows, xác định
các file vật lý còn chứa payload quá hạn rồi thu hồi trong SLO một giờ. Giữ audit
manifest chỉ gồm IDs/hashes/counts, không body. Không rollback resurrect dữ liệu expired.

Đây là mechanism khó nhất: ordinary DELETE giữ file cũ để time travel; default vacuum
retention có thể kéo dài việc lưu payload. Chỉ thay retention sau khi reader/writer lease
và stream lag đã được chứng minh; không dùng `VACUUM RETAIN 0` từ lab cho production.
Nếu không bảo đảm lease, phải fail deployment gate thay vì tuyên bố purge thành công.
[Delta maintenance/retention](https://docs.delta.io/delta-utility/).

S3 Lifecycle chỉ là lớp cleanup phụ, không được đặt TTL tùy ý lên active Delta files.
Lifecycle deletion là asynchronous; bucket versioning có thể giữ noncurrent versions.
Payload bucket không bật versioning/Object Lock/replication trong scope này; mất
khả năng khôi phục payload đã purge là tradeoff được chấp nhận. Các file checkpoint,
shuffle, broker replay, caches và sanitized DLQ cũng phải nằm trong expiry inventory.
[S3 expiration semantics](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html).

<div style="break-after: page;"></div>

## 4. Back-of-envelope cost và sensitivity

Chọn `us-east-1` làm region tính toán. Tra nguồn ngày 04/10/2026. Vì bảng regional S3
được tải động, các đơn giá S3 dưới đây là **planning ceilings giả định**, không phải
báo giá region đã khóa: storage 0.03 USD/GB-month, PUT/LIST 0.006 USD/1K,
GET 0.001 USD/1K. Broker disk có planning ceiling riêng 0.10 USD/GB-month.
Các mức này là inputs cho sensitivity, không phải giá niêm yết đã xác minh.
Phải xác nhận lại bằng AWS Pricing Calculator trước deployment.
S3 có các thành phần storage, requests và transfer; không chỉ tính bytes hiện tại.
[S3 pricing](https://aws.amazon.com/s3/pricing/).

### Storage: working set, không lấy daily volume làm monthly occupancy

| Thành phần | Công thức | TB resident |
|---|---|---:|
| Bronze body, compression 4× | `5 × 7 / 4` | 8.75 |
| Silver metadata 500 B/request, 4× | `0.5 × 7 / 4` | 0.875 |
| Gold 365d, 100K tenants ×3 models ×288 windows/d ×96 B, 4× | `100000×3×288×365×96 / 1e12 / 4` | 0.756864 |
| Budget một bản rewrite/tombstone của cả ba tầng | `8.75 +0.875 +0.756864` | 10.381864 |
| Checkpoints, shuffle, audit và purge backlog allowance | `1` | 1.00 |
| **Tổng S3 occupancy bảo thủ** | | **21.763728** |

S3 storage: `21.763728 ×1000 ×$0.03 ≈ $653/tháng`.
Requests assumption: `1M PUT/LIST /1000 ×$0.006 = $6`;
`100M GET /1000 ×$0.001 = $100`. Cộng $100 allowance cho inventory/metadata:
**S3 storage + object operations ≈ $859/tháng**.
Broker replay tối đa 24h, ba replicas, không dựa vào compression:
`5 TB ×3 ×1000 ×$0.10 = $1,500/tháng` cho disk.
**Tổng storage, kể cả broker ≈ $2,359/tháng**, còn khoảng $2,641 dưới cap.
Broker compute/network được tính riêng ở bảng dưới; không coi disk là compute.

Sensitivity compression **1×**: Bronze 35 TB + Silver 3.5 TB + Gold 3.027456 TB
+ một bản rewrite của cả ba tầng 41.527456 TB + overhead 1 TB =84.054912 TB.
S3 bytes khoảng $2,522; cộng $206 operations/allowance và $1,500 broker disk
≈ **$4,228/tháng**. Chỉ còn khoảng $772 dưới cap theo assumptions.
Ngược lại, một object/request tạo `30B PUT/month ×$0.006/1000=$180K/month`:
việc batching là điều kiện bắt buộc dù byte storage rất rẻ.

Gold 96 B/row và cardinality tenant/model đều là giả định, chưa benchmark. Không giữ
request IDs, text hoặc user identifiers trong Gold. Không cho phép compaction lặp
toàn bộ working set làm tích lũy nhiều bản rewrite ngoài allowance. Cảnh báo forecast
ở $3K; ở $4K hạn chế query/ad-hoc và scale maintenance có kiểm soát. Không giảm
retention bảy ngày hoặc sampling bỏ request để che việc vượt cap.

### Compute và tổng logging budget

Dùng đơn giá tham chiếu **$0.44/DPU-hour** trong ví dụ chính thức AWS Glue;
đơn giá regional cần chốt lại. [AWS Glue pricing](https://aws.amazon.com/glue/pricing/).

| Khoản | Công thức / giả định | USD/tháng |
|---|---|---:|
| Spark ingest/aggregation baseline | `20 DPU ×24h ×30d ×0.44` | 6,336 |
| Peak capacity thêm | `40 DPU ×4h ×30d ×0.44` | 2,112 |
| Compaction/reconciliation riêng | `8 DPU ×6h ×30d ×0.44` | 633.60 |
| Privacy gateway + broker compute/network | Planning allowance; chưa sizing benchmark, disk tính riêng | 1,000 |
| Dashboard/query service/cache | Planning allowance | 500 |
| Audit/keys/catalog/monitoring | Planning allowance | 200 |
| S3 + broker disk + S3 operations | Ước lượng trên | 2,359 |
| **Tổng logging services** | | **≈13,141** |

20 DPU là capacity hypothesis, chưa chứng minh 1B/day. MVP phải đo throughput,
state size và DPU-hours/TB, rồi sửa estimate. Không có cap $5K cho tổng compute trong
đề; cap đó chỉ là storage. Chưa gồm VAT, internet/cross-region egress, support hoặc
nhân sự; thiết kế tránh cross-region payload replication và full-body exports.

<div style="break-after: page;"></div>

## 5. Failure modes và MVP một tuần

| Hỏng lúc 03:00 | Detection | Containment và rollback/recovery |
|---|---|---|
| Detector PII timeout hoặc bỏ sót fixture | Redaction latency/error counters; seeded PII canaries và scan sample từ Bronze | Fail closed; dừng publication cho policy lỗi, thu hồi quyền đọc partition ảnh hưởng; deploy detector version tốt. Reprocess sanitized data còn giữ được; không RESTORE dữ liệu có leak. |
| Retry/restart cộng duplicate vào Gold | Key uniqueness, reconciled request/token totals; run_id/source offsets lặp | Dừng Gold publish; replay batch idempotently, dedup Silver rồi rebuild affected windows và MERGE replace; kiểm tra totals trước mở lại. |
| Schema đổi token count từ integer sang string | Contract gate/enforcement error; bad-event rate tăng | Quarantine metadata, giữ checkpoint trước batch lỗi; rollback parser version rồi replay trong replay horizon. Không bật auto-merge toàn cục để bỏ qua mismatch. |
| Purger xóa file reader còn cần, hoặc payload expired còn recoverable ở version cũ | Lease failures, snapshot read tests và expiry inventory vượt SLO | Chặn purge nếu còn lease; hủy stale reader theo contract. Nếu file chưa xóa, rollback tombstone trước expiry; nếu đã purge thì không giả vờ RESTORE được. Rebuild Gold từ phần source còn hợp lệ, báo mất payload nếu không còn nguồn. |
| Small files hoặc rewrite backlog đẩy forecast vượt cap | Active/tombstoned bytes, median file size, files/query, lag và cost forecast | Điều chỉnh batch/coalesce; compact closed hour một lần, tăng maintenance theo bounded budget; giới hạn heavy query. Không archive body expired hoặc xóa dữ liệu chưa hết hạn để giảm bill. |

Failure modes gắn trực tiếp với schema enforcement, ACID MERGE, time travel,
retention và maintenance; audit ghi nguyên nhân và version nhưng không chứa body.

### Slice một tuần: một tenant, ba model, pipeline và purge thật

| Ngày | Sản phẩm có thể review |
|---|---|
| 1 | Data contract, synthetic PII fixtures, key/UTC semantics; chốt định nghĩa 168h và physical purge SLO |
| 2 | Gateway → replay queue → Bronze/Silver trên stack Spark/Delta mục tiêu; pin engine/runtime |
| 3 | Gold windows/daily; tenant-scoped read; freshness và totals reconciliation |
| 4 | Crash/retry/late-event tests; compare same-input output counts/token sums và version audit |
| 5 | Expiry inventory, lease cancellation và physical purge test bao gồm tombstoned files/cache/replay |
| 6 | Load ramp, compression và files/query measurements; cập nhật cost bằng measured DPU-hours/TB |
| 7 | Failure drill, acceptance report và quyết định go/no-go; chưa rollout 100K tenants |

**Nghiệm thu.** Seeded PII không xuất hiện trong Bronze, broker, logs hoặc DLQ;
detector timeout không publish body. Crash rồi replay cùng batch không đổi unique
request counts, token totals hoặc cost. Inject late events trong 24h và chứng minh
window được sửa đúng. p95 source-to-Gold ≤300s trên load slice, test riêng burst 3×;
không ngoại suy tuyến tính để tuyên bố đã đạt 1B/day.

**Kiểm tra phần khó nhất.** Dùng dữ liệu scratch có clock/retention tăng tốc, tạo
compaction và các version cũ trước expiry; giữ một reader lease khi purger chạy.
Purger phải từ chối xóa lúc lease còn hiệu lực. Sau expiry/lease release, current
query và old-version read bị chặn; enumerate file/object versions, queue/cache/DLQ
để xác nhận payload hết hạn không còn recoverable trong SLO. Cố restore rồi verify
không resurrect expired content. Test fail thì không có acceptance, dù current query trả zero rows.

Lab hiện có bằng chứng NB2/NB6 về skipping/maintenance, NB4 về dedup/Gold và NB8
về version pin. Các số đó không chứng minh privacy gateway, lease protocol,
Spark cloud throughput hoặc physical purge của thiết kế này đã chạy.
[Kết quả lab thực tế](../RESULTS.md). PoC riêng không nộp; document là deliverable.

**Giới hạn bản brief:** source Markdown chia năm phần bằng page-break hints;
số trang 3–6 phải kiểm tra trên bản render cuối. Đây là thiết kế có deployment gates,
không phải chứng nhận đã đáp ứng tuyệt đối physical TTL hoặc một báo giá cloud đã khóa.
