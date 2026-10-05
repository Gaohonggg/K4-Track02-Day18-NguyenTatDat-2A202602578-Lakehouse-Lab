# Lakehouse Lab — Kết quả và giải thích

Các số dưới đây lấy từ tám `.ipynb` trong [notebooks/](notebooks/), thực thi ngày
04/10/2026 trên môi trường ghi tại [INFO.md](INFO.md). 

## Tổng hợp theo rubric

| NB | Bằng chứng quan sát trong notebook | Đối chiếu |
|---|---|---|
| 1 | Hai commit JSON; ghi `age='thirty'` bị chặn; version 0→0, dữ liệu 3→3; thêm `tier`, có hai nhóm tier | Đạt các kiểm tra Delta basics |
| 2 | 200→55 file; 53.2→4.0 ms; speedup 13.2×; một trong 55 file chứa target, pruning 55× | ≥100 file ban đầu; đạt cả speedup ≥3× và pruning ≥10× |
| 3 | MERGE 100K: 50K update + 50K insert; history v0–v4 có RESTORE; `score<0` còn 0 | Đạt MERGE, time travel và rollback |
| 4 | Bronze 200,000→Silver 190,052; Gold 8 ngày ×3 model =24 nhóm; các checks và reference calculation PASS | Đạt ≥7 ngày, dedup và chất lượng Gold |
| 5 | Catalog SQLite; `day(ts)`; plan 10→1 file; field ID 4 giữ nguyên; spec ID [1,2]; 5,500 dòng đọc được | Đạt pruning ≥5×, schema/partition evolution |
| 6 | Compaction 200→11 file; clustering 1/10 file, skip 90%; vacuum thu hồi 16.1 MB; xóa 3 Delta orphan; Iceberg 20→3 snapshot, sweep 17 manifest lists; có checkpoint | Đạt cả năm job được chấm |
| 7 | Amplification 200× theo row-group metadata; int8 nhỏ 5.8×; recall 0.904, topic fidelity 1.000; deleted hits 0/8; 8 CDF deletes | Đạt các ngưỡng multimodal/vector và tái hiện lifecycle bug |
| 8 | Hai policy partition; pin v0 với 1,578 bước; replay khớp; 5 list→1 catalog read; task completed; bốn bucket và 334 UNCLASSIFIED bị loại | Đạt các kiểm tra trajectory và mô phỏng provenance |

## NB1 — ACID log, enforcement và evolution

Commit đầu chứa `commitInfo`, `protocol`, `metaData` và `add`: log ghi operation,
schema và file đã được commit. Sau append hợp lệ có hai commit JSON, v0 và v1.
Lần ghi sai kiểu trả lỗi `Cast error: Cannot cast string 'thirty' to value of Int64 type`.
Version vẫn bằng 0, schema và cả ba dòng không đổi. Điều này chứng minh failure đã
được kiểm tra thực tế, thay vì dùng flag PASS đặt sẵn của notebook gốc.

`schema_mode="merge"` thêm `tier` khi được cho phép rõ ràng. Dòng mới có `premium`,
ba dòng cũ có NULL; DuckDB trả hai nhóm. Evolution thay đổi schema có chủ đích,
không đồng nghĩa mọi dữ liệu sai kiểu đều được chấp nhận.

## NB2 — Compaction và file skipping

200 lần append tạo 200 file, đáp ứng yêu cầu tái hiện small-file problem.
Sau compact + Z-order còn 55 file, giảm khoảng 3.64×. Query trả cùng năm dòng
trước/sau; median ba lần đo giảm từ 53.2 xuống 4.0 ms, notebook báo speedup 13.2×.
Không tính lại speedup bằng hai timing đã làm tròn để thay giá trị báo trong output.

Stats cho thấy chỉ một file chứa `user_id=4242` trong khoảng min/max; 54/55 file
có thể bị loại ở bước planning. Pruning ratio là `55/1=55×`, khác với tỷ lệ giảm
số file `200/55`. Z-order làm stats có ích cho predicate; compaction giảm số file.
Timing chịu ảnh hưởng cache/CPU/SSD, còn pruning phản ánh layout trực tiếp hơn.

## NB3 — Versioning và RESTORE

MERGE dùng 100,000 source rows: 50,000 bản ghi được update và 50,000 được insert,
cho 150,000 output rows. Lần chạy mất 0.04 giây. Version v3 append 50 dòng lỗi;
RESTORE về trạng thái v2 tạo commit mới v4. History cuối có năm version và dòng RESTORE.

Query v0 vẫn trả 100,000 dòng; schema v1 có `tier`. Sau RESTORE không còn `score<0`.
Rollback đổi trạng thái hiện tại và giữ audit trail; nó không xóa các commit cũ.
Khả năng đọc version cũ còn phụ thuộc retention của file vật lý, như NB6 minh họa.

## NB4 — Medallion và kiểm tra Gold

