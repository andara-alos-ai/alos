# Interface Design-Time Genesis

| Metadata | Nilai |
|---|---|
| Status | Diimplementasikan untuk Fondasi Genesis G3 |
| Versi | 0.1.0 |
| Pembaruan terakhir | 30 Agustus 2026 |

## 1. Tujuan

Interface Genesis menyiapkan batas teknis untuk memilih `REUSE`, `EXTEND`, atau `CREATE` menggunakan Agent Contract yang sama dengan 18 Core Agent. Implementasi ini belum merupakan full Genesis dan tidak melakukan generation dengan LLM, penulisan registry, staging, release, atau deployment.

## 2. Strategi

| Strategi | Hasil |
|---|---|
| `REUSE` | menunjuk agent dan versi yang sudah terdaftar tanpa membuat kontrak baru |
| `EXTEND` | mengusulkan Sub-Agent/Sub-Sub-Agent DRAFT yang mempertahankan capability dan tool base |
| `CREATE` | mengusulkan kontrak DRAFT baru setelah reuse/extend tidak dipilih |

Setiap permintaan wajib memiliki pemohon, alasan, referensi sumber, dan target/candidate sesuai strategi. Hasil berupa proposal immutable berisi validasi, diff deterministik, referensi kontrak, dan status `AWAITING_HUMAN_REVIEW` atau `INVALID`.

## 3. Kontrol Wajib

- Genesis tidak dapat membuat atau mengubah Core Agent;
- candidate wajib `DRAFT` dan mengikuti hierarchy Core → Sub-Agent → Sub-Sub-Agent;
- kombinasi `agent_id` dan `version` tidak boleh menimpa registry;
- parent, `extends`, capability, serta tool divalidasi terhadap registry;
- `EXTEND` tidak boleh menghapus capability atau tool base;
- proposal selalu `production_effect=false`;
- satu-satunya tindakan berikutnya adalah review manusia.

## 4. Jalur Pengembangan Berikutnya

Pipeline penuh nantinya dapat memasok candidate ke interface ini melalui `source/specification → analyze → generate`. Setelah proposal valid, tahap `test → diff → human review → staging/release` dibangun sebagai layanan terpisah dengan otorisasi, audit, dan lingkungan terisolasi. Tidak ada jalur langsung dari proposal menuju production.