Bronze giữ 200,000 dòng raw. Silver dedup theo `request_id`, còn 190,052 dòng;
9,948 dòng bị loại, tương đương khoảng 4.97% Bronze. Gold có 24 nhóm, phủ
2026-04-01 đến 2026-04-08 và ba model. Kết quả tám ngày thực tế đáp ứng ngưỡng
ít nhất bảy ngày; không thay bằng dự kiến 21 nhóm của generator.

Generator dùng timestamp UTC, nhưng `CAST(ts AS DATE)` chịu ảnh hưởng timezone của
session xử lý. Vì thế không dùng số ngày calendar làm bằng chứng rằng generator
sinh thêm 24 giờ dữ liệu. Output hiện tại chưa ghi timezone của DuckDB session;
nguyên nhân tám ngày là một điểm cần xác minh riêng nếu chuẩn hóa ngày báo cáo.

Không có missing pairs, duplicate keys, unpriced Silver rows hoặc invalid metrics.
Nhóm đối chiếu `2026-04-01 / claude-haiku-4-5` có 5,855 dòng Silver:

| Metric | Gold | Kết quả tính lại bằng Python |
|---|---:|---:|
| p50 latency | 567 ms | 567 ms |
| p95 latency | 1,121 ms | 1,121 ms |
| Prompt tokens | 11,888,206 | 11,888,206 |
| Completion tokens | 5,916,990 | 5,916,990 |
| Error rate | 0.04935952177625961 | 0.04935952177625961 |
| Cost | 33.178524800000005 USD | 33.1785248 USD |

Sai khác cost ở chữ số cuối nằm trong tolerance floating-point. Cost dùng bảng giá
minh họa cố định của lab, không phải báo giá thương mại. Error rate bằng 0 là giá trị hợp lệ;
kiểm tra đúng là không NULL, hữu hạn và trong [0,1].

## NB5 — Catalog, hidden partitions và metadata

`SqlCatalog` tạo và quản lý bảng; transform `day(ts)` được lưu trong partition spec.
Predicate trên `ts` chọn một trong mười file và trả 500 dòng, pruning 10× mà người query
không cần lọc trực tiếp `ts_day`. Metadata được đi theo chuỗi catalog → metadata JSON
→ manifest list → manifests → data files.

Output ghi metadata 137.3 KB, data 47.3 KB và tỷ lệ metadata:data 290.3%.
Đây là `metadata_bytes/data_bytes`, không phải phần trăm metadata trong tổng dung lượng.
Ví dụ lab giữ nhiều metadata lịch sử cho file rất nhỏ; không ngoại suy tỷ lệ này cho
bảng production. Các phép tính USD trong notebook là tình huống minh họa, không đo chi phí phát sinh.

Rename `latency_ms` thành `latency_millis` giữ field ID 4; các dòng cũ vẫn đọc được,
cột `tier` mới có 5,000 NULL. Sau evolution, files dùng spec ID 1 và 2 cùng tồn tại;
5,500 dòng đọc được qua một bảng. Catalog cục bộ không chứng minh có authorization
hoặc server-side scan planning của catalog production.

## NB6 — Maintenance: số liệu và cách diễn giải

| Job | Trước | Sau | Cơ chế / kết quả |
|---|---|---|---|
| Compaction | 200 active data files | 11 | Giảm khoảng 18.18×; vẫn 100,000 dòng |
| Clustering | Point query phải mở 11/11 file | 1/10 | Skip 90% nhờ min/max `user_id` |
| Delta vacuum | File tombstoned còn trên đĩa | Thu hồi 16.1 MB | Active table vẫn 100,000 dòng |
| Delta orphan sweep | Ba file crashed-writer 30 ngày tuổi | Cả ba bị xóa | Tìm bằng physical files trừ active references, có age guard |
| Iceberg expiry | 20 snapshots, 40 Avro files | 3 snapshots, vẫn 40 Avro | API đang dùng thay metadata, chưa thu hồi file |
| Iceberg sweep | 17 manifest lists không được retained snapshots tham chiếu | Xóa 17, còn 23 Avro | Thu hồi 37.2 KB; vẫn 2,000 dòng |
| Checkpoint | Có JSON history | Có checkpoint Parquet và `_last_checkpoint` | Reader dùng checkpoint làm điểm bắt đầu replay |

Ba điểm tránh đọc sai output notebook gốc:

1. `VACUUM would reclaim ... (0 B)` không phải số bytes thu hồi thực tế.
   Cell cộng `du(f)` trực tiếp mà chưa resolve đường dẫn theo table root;
   cần kiểm tra/chuẩn hóa đường dẫn trước khi dùng con số này làm byte estimate.
   Bằng chứng thu hồi là chênh lệch dung lượng trước/sau vacuum: 16.1 MB.
   Dry-run lần sau có thể vẫn liệt kê tombstone của file đã xóa; không coi đó là
   211 file vật lý còn tồn tại.
2. `count_files(TABLE)` tìm mọi `.parquet`, gồm cả checkpoint dưới `_delta_log`.
   Chênh lệch 15 file trên đĩa trừ 10 active data files là năm, nhưng có hai checkpoint
   tại thời điểm đó. Ba planted orphans được `find_orphans` tìm và xóa; hàm này loại
   `_delta_log` khỏi candidates. Sau sweep, chênh lệch hai không chứng minh còn hai orphan data files.
3. Dòng tên checkpoint dùng phần tử đầu của danh sách glob nên có thể in checkpoint cũ v99.
   Sau lần chạy runner, kiểm tra file thật cho thấy checkpoint v99, v199 và v203;
   `_last_checkpoint` trỏ version 203. Đây là quan sát filesystem của lần chạy sau,
   không phải sửa lại output notebook đã lưu.

Kết luận về vacuum/expiry áp dụng cho `deltalake 1.6.6` và `pyiceberg 0.12.0`
trong lab. Không áp dụng thuật toán chỉ bảo vệ active files cho hệ thống thật còn
retained historical versions, reader hoặc writer đồng thời. Retention 0 chỉ dùng
trên bảng scratch; production cần xét retained versions và tuổi file trước khi sweep.

## NB7 — Layout multimodal, quantization và lifecycle

Inline có một row group gồm 200 blobs; một blob 64 KB, row-group metadata báo khoảng
12.5 MB. Tỷ số khoảng 200× vượt ngưỡng 5×. Đây là ước lượng theo
`row_group.total_byte_size` và giả định đọc ở độ hạt row group, không phải phép đo
disk/network I/O của mọi reader. Page indexes, caching và implementation có thể thay đổi I/O thực tế.
Analytical projection `doc_id/topic` chỉ có khoảng 1.2 KB column chunks, minh họa lợi ích column pruning.

Float32 table 2.6 MB so với int8 451.9 KB, notebook báo nhỏ hơn 5.8×;
đây là tỷ số dung lượng gồm table metadata và Parquet compression, khác tỷ số raw dtype 4×.
Recall@10 là 0.904 và topic fidelity 1.000 trên corpus synthetic có topic clusters.
Top-5 SQL search đều thuộc topic storage, nhưng gồm chính query document;
không coi đó là benchmark retrieval trên tài liệu tự nhiên hoặc tải phục vụ lớn.

Xóa tám tài liệu của `user_042` làm bảng hiện tại còn 1,992 dòng, trong khi bản copy
external index vẫn có 2,000. Kiểm tra ID cho thấy zero deleted hits trong bảng và
tám trong index; CDF phát tám delete events. Đây là tái hiện một derived index stale,
không phải một vector database đã triển khai. Notebook minh họa feed cần dùng để
evict IDs; chưa thực thi consumer đồng bộ xóa vào index.

## NB8 — Trajectory và provenance

1,578 bước được ghi vào hai partition `policy-v2` và `policy-v3`; mỗi policy có
150 trajectories. Gold báo success rate 0.760 và 0.753. Training record pin version 0,
1,578 bước. Append thêm 400 bước tạo version 1 với 1,978 bước; replay v0 vẫn trả đúng
1,578. Kiểm tra là row count, chưa chứng minh content hash, thứ tự hay model replay giống hệt.

Mô phỏng `list_tables` có năm calls nhưng chỉ một catalog read. Destructive call
chưa confirmed trả `input_required`; task poll hoàn tất với 300 rows. Đây là lớp offline;
cờ confirmed do caller truyền và `delete_rows` là no-op, không phải authorization boundary.

| Bucket minh họa | Rows |
|---|---:|
| licensed | 675 |
| public_domain | 333 |
| scraped_optout_checked | 327 |
| synthetic | 331 |
| UNCLASSIFIED | 334 |

Training filter chọn 1,666/2,000 dòng, loại 334 UNCLASSIFIED. Bốn bucket là quy tắc
của lab. Mapping CC BY vào `public_domain` và ownership/consent vào
`scraped_optout_checked` không đủ để xác lập quyền sử dụng dữ liệu thật.
Xóa subject `user_007` làm current version còn zero subject rows, nhưng version 0
vẫn giữ dữ liệu. Đây không phải chứng minh đã xóa backups, index hoặc ảnh hưởng trong model.

## Reproducibility và phần còn phải hoàn tất

Smoke 9/9, pytest baseline 24/24; nbconvert đã lưu tám notebook với tổng 87 code cells,
không có cell chưa chạy hoặc error output. Runner `.py` sau đó PASS 8/8 trong 10.9 giây.
Chưa kiểm thử Spark, Apple container hoặc một clean checkout riêng; không dùng kết quả
lightweight để khẳng định các đường đó đã PASS.

Cần kiểm tra đủ ảnh kết quả trong [screenshots/](screenshots/) theo rubric, rà soát reflection,
thông tin cá nhân, bonus nếu nộp, và chốt repo/PR/commit SHA qua kênh lớp.
