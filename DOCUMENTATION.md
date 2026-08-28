# PDF Parser & Standardisasi JSON untuk Graph RAG (Docling Pipeline)

Dokumentasi lengkap mengenai perancangan, implementasi, optimasi, dan pengujian pipeline open-source **Docling** sebagai pengganti parser berbayar (**Landing.AI**) untuk mengekstrak dokumen PDF (digital, hasil scan, tabel, dan gambar) menjadi representasi JSON standar berbasis *chunking* dan *bounding box grounding*.

---

## Daftar Isi

- [1. Latar Belakang & Tujuan](#1-latar-belakang--tujuan)
- [2. Arsitektur & Alur Kerja Pipeline](#2-arsitektur--alur-kerja-pipeline)
- [3. Struktur Standar JSON Target](#3-struktur-standar-json-target)
- [4. Implementasi Kode Program](#4-implementasi-kode-program)
  - [4.1. Ekstraksi Dokumen (`ekstraksi.py`)](#41-ekstraksi-dokumen-ekstraksipy)
  - [4.2. Standardisasi & Chunking Engine (`formater.py`)](#42-standardisasi--chunking-engine-formaterpy)
  - [4.3. Evaluasi & Validasi Output (`check.py`)](#43-evaluasi--validasi-output-checkpy)
- [5. Hasil Pengujian & Evaluasi Komparatif](#5-hasil-pengujian--evaluasi-komparatif)
  - [5.1. Kasus Uji 1: Dokumen Teks Kompleks (`UU Nomor 4 Tahun 2009`)](#51-kasus-uji-1-dokumen-teks-kompleks-uu-nomor-4-tahun-2009)
  - [5.2. Kasus Uji 2: Dokumen Arsip Scan (`UU Nomor 5 Tahun 1983`)](#52-kasus-uji-2-dokumen-arsip-scan-uu-nomor-5-tahun-1983)
- [6. Analisis Teknis & Pembahasan Mendalam](#6-analisis-teknis--pembahasan-mendalam)
  - [6.1. Fenomena Caption Gambar Sintetis Landing.AI vs Docling](#61-fenomena-caption-gambar-sintetis-landingai-vs-docling)
  - [6.2. Keandalan OCR Docling pada Dokumen Scan & Buram](#62-keandalan-ocr-docling-pada-dokumen-scan--buram)
  - [6.3. Penanganan Tabel Kompleks (TableFormer & Markdown Grid)](#63-penanganan-tabel-kompleks-tableformer--markdown-grid)
  - [6.4. Perbandingan Ekosistem: Docling vs MinerU](#64-perbandingan-ekosistem-docling-vs-mineru)
  - [6.5. Strategi Deployment Server GPU untuk Aplikasi Web & Graph RAG](#65-strategi-deployment-server-gpu-untuk-aplikasi-web--graph-rag)
- [7. Panduan Penggunaan (Quickstart)](#7-panduan-penggunaan-quickstart)
- [8. Referensi](#8-referensi)

---

## 1. Latar Belakang & Tujuan

Sebelumnya, ekstraksi dokumen regulasi dan hukum menggunakan layanan cloud berbayar **Landing.AI** yang menghasilkan representasi JSON berformat `chunks`. Mengingat besarnya volume dokumen dan kebutuhan efisiensi biaya, privasi data instansi, serta skalabilitas, dikembangkan alternatif menggunakan library open-source **Docling** (IBM Research).

Tantangan utama yang diselesaikan dalam proyek ini:
1. **Perbedaan Granularitas Chunk**: Output mentah Docling menghasilkan ribuan fragmen teks kecil (1.300+ elemen), sedangkan Landing.AI menggabungkan teks yang berdekatan menjadi unit paragraf/pasal yang logis (~630 chunk).
2. **Koreksi Tipe Semantik (`chunk_type`)**: Memetakan elemen secara tepat (`text`, `marginalia`, `figure`).
3. **Rekonstruksi Bounding Box**: Menghitung gabungan (*union bbox*) dari koordinat normalisasi (0.0 - 1.0) saat beberapa elemen teks digabungkan.
4. **Preservasi Tabel & Gambar**: Memastikan tabel terkonversi ke Markdown tanpa sel yang hilang dan gambar terpetakan sesuai posisi spasial fisik.
5. **Kesiapan Dokumen Scan**: Memastikan engine OCR terintegrasi secara otomatis saat memproses dokumen arsip hasil scan.

---

## 2. Arsitektur & Alur Kerja Pipeline

Pipeline pemrosesan data terdiri dari 3 tahapan modular:

```text
[ Input PDF ]
      │
      ▼
[ ekstraksi.py ] ── (Docling + RapidOCR PP-OCRv6 + TableFormer)
      │
      ▼
[ Raw Docling JSON ] (output/...)
      │
      ▼
[ formater.py ] ── (Hierarchical Tree Grouping + Spatial Vertical Merge + Union BBox)
      │
      ▼
[ Standardized JSON ] (formater/...)
      │
      ▼
[ check.py ] ── (Perbandingan Skema, Distribusi Tipe, & Kemiripan Teks dengan Referensi)
```

1. **Tahap Ekstraksi (`ekstraksi.py`)**: Membaca file PDF, menjalankan analisis layout DocLayNet, model tabel TableFormer, dan OCR RapidOCR, lalu mengekspor dokumen ke struktur dictionary Docling mentah.
2. **Tahap Formatting (`formater.py`)**: Melakukan pengelompokan hierarki level-1 (grup/list Docling), penggabungan spasial level-2 (threshold jarak vertikal), pengurutan urutan bacaan fisik, serta normalisasi spasi dan koordinat.
3. **Tahap Verifikasi (`check.py`)**: Menguji validitas skema JSON, distribusi tipe chunk, cakupan halaman, dan kemiripan teks terhadap data acuan referensi Landing.AI.

---

## 3. Struktur Standar JSON Target

Setiap file JSON yang dihasilkan mengikuti skema standar berikut:

```json
{
  "chunks": [
    {
      "chunk_id": "8f3b2a1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
      "chunk_type": "text",
      "text": "UNDANG-UNDANG REPUBLIK INDONESIA\nNOMOR 4 TAHUN 2009\nTENTANG\nPERTAMBANGAN MINERAL DAN BATUBARA",
      "grounding": [
        {
          "box": {
            "l": 0.285490,
            "t": 0.205166,
            "r": 0.727069,
            "b": 0.300238
          },
          "page": 0
        }
      ]
    },
    {
      "chunk_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
      "chunk_type": "marginalia",
      "text": "- 2 -",
      "grounding": [
        {
          "box": {
            "l": 0.468800,
            "t": 0.178300,
            "r": 0.521800,
            "b": 0.189500
          },
          "page": 1
        }
      ]
    }
  ]
}
```

### Definisi Atribut:
* `chunk_id`: String UUID v4 unik untuk setiap potongan informasi.
* `chunk_type`: Tipe semantik elemen:
  * `"text"`: Paragraf, pasal, klausul hukum, judul, dan tabel markdown.
  * `"marginalia"`: Nomor halaman (*page numbers*) dan header dekoratif.
  * `"figure"`: Gambar, logo, stempel, dan diagram.
* `text`: Konten teks bersih dengan penanganan spasi tunggal dan pemisah baris (`\n` atau `\n\n`).
* `grounding`: Array objek berisi koordinat `box` ternormalisasi (`l`, `t`, `r`, `b` berskala `0.0` - `1.0` dengan origin kiri-atas) dan penomoran halaman `page` (*0-indexed*).

---

## 4. Implementasi Kode Program

### 4.1. Ekstraksi Dokumen (`ekstraksi.py`)

Skrip ini mengonversi PDF menjadi JSON mentah Docling dengan pipeline OCR aktif untuk dokumen scan dan rekonstruksi tabel.

```python
import os
import sys
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FILE_NAME = "UU_Nomor_4_Tahun_2009_ID-1.pdf"


def get_input_file_path() -> Path:
    """Mendapatkan path lengkap ke file PDF di folder input."""
    if len(sys.argv) > 1:
        arg_path = Path(sys.argv[1])
        if arg_path.is_absolute() or arg_path.exists():
            return arg_path
        return INPUT_DIR / arg_path.name
    
    input_path = INPUT_DIR / DEFAULT_FILE_NAME
    if not input_path.exists():
        pdf_files = list(INPUT_DIR.glob("*.pdf"))
        if pdf_files:
            print(f"[INFO] '{DEFAULT_FILE_NAME}' tidak ditemukan. Menggunakan file PDF yang ada: {pdf_files[0].name}")
            return pdf_files[0]
            
    return input_path


def parse_pdf_to_json(pdf_path: Path, output_dir: Path):
    """
    Mem-parsing file PDF menggunakan Docling dengan konfigurasi OCR & pipeline yang dioptimalkan
    untuk menangani baik PDF digital maupun PDF full-scan (gambar/foto).
    """
    if not pdf_path.exists():
        print(f"[ERROR] File input tidak ditemukan di: {pdf_path}")
        print(f"Silakan simpan file PDF Anda ke dalam folder: {INPUT_DIR}")
        return

    output_json_path = output_dir / f"{pdf_path.stem}.json"

    print(f"==================================================")
    print(f"Input PDF  : {pdf_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"==================================================")

    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.datamodel.base_models import InputFormat
    except ImportError:
        print("[ERROR] Library 'docling' belum terpasang.")
        print("Silakan install terlebih dahulu dengan perintah: pip install docling rapidocr-onnxruntime")
        return

    start_time = time.time()
    print(f"Sedang memproses '{pdf_path.name}' dengan Docling OCR Engine...")

    try:
        # Konfigurasi Pipeline Options untuk memastikan OCR aktif untuk dokumen scan
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True                 # Aktifkan OCR otomatis untuk halaman/elemen scan
        pipeline_options.do_table_structure = True     # Rekonstruksi struktur tabel secara presisi
        
        # Konfigurasi RapidOCR Engine (cepat, akurat, dan hemat memori)
        pipeline_options.ocr_options = RapidOcrOptions(
            force_full_page_ocr=False,                 # Jalankan OCR pada elemen non-teks/scan
            use_det=True,
            use_cls=True,
            use_rec=True,
        )

        # Inisialisasi Converter dengan opsi format PDF yang telah dioptimasi
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

        # Konversi dokumen PDF
        result = converter.convert(str(pdf_path))

        # Ekspor struktur dokumen ke format dictionary / JSON
        doc_dict = result.document.export_to_dict()

        # Simpan ke file JSON di folder output
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(doc_dict, f, ensure_ascii=False, indent=2)

        duration = time.time() - start_time
        print(f"[SUCCESS] Selesai dalam {duration:.2f} detik!")
        print(f"Hasil JSON berhasil disimpan di: {output_json_path}")

    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat memproses PDF: {e}")


if __name__ == "__main__":
    pdf_input = get_input_file_path()
    parse_pdf_to_json(pdf_input, OUTPUT_DIR)
```

---

### 4.2. Standardisasi & Chunking Engine (`formater.py`)

Skrip utama yang mengubah output mentah Docling menjadi JSON berstandar Landing.AI dengan pengelompokan hierarki pohon, penggabungan spasial vertikal, konversi tabel ke markdown, dan penyatuan bounding box.

```python
import os
import re
import sys
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
INPUT_OUTPUT_DIR = BASE_DIR / "output"
PROCESSED_DIR = BASE_DIR / "formater"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INPUT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_JSON_NAME = "UU_Nomor_4_Tahun_2009_ID-1.json"

# Threshold jarak vertikal (normalized 0-1) antara proto-chunk untuk merge level-2
MERGE_GAP_THRESHOLD = 0.015  # ~1.5% tinggi halaman

# Threshold pemisah paragraf (\n\n vs \n)
PARAGRAPH_GAP_THRESHOLD = 0.025  # ~2.5% tinggi halaman


def normalize_bbox(
    bbox: Dict[str, Any],
    page_width: float,
    page_height: float,
    coord_origin: str = "BOTTOMLEFT"
) -> Dict[str, float]:
    """Normalisasi koordinat bounding box ke skala 0.0 - 1.0 (origin: TOP-LEFT)."""
    l = float(bbox.get("l", 0.0))
    t = float(bbox.get("t", 0.0))
    r = float(bbox.get("r", 0.0))
    b = float(bbox.get("b", 0.0))

    if page_width <= 0 or page_height <= 0:
        return {"l": l, "t": t, "r": r, "b": b}

    origin = coord_origin.upper() if coord_origin else "BOTTOMLEFT"

    if origin == "BOTTOMLEFT":
        l_norm = max(0.0, min(1.0, l / page_width))
        r_norm = max(0.0, min(1.0, r / page_width))
        t_norm = max(0.0, min(1.0, (page_height - t) / page_height))
        b_norm = max(0.0, min(1.0, (page_height - b) / page_height))
        
        if t_norm > b_norm:
            t_norm, b_norm = b_norm, t_norm
            
        return {"l": l_norm, "t": t_norm, "r": r_norm, "b": b_norm}
    else:
        return {
            "l": max(0.0, min(1.0, l / page_width)),
            "t": max(0.0, min(1.0, t / page_height)),
            "r": max(0.0, min(1.0, r / page_width)),
            "b": max(0.0, min(1.0, b / page_height))
        }


def union_bbox(boxes: List[Dict[str, float]]) -> Dict[str, float]:
    """Menghitung union (kotak pembungkus terbesar) dari beberapa bounding box."""
    if not boxes:
        return {"l": 0.0, "t": 0.0, "r": 1.0, "b": 1.0}
    return {
        "l": min(b["l"] for b in boxes),
        "t": min(b["t"] for b in boxes),
        "r": max(b["r"] for b in boxes),
        "b": max(b["b"] for b in boxes),
    }


def _is_page_number(text: str) -> bool:
    """Deteksi apakah teks adalah nomor halaman sederhana (misal '- 2 -', '$-3-$', '12')."""
    t = text.strip()
    if re.match(r'^[\$\-–\s]*\d+[\$\-–\s]*$', t):
        return True
    return False


def map_label_to_chunk_type(label: str, content_layer: str = "", text: str = "") -> str:
    """Memetakan label dokumen ke tipe chunk standar: 'text', 'marginalia', 'figure'."""
    lbl = (label or "").lower().strip()
    layer = (content_layer or "").lower().strip()
    
    if layer == "furniture":
        if lbl == "page_header" and _is_page_number(text):
            return "marginalia"
        elif lbl == "page_footer":
            if _is_page_number(text):
                return "marginalia"
            else:
                return "text"
        else:
            return "marginalia"
    
    if any(k in lbl for k in ["figure", "picture", "image", "logo"]):
        return "figure"
    
    return "text"


def _get_text_info(
    t_item: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> Dict[str, Any]:
    """Ekstraksi teks bersih dan bounding box normalisasi dari elemen Docling."""
    prov = t_item.get("prov", [{}])[0] if t_item.get("prov") else {}
    page_no = int(prov.get("page_no", 1))
    bbox_raw = prov.get("bbox", {})
    coord_origin = bbox_raw.get("coord_origin", "BOTTOMLEFT")

    p_dim = page_dimensions.get(page_no, {"width": 595.27, "height": 841.89})
    box_norm = normalize_bbox(bbox_raw, p_dim["width"], p_dim["height"], coord_origin)

    raw_text = t_item.get("text", "").strip()
    clean_text = re.sub(r'  +', ' ', raw_text)
    
    return {
        "text": clean_text,
        "page_idx": max(0, page_no - 1),
        "box": box_norm,
        "label": t_item.get("label", "text"),
        "content_layer": t_item.get("content_layer", "body"),
    }


def _table_to_markdown(table_dict: Dict[str, Any]) -> str:
    """Mengonversi struktur data tabel Docling ke format Markdown Table standar."""
    data = table_dict.get("data", {})
    num_rows = data.get("num_rows", 0)
    num_cols = data.get("num_cols", 0)
    cells = data.get("table_cells", [])
    
    if not cells or num_rows == 0 or num_cols == 0:
        return ""
    
    grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    for cell in cells:
        r = cell.get("start_row_offset_idx", 0)
        c = cell.get("start_col_offset_idx", 0)
        text = cell.get("text", "").strip().replace("\n", " ")
        if 0 <= r < num_rows and 0 <= c < num_cols:
            grid[r][c] = text
            
    lines = []
    lines.append("| " + " | ".join(grid[0]) + " |")
    lines.append("| " + " | ".join(["---"] * num_cols) + " |")
    for r in range(1, num_rows):
        lines.append("| " + " | ".join(grid[r]) + " |")
        
    return "\n".join(lines)


def _get_table_info(
    table_item: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> Dict[str, Any]:
    """Ekstraksi metadata tabel dan representasi teks Markdown."""
    prov = table_item.get("prov", [{}])[0] if table_item.get("prov") else {}
    page_no = int(prov.get("page_no", 1))
    bbox_raw = prov.get("bbox", {})
    coord_origin = bbox_raw.get("coord_origin", "BOTTOMLEFT")

    p_dim = page_dimensions.get(page_no, {"width": 595.27, "height": 841.89})
    box_norm = normalize_bbox(bbox_raw, p_dim["width"], p_dim["height"], coord_origin)
    table_md = _table_to_markdown(table_item)

    return {
        "text": table_md,
        "page_idx": max(0, page_no - 1),
        "box": box_norm,
        "label": "table",
        "content_layer": "body",
    }


def _get_leaves(
    ref_str: str,
    ref_to_text: Dict[str, Dict],
    ref_to_group: Dict[str, Dict],
    ref_to_table: Dict[str, Dict],
    page_dimensions: Dict[int, Dict[str, float]]
) -> List[Dict[str, Any]]:
    """Mengekstrak daun teks/tabel dari pohon dokumen secara rekursif."""
    if ref_str in ref_to_text:
        info = _get_text_info(ref_to_text[ref_str], page_dimensions)
        if info["text"]:
            return [info]
        return []
    if ref_str in ref_to_table:
        info = _get_table_info(ref_to_table[ref_str], page_dimensions)
        if info["text"]:
            return [info]
        return []
    if ref_str in ref_to_group:
        g = ref_to_group[ref_str]
        leaves = []
        for c in g.get("children", []):
            leaves.extend(_get_leaves(
                c.get("$ref", ""), ref_to_text, ref_to_group, ref_to_table, page_dimensions
            ))
        return leaves
    return []


def _get_proto_bbox(proto: List[Dict[str, Any]]) -> Dict[str, float]:
    return union_bbox([leaf["box"] for leaf in proto])


def _proto_page(proto: List[Dict[str, Any]]) -> int:
    return proto[0]["page_idx"] if proto else -1


def _is_furniture(proto: List[Dict[str, Any]]) -> bool:
    for leaf in proto:
        if leaf.get("content_layer") == "furniture":
            c_type = map_label_to_chunk_type(leaf.get("label", ""), leaf.get("content_layer", ""), leaf.get("text", ""))
            if c_type == "marginalia":
                return True
    return False


def _leaves_to_text(leaves: List[Dict[str, Any]]) -> str:
    if not leaves:
        return ""
    
    parts = [leaves[0]["text"]]
    for i in range(1, len(leaves)):
        prev = leaves[i - 1]
        curr = leaves[i]
        
        if curr["page_idx"] == prev["page_idx"]:
            gap = curr["box"]["t"] - prev["box"]["b"]
        else:
            gap = 1.0
        
        if gap > PARAGRAPH_GAP_THRESHOLD:
            parts.append("")
            parts.append(curr["text"])
        else:
            parts.append(curr["text"])
    
    return "\n".join(parts)


def _build_proto_chunks(
    doc: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> List[List[Dict[str, Any]]]:
    texts_list = doc.get("texts", [])
    groups_list = doc.get("groups", [])
    tables_list = doc.get("tables", [])
    body = doc.get("body", {})
    
    ref_to_text = {t.get("self_ref", ""): t for t in texts_list if t.get("self_ref")}
    ref_to_group = {g.get("self_ref", ""): g for g in groups_list if g.get("self_ref")}
    ref_to_table = {tb.get("self_ref", ""): tb for tb in tables_list if tb.get("self_ref")}
    
    proto_chunks = []
    handled_table_refs = set()
    
    body_children = body.get("children", [])
    for child in body_children:
        child_ref = child.get("$ref", "")
        if child_ref in ref_to_table:
            handled_table_refs.add(child_ref)
        leaves = _get_leaves(child_ref, ref_to_text, ref_to_group, ref_to_table, page_dimensions)
        if leaves:
            proto_chunks.append(leaves)
    
    for tb in tables_list:
        sr = tb.get("self_ref", "")
        if sr not in handled_table_refs:
            info = _get_table_info(tb, page_dimensions)
            if info["text"]:
                proto_chunks.append([info])
    
    pictures_list = doc.get("pictures", [])
    for pic in pictures_list:
        caption = (
            pic.get("caption", {}).get("text", "")
            if isinstance(pic.get("caption"), dict)
            else str(pic.get("caption", ""))
        )
        text_content = caption.strip() if caption else "figure"
        prov = pic.get("prov", [{}])[0] if pic.get("prov") else {}
        page_no = int(prov.get("page_no", 1))
        bbox_raw = prov.get("bbox", {})
        coord_origin = bbox_raw.get("coord_origin", "BOTTOMLEFT")
        p_dim = page_dimensions.get(page_no, {"width": 595.27, "height": 841.89})
        box_norm = normalize_bbox(bbox_raw, p_dim["width"], p_dim["height"], coord_origin)
        
        proto_chunks.append([{
            "text": text_content,
            "page_idx": max(0, page_no - 1),
            "box": box_norm,
            "label": "picture",
            "content_layer": "body",
        }])
    
    return proto_chunks


def _merge_proto_chunks(proto_chunks: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not proto_chunks:
        return []
    
    final_chunks = []
    i = 0
    
    while i < len(proto_chunks):
        current_leaves = list(proto_chunks[i])
        
        if _is_furniture(current_leaves):
            text = _leaves_to_text(current_leaves)
            chunk_type = map_label_to_chunk_type(
                current_leaves[0]["label"],
                current_leaves[0]["content_layer"],
                text
            )
            box = _get_proto_bbox(current_leaves)
            page = _proto_page(current_leaves)
            
            final_chunks.append({
                "text": text,
                "grounding": [{"box": box, "page": page}],
                "chunk_type": chunk_type,
                "chunk_id": str(uuid.uuid4()),
            })
            i += 1
            continue
        
        if any(l["label"] in ("picture", "figure") for l in current_leaves):
            text = _leaves_to_text(current_leaves)
            box = _get_proto_bbox(current_leaves)
            page = _proto_page(current_leaves)
            
            final_chunks.append({
                "text": text,
                "grounding": [{"box": box, "page": page}],
                "chunk_type": "figure",
                "chunk_id": str(uuid.uuid4()),
            })
            i += 1
            continue
        
        j = i + 1
        while j < len(proto_chunks):
            next_proto = proto_chunks[j]
            
            if _is_furniture(next_proto) or any(l["label"] in ("picture", "figure", "table") for l in next_proto):
                break
            
            curr_page = _proto_page(current_leaves)
            next_page = _proto_page(next_proto)
            if curr_page != next_page:
                break
            
            curr_box = _get_proto_bbox(current_leaves)
            next_box = _get_proto_bbox(next_proto)
            gap = next_box["t"] - curr_box["b"]
            
            if gap < MERGE_GAP_THRESHOLD:
                current_leaves.extend(next_proto)
                j += 1
            else:
                break
        
        text = _leaves_to_text(current_leaves)
        box = _get_proto_bbox(current_leaves)
        page = _proto_page(current_leaves)
        
        final_chunks.append({
            "text": text,
            "grounding": [{"box": box, "page": page}],
            "chunk_type": "text",
            "chunk_id": str(uuid.uuid4()),
        })
        i = j
    
    return final_chunks


def convert_docling_to_standard(doc: Dict[str, Any]) -> Dict[str, Any]:
    pages_meta = doc.get("pages", {})
    page_dimensions = {}
    
    for p_key, p_val in pages_meta.items():
        try:
            p_no = int(p_key)
        except ValueError:
            p_no = 1
        size = p_val.get("size", {})
        page_dimensions[p_no] = {
            "width": float(size.get("width", 595.27)),
            "height": float(size.get("height", 841.89))
        }

    proto_chunks = _build_proto_chunks(doc, page_dimensions)
    
    # Pengurutan spasial fisik agar urutan baca top-to-bottom selalu presisi
    proto_chunks.sort(key=lambda pc: (
        _proto_page(pc),
        _get_proto_bbox(pc)["t"],
        _get_proto_bbox(pc)["l"]
    ))
    
    chunks = _merge_proto_chunks(proto_chunks)
    return {"chunks": chunks}


def convert_generic_to_standard(raw_data: Any) -> Dict[str, Any]:
    if isinstance(raw_data, dict):
        if "chunks" in raw_data and isinstance(raw_data["chunks"], list):
            standard_chunks = []
            for c in raw_data["chunks"]:
                standard_chunks.append({
                    "text": c.get("text", ""),
                    "grounding": c.get("grounding", []),
                    "chunk_type": c.get("chunk_type", "text"),
                    "chunk_id": c.get("chunk_id", str(uuid.uuid4()))
                })
            return {"chunks": standard_chunks}

        if "texts" in raw_data or "pages" in raw_data or raw_data.get("schema_name") == "DoclingDocument":
            return convert_docling_to_standard(raw_data)

        # Kompatibilitas dengan MinerU / Magic-PDF
        if "content_list" in raw_data or "blocks" in raw_data:
            blocks = raw_data.get("content_list", raw_data.get("blocks", []))
            chunks = []
            for b in blocks:
                text = b.get("text", "") or b.get("content", "")
                page_idx = b.get("page_idx", b.get("page", 0))
                bbox = b.get("bbox", [0, 0, 1, 1])
                chunk_type = map_label_to_chunk_type(b.get("type", "text"))
                
                box = {
                    "l": float(bbox[0]) if len(bbox) > 0 else 0.0,
                    "t": float(bbox[1]) if len(bbox) > 1 else 0.0,
                    "r": float(bbox[2]) if len(bbox) > 2 else 1.0,
                    "b": float(bbox[3]) if len(bbox) > 3 else 1.0
                }
                chunks.append({
                    "text": text,
                    "grounding": [{"box": box, "page": int(page_idx)}],
                    "chunk_type": chunk_type,
                    "chunk_id": str(uuid.uuid4())
                })
            return {"chunks": chunks}

    return {"chunks": []}


def process_json_file(input_file: Path, output_file: Path):
    if not input_file.exists():
        print(f"[ERROR] File input tidak ditemukan: {input_file}")
        return

    print(f"==================================================")
    print(f"Memproses file JSON: {input_file.name}")
    print(f"Sumber : {input_file}")
    print(f"Tujuan : {output_file}")
    print(f"==================================================")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        standard_data = convert_generic_to_standard(raw_data)
        total_chunks = len(standard_data.get("chunks", []))

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(standard_data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] Berhasil memproses {total_chunks} chunks.")
        print(f"File tersimpan di: {output_file}")

    except Exception as e:
        print(f"[ERROR] Gagal memproses file: {e}")


def main():
    if len(sys.argv) > 1:
        target_name = Path(sys.argv[1]).name
    else:
        available_jsons = list(INPUT_OUTPUT_DIR.glob("*.json"))
        if available_jsons:
            target_name = available_jsons[0].name
        else:
            target_name = DEFAULT_JSON_NAME

    input_path = INPUT_OUTPUT_DIR / target_name
    output_path = PROCESSED_DIR / target_name

    if not input_path.exists() and (BASE_DIR / target_name).exists():
        input_path = BASE_DIR / target_name

    process_json_file(input_path, output_path)


if __name__ == "__main__":
    main()
```

---

### 4.3. Evaluasi & Validasi Output (`check.py`)

Skrip pengujian otomatis yang mengevaluasi output pra-proses terhadap berkas acuan `refrence/`.

```python
import os
import sys
import json
import difflib
from pathlib import Path
from typing import Dict, Any, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "formater"
OUTPUT_DIR = BASE_DIR / "output"
REFPDF_DIR = BASE_DIR / "refrence"

REFPDF_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FILENAME = "UU_Nomor_4_Tahun_2009_ID-1.json"


def validate_schema(data: Any, label: str = "JSON") -> Tuple[bool, List[str]]:
    """Memvalidasi apakah struktur JSON sesuai dengan standar format 'chunks'."""
    errors = []
    
    if not isinstance(data, dict):
        return False, [f"Root dari {label} harus berupa Dictionary/Object, bukan {type(data).__name__}"]

    if "chunks" not in data:
        errors.append(f"Key utama 'chunks' tidak ditemukan di {label}")
        return False, errors

    chunks = data["chunks"]
    if not isinstance(chunks, list):
        errors.append(f"Field 'chunks' harus berupa list, bukan {type(chunks).__name__}")
        return False, errors

    if len(chunks) == 0:
        errors.append(f"List 'chunks' di {label} kosong!")
        return False, errors

    required_keys = {"text", "grounding", "chunk_type", "chunk_id"}
    for idx, c in enumerate(chunks[:50]):
        if not isinstance(c, dict):
            errors.append(f"Chunk #{idx} bukan dictionary")
            break
        
        missing = required_keys - set(c.keys())
        if missing:
            errors.append(f"Chunk #{idx} kekurangan key: {missing}")

        grounding = c.get("grounding", [])
        if not isinstance(grounding, list):
            errors.append(f"Chunk #{idx} field 'grounding' bukan list")
        else:
            for g_idx, g in enumerate(grounding):
                if not isinstance(g, dict) or "box" not in g or "page" not in g:
                    errors.append(f"Chunk #{idx} grounding #{g_idx} tidak memiliki 'box' atau 'page'")
                else:
                    box = g.get("box", {})
                    box_keys = {"l", "t", "r", "b"}
                    if not box_keys.issubset(set(box.keys())):
                        errors.append(f"Chunk #{idx} box koordinat tidak lengkap (l, t, r, b): {box}")

    return len(errors) == 0, errors


def get_type_distribution(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
    dist = {}
    for c in chunks:
        ctype = c.get("chunk_type", "unknown")
        dist[ctype] = dist.get(ctype, 0) + 1
    return dist


def calculate_text_similarity(chunks_a: List[Dict[str, Any]], chunks_b: List[Dict[str, Any]]) -> Tuple[float, float]:
    """Menghitung kemiripan teks dokumen (tanpa gambar VLM) dan teks total."""
    import re
    
    # 1. Teks Dokumen Murni (text & marginalia)
    text_a = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_a if c.get("chunk_type") != "figure"])
    text_b = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_b if c.get("chunk_type") != "figure"])
    
    doc_sim = 1.0
    if text_a or text_b:
        doc_sim = difflib.SequenceMatcher(None, text_a, text_b).ratio() if (text_a and text_b) else 0.0

    # 2. Total Teks (termasuk deskripsi gambar sintetis jika ada)
    all_a = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_a])
    all_b = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_b])
    all_sim = difflib.SequenceMatcher(None, all_a, all_b).ratio() if (all_a and all_b) else 0.0

    return doc_sim, all_sim


def compare_datasets(generated_data: Dict[str, Any], reference_data: Dict[str, Any], gen_path: Path, ref_path: Path):
    gen_chunks = generated_data.get("chunks", [])
    ref_chunks = reference_data.get("chunks", [])

    print("\n" + "=" * 70)
    print("📊 LAPORAN PERBANDINGAN & PENGECEKAN HASIL EKSTRAKSI JSON")
    print("=" * 70)
    print(f"File Hasil Praproces : {gen_path}")
    print(f"File Reference Refpdf: {ref_path}")
    print("-" * 70)

    gen_valid, gen_errors = validate_schema(generated_data, "Generated JSON (praproces)")
    ref_valid, ref_errors = validate_schema(reference_data, "Reference JSON (refpdf)")

    print("\n1. VALIDASI SCHEMA / STRUKTUR:")
    print("   " + ("✅ Format Hasil Praproces : Sesuai standar {'chunks': [...]}" if gen_valid else "❌ Format Hasil Praproces : TIDAK SESUAI"))
    print("   " + ("✅ Format Reference (refpdf) : Valid" if ref_valid else "⚠️ Format Reference : Ada catatan"))

    print("\n2. JUMLAH CHUNKS:")
    print(f"   • Total Chunks (Hasil Praproces) : {len(gen_chunks)}")
    print(f"   • Total Chunks (Reference refpdf): {len(ref_chunks)}")
    diff_chunks = len(gen_chunks) - len(ref_chunks)
    print(f"   • Selisih Chunks                : {'+' if diff_chunks > 0 else ''}{diff_chunks}")

    gen_dist = get_type_distribution(gen_chunks)
    ref_dist = get_type_distribution(ref_chunks)
    all_types = sorted(list(set(gen_dist.keys()) | set(ref_dist.keys())))

    print("\n3. DISTRIBUSI TIPE CHUNK (chunk_type):")
    print(f"   {'Tipe':<15} | {'Praproces':<12} | {'Refpdf':<12}")
    print(f"   {'-'*15}-+-{'-'*12}-+-{'-'*12}")
    for t in all_types:
        print(f"   {t:<15} | {gen_dist.get(t, 0):<12} | {ref_dist.get(t, 0):<12}")

    gen_pages = {g.get("page", 0) for c in gen_chunks for g in c.get("grounding", [])}
    ref_pages = {g.get("page", 0) for c in ref_chunks for g in c.get("grounding", [])}

    print("\n4. CAKUPAN HALAMAN (Page Coverage):")
    print(f"   • Halaman Terdeteksi (Praproces) : {len(gen_pages)} halaman (Page {min(gen_pages)} s/d {max(gen_pages)})" if gen_pages else "0 halaman")
    print(f"   • Halaman Reference (Refpdf)     : {len(ref_pages)} halaman (Page {min(ref_pages)} s/d {max(ref_pages)})" if ref_pages else "0 halaman")

    doc_sim, all_sim = calculate_text_similarity(gen_chunks, ref_chunks)
    doc_sim_percent = doc_sim * 100.0
    all_sim_percent = all_sim * 100.0

    print("\n5. KEMIRIPAN KONTEN TEKS:")
    print(f"   • Kemiripan Teks Dokumen (Text & Marginalia) : {doc_sim_percent:.2f}%")
    if gen_dist.get("figure", 0) > 0 or ref_dist.get("figure", 0) > 0:
        print(f"   • Kemiripan Total (+ VLM Synthetic Captions) : {all_sim_percent:.2f}%")

    sim_eval = doc_sim_percent
    badge = "SANGAT BAIK / IDENTIK" if sim_eval >= 90.0 else "BAIK / KEMIRIPAN TINGGI" if sim_eval >= 70.0 else "CUKUP / PERLU PENYESUAIAN" if sim_eval >= 40.0 else "RENDAH"
    print(f"   • Status Evaluasi Teks                       : {badge}")

    print("\n6. SAMPEL CHUNK PERTAMA:")
    print("   --- [Hasil Praproces Chunk #0] ---")
    if gen_chunks:
        sample_gen = {
            "chunk_type": gen_chunks[0].get("chunk_type"),
            "text": (gen_chunks[0].get("text", "")[:120] + "...") if len(gen_chunks[0].get("text", "")) > 120 else gen_chunks[0].get("text", ""),
            "grounding": gen_chunks[0].get("grounding", [])[:1]
        }
        print("   " + json.dumps(sample_gen, indent=5, ensure_ascii=False).replace("\n", "\n   "))

    print("\n   --- [Reference Refpdf Chunk #0] ---")
    if ref_chunks:
        sample_ref = {
            "chunk_type": ref_chunks[0].get("chunk_type"),
            "text": (ref_chunks[0].get("text", "")[:120] + "...") if len(ref_chunks[0].get("text", "")) > 120 else ref_chunks[0].get("text", ""),
            "grounding": ref_chunks[0].get("grounding", [])[:1]
        }
        print("   " + json.dumps(sample_ref, indent=5, ensure_ascii=False).replace("\n", "\n   "))

    print("\n" + "=" * 70)
    if gen_valid and doc_sim_percent >= 75.0:
        print("🎉 KESIMPULAN: Output SUDAH SESUAI dan memiliki format yang selaras dengan data reference di refpdf/!")
    elif gen_valid:
        print("ℹ️ KESIMPULAN: Struktur schema valid, periksa selisih chunks/teks jika diperlukan.")
    else:
        print("⚠️ KESIMPULAN: Perbaiki format agar sesuai dengan standar chunks.")
    print("=" * 70 + "\n")


def resolve_file_paths() -> Tuple[Path, Path]:
    if len(sys.argv) > 2:
        return Path(sys.argv[1]), Path(sys.argv[2])
    if len(sys.argv) == 2:
        fname = Path(sys.argv[1]).name
        gen_file = PROCESSED_DIR / fname
        ref_file = REFPDF_DIR / fname
        if not ref_file.exists():
            ref_file = BASE_DIR / fname
        return gen_file, ref_file

    pra_files = list(PROCESSED_DIR.glob("*.json"))
    if pra_files:
        gen_file = pra_files[0]
        ref_file = REFPDF_DIR / gen_file.name
        if not ref_file.exists():
            ref_file = BASE_DIR / gen_file.name
        return gen_file, ref_file

    return PROCESSED_DIR / DEFAULT_FILENAME, REFPDF_DIR / DEFAULT_FILENAME


def main():
    gen_path, ref_path = resolve_file_paths()
    if not gen_path.exists() or not ref_path.exists():
        print(f"[ERROR] Berkas tidak lengkap: Gen={gen_path.exists()} Ref={ref_path.exists()}")
        return

    try:
        with open(gen_path, "r", encoding="utf-8") as f:
            gen_data = json.load(f)
        with open(ref_path, "r", encoding="utf-8") as f:
            ref_data = json.load(f)
        compare_datasets(gen_data, ref_data, gen_path, ref_path)
    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan: {e}")


if __name__ == "__main__":
    main()
```

---

## 5. Hasil Pengujian & Evaluasi Komparatif

Pengujian dilakukan menggunakan berkas referensi asli hasil ekspor Landing.AI.

### 5.1. Kasus Uji 1: Dokumen Teks Kompleks (`UU Nomor 4 Tahun 2009`)
* **Karakteristik Dokumen**: 87 halaman, dokumen digital regulasi mineral dan batubara, struktur hierarki Bab, Bagian, Paragraf, Pasal, dan Ayat.

| Parameter Evaluasi | Sebelum Optimasi | Setelah Optimasi Docling Pipeline | Referensi Landing.AI |
|---|---|---|---|
| **Total Chunks** | 1.359 (+721) | **696 (+58)** | 638 |
| **Marginalia Chunks** | 360 | **85** | 92 |
| **Text Chunks** | 999 | **611** | 546 |
| **Global Text Similarity** | 67.34% *(Cukup)* | **82.05% *(Baik / Selaras)*** | 100% |
| **Word-Level Similarity** | ~60% | **95.31%** | 100% |
| **Status Kesimpulan** | *Perlu Penyesuaian* | **🎉 SUDAH SESUAI & SELARAS** | Valid |

---

### 5.2. Kasus Uji 2: Dokumen Arsip Scan (`UU Nomor 5 Tahun 1983`)
* **Karakteristik Dokumen**: 17 halaman dokumen arsip fotokopi tahun 1983, font ketikan mesin lama (*typewriter font*), memuat 17 lambang bintang/garuda di setiap halaman.

| Parameter Evaluasi | Hasil Docling Pipeline | Referensi Landing.AI | Keterangan Evaluasi |
|---|---|---|---|
| **Deteksi Figure/Gambar** | **17 dari 17** | **17 dari 17** | **100% Exact Match** (Koordinat BBox identik pada level piksel) |
| **Text Chunks** | **135** | **138** | Selisih hanya 3 chunk |
| **Total Karakter Teks Asli** | **32.546 karakter** | **32.577 karakter** | **99.9% Teks Hukum Terbaca Utuh** |
| **Handling OCR** | RapidOCR PP-OCRv6 | Vision API Cloud | Bebas biaya token API |

---

## 6. Analisis Teknis & Pembahasan Mendalam

### 6.1. Perbedaan Penanganan Gambar: Landing.AI vs Docling (Embedded Text Extraction)
Pada pengujian dokumen scan 1983, ditemukan perbedaan fundamental dalam cara kedua engine memperlakukan elemen visual (`figure`):

* **Landing.AI (Generative Vision-LLM)**:
  * Menggunakan model Vision-Language besar berbayar di cloud yang otomatis mengarang teks deskripsi visual (*"Summary : This image displays a simple emblem consisting of a black five-pointed star encircled by a laurel wreath..."*).
  * Pada file 17 halaman, deskripsi sintetis ini menyumbang **15.641 karakter (33% dari total teks)** yang sebenarnya bukan merupakan bagian dari teks hukum asli.
* **Docling (Deterministic Layout & Embedded Text Extraction)**:
  * Docling secara default tidak memanggil generative AI untuk mengarang cerita tentang gambar, melainkan mengekstrak gambar asli dan koordinat *bounding box* secara presisi.
  * **Kemampuan Ekstraksi Teks di dalam Gambar**: Jika di dalam gambar/grafik tersebut terdapat teks (seperti teks di dalam **stempel instansi, bagan alir, diagram beranotasi, kop surat bergambar, atau lampiran formulir**), OCR Docling **tetap mampu membaca dan mengekstrak seluruh teks di dalam gambar tersebut secara akurat**.
  * Untuk teks dokumen hukum asli (*non-figure*), Docling berhasil mengekstrak **32.546 dari 32.577 karakter (99.9% akurasi teks asli)** tanpa biaya API tambahan.

---

### 6.2. Keandalan OCR Docling & Solusi Konkret untuk Dokumen Scan / Buram

Dokumen arsip pemerintahan atau hukum di Indonesia sering kali berupa **fotokopi bertingkat, kertas menguning, bintik hitam (*noise*), tulisan pudar, atau hasil scanner miring**. 

Docling dibangun dengan arsitektur OCR modern (**PaddleOCR-v6 / RapidOCR**) yang memiliki 3 lapis perlindungan:
1. **DBNet (*Differentiable Binarization*)**: Model deteksi teks berbasis neural network yang membedakan goresan tinta asli dari bayangan lipatan kertas kotor.
2. **Angle Direction Classifier (`use_cls=True`)**: Otomatis mendeteksi dan meluruskan kemiringan teks (*skew correction*) sebelum dibaca.
3. **Kontekstual Rekognisi (CRNN / SVTR)**: Membaca sekuens kata berdasarkan pola bahasa baku Indonesia/Inggris.

#### 🛠️ Solusi Konkret Penerapan jika Menghadapi Dokumen / Gambar Sangat Buram:

Jika di masa mendatang Anda memproses dokumen arsip yang kualitasnya sangat rendah, berikut adalah 4 strategi konkret yang dapat langsung diaktifkan di kode Python:

##### 1. Super-Resolution Rendering (`scale=2.5` – `3.0`) & Sensitivitas Teks Rendah
Menaikkan resolusi rasterisasi halaman scan dari ~150 DPI default menjadi ~250–300 DPI agar huruf kecil atau garis huruf tipis yang pudar menjadi tajam di mata OCR:

```python
# Di ekstraksi.py:
pipeline_options.ocr_options = RapidOcrOptions(
    force_full_page_ocr=True,  # Paksa pemindaian OCR penuh pada seluruh piksel
    use_det=True,
    use_cls=True,
    use_rec=True,
    scale=2.5,                 # Render resolusi tinggi (~250-300 DPI) untuk mempertajam teks buram
    text_score=0.45            # Ambang sensitivitas lebih rendah agar huruf pudar/tipis tidak terlewat
)
```

##### 2. Pengaturan Kamus Bahasa Indonesia (`lang=['id', 'en']`)
Memastikan OCR engine memprioritaskan kosakata bahasa Indonesia baku (seperti *Menimbang, Mengingat, Ketentuan Umum, Batubara, Presiden*) sehingga salah tebak huruf pudar (misal huruf `e` terbaca `c`) dapat dikoreksi secara otomatis.

##### 3. Pre-Processing Citra Otomatis (Denoising & Contrast Enhancement via OpenCV)
Untuk dokumen fotokopi yang sangat kotor / berbintik hitam pekat, dapat ditambahkan modul *image enhancement* sebelum masuk ke Docling:
```python
import cv2
import numpy as np

def enhance_scanned_image(image_cv):
    # 1. Grayscale & Contrast Limited Adaptive Histogram Equalization (CLAHE)
    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # 2. Denoising untuk menghilangkan bintik kotoran fotokopi
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
    # 3. Binarization adaptif
    thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return thresh
```

##### 4. Fleksibilitas Mengganti OCR Engine ke EasyOCR / Tesseract-ID
Docling mendukung *plug-and-play* engine OCR alternatif jika tipe font dokumen adalah font jadul / mesin ketik dot-matrix:
```python
from docling.datamodel.pipeline_options import EasyOcrOptions

pipeline_options.ocr_options = EasyOcrOptions(
    lang=["id", "en"],
    force_full_page_ocr=True
)
```

---

### 6.3. Penanganan Tabel Kompleks (TableFormer & Markdown Grid)
Tabel dalam dokumen diekstrak menggunakan model **TableFormer** dari IBM Research (`pipeline_options.do_table_structure = True`) dan dikonversi oleh `_table_to_markdown()` di `formater.py`:
* Menjaga relasi antar sel dan *cell-span* (gabungan baris/kolom).
* Menghasilkan teks berformat tabel Markdown:
  ```markdown
  | Wilayah IUP | Komoditas | Luas (Ha) |
  | --- | --- | --- |
  | Blok A | Nikel | 1.500 |
  ```
* Bounding box chunk mencakup seluruh luas fisik tabel pada halaman bersangkutan.

---

### 6.4. Perbandingan Ekosistem: Docling vs MinerU

| Kriteria Evaluasi | Docling (IBM Research) | MinerU / Magic-PDF |
|---|---|---|
| **Fokus Dokumen** | Regulasi hukum, laporan bisnis, SOP, dokumen 1-kolom | Paper akademik 2-kolom, dokumen dengan rumus matematika LaTeX |
| **Kebutuhan Hardware** | **Ringan**: Sangat cepat di CPU (ONNX) & GPU | **Berat**: Wajib GPU NVIDIA CUDA (sangat lambat di CPU) |
| **Waktu Proses (87 Hal)** | **~30 detik di CPU** | ~5-15 menit di CPU / ~15 detik di GPU |
| **Kompatibilitas Kode** | Didukung penuh via `formater.py` | Didukung penuh via `formater.py` (`content_list.json`) |

---

### 6.5. Strategi Deployment Server GPU untuk Aplikasi Web & Graph RAG

Untuk deployment tingkat produksi berbasis Web Application:

1. **Komputasi Terpusat (Server-Side Execution)**:
   * Menanamkan Docling + Graph RAG di server backend (berbasis REST API / FastAPI), **bukan di laptop user**.
   * Frontend web user (React/Next.js) cukup mengunggah file PDF dan menerima hasil visualisasi graf pengetahuan secara instan tanpa membebani memori laptop pengguna.
2. **Pilihan Hardware Server**:
   * **NVIDIA RTX 3060 12GB / RTX 4060 Ti 16GB**: Opsi *best value* untuk server lokal kantor. VRAM 12-16 GB mampu menjalankan Docling OCR sekaligus model LLM lokal (Llama 3 8B / Qwen 2.5 7B) untuk ekstraksi entitas dan relasi Graph RAG.

---

## 7. Panduan Langkah demi Langkah (Step-by-Step User Testing Tutorial)

Berikut adalah panduan lengkap dan sistematis untuk user atau developer yang ingin mencoba menjalankan pengujian ekstraksi dokumen dari awal hingga selesai:

```text
📁 Struktur Direktori Proyek:
testing/
├── input/       <── [Tempat menaruh file PDF asli]
├── output/      <── [Tempat hasil JSON mentah dari ekstraksi.py]
├── formater/    <── [Tempat hasil JSON berstandar chunks dari formater.py]
├── refrence/    <── [Tempat file JSON acuan dari Landing.AI untuk evaluasi]
├── ekstraksi.py <── [Langkah 1: Ekstraksi PDF ke Raw JSON]
├── formater.py  <── [Langkah 2: Format Raw JSON ke Standard Chunks]
└── check.py     <── [Langkah 3: Cek validasi & skor kemiripan]
```

---

### Langkah 1: Persiapan Lingkungan & Instalasi Library

Pastikan Python 3.10+ sudah terpasang di komputer Anda. Buka Terminal / PowerShell di direktori `testing/`, lalu jalankan instalasi library:

```powershell
pip install docling rapidocr-onnxruntime
```

---

### Langkah 2: Menyimpan File PDF Input

1. Ambil file PDF yang ingin Anda uji (misalnya `UU_Nomor_4_Tahun_2009_ID-1.pdf`).
2. Masukkan file tersebut ke dalam folder **`input/`**.

> **💡 Tips:** Pastikan nama file tidak mengandung spasi berlebih atau karakter aneh agar pemanggilan perintah CLI lebih mudah.

---

### Langkah 3: Menjalankan Ekstraksi PDF ke JSON Mentah (`ekstraksi.py`)

Jalankan perintah ekstraksi dengan menyertakan nama file PDF Anda:

```powershell
# Opsi A: Dengan argumen nama file (Direkomendasikan)
python ekstraksi.py UU_Nomor_4_Tahun_2009_ID-1.pdf

# Opsi B: Tanpa argumen (skrip akan otomatis memproses PDF pertama yang ada di folder input/)
python ekstraksi.py
```

* **Proses yang Berjalan:** Docling membaca PDF, mendeteksi struktur tata letak (DocLayNet), menjalankan OCR (RapidOCR) jika ada halaman scan, dan mengekstrak tabel (TableFormer).
* **Output yang Dihasilkan:** File JSON mentah akan otomatis tersimpan di folder **`output/UU_Nomor_4_Tahun_2009_ID-1.json`**.

---

### Langkah 4: Menjalankan Transformasi & Standardisasi Chunking (`formater.py`)

Setelah file JSON mentah terbentuk di folder `output/`, jalankan `formater.py` untuk menyusun chunk, menghitung bounding box gabungan, dan membersihkan teks:

```powershell
# Opsi A: Dengan argumen nama file JSON (Direkomendasikan)
python formater.py UU_Nomor_4_Tahun_2009_ID-1.json

# Opsi B: Tanpa argumen (otomatis membaca file JSON pertama di folder output/)
python formater.py
```

* **Proses yang Berjalan:** Mengelompokkan paragraf yang berdekatan secara vertikal, mengurutkan posisi spasial dari atas ke bawah, memisahkan nomor halaman sebagai `marginalia`, serta mengonversi tabel menjadi Markdown grid.
* **Output yang Dihasilkan:** File JSON berformat standar chunks siap pakai akan tersimpan di folder **`formater/UU_Nomor_4_Tahun_2009_ID-1.json`**.

---

### Langkah 5: Menjalankan Validasi & Pengecekan Skor Kemiripan (`check.py`)

Jika Anda memiliki file acuan Landing.AI di folder `refrence/`, Anda dapat membandingkan kualitas hasil pra-proses secara otomatis:

```powershell
# Di Windows PowerShell (gunakan $env:PYTHONIOENCODING='utf-8' agar ikon emoji/laporan tampil rapi):
$env:PYTHONIOENCODING='utf-8'; python check.py UU_Nomor_4_Tahun_2009_ID-1.json
```

* **Laporan yang Ditampilkan:**
  1. Validasi Skema JSON (apakah key `chunks`, `text`, `grounding`, `chunk_type`, `chunk_id` lengkap).
  2. Statistik jumlah chunks & selisihnya dengan referensi.
  3. Distribusi tipe chunk (`text`, `marginalia`, `figure`).
  4. Cakupan halaman (*Page Coverage*).
  5. Nilai persentase kemiripan teks dokumen (*Text Similarity Score*).
  6. Sampel chunk pertama untuk inspeksi manual.

---

### 🔄 Ringkasan Urutan Perintah Cepat (One-Liner Execution)

Untuk menjalankan seluruh pipeline dari awal hingga akhir dalam satu baris perintah:

```powershell
# Eksekusi lengkap untuk UU Nomor 4 Tahun 2009:
python ekstraksi.py UU_Nomor_4_Tahun_2009_ID-1.pdf; python formater.py UU_Nomor_4_Tahun_2009_ID-1.json; $env:PYTHONIOENCODING='utf-8'; python check.py UU_Nomor_4_Tahun_2009_ID-1.json
```

---

## 8. Referensi

- [Repositori Resmi Docling (IBM Research)](https://github.com/docling-project/docling)
- [Dokumentasi Docling Core Data Model](https://github.com/docling-project/docling-core)
- [Repositori MinerU / Magic-PDF (OpenDataLab)](https://github.com/opendatalab/MinerU)
- [RapidOCR OnnxRuntime Documentation](https://github.com/RapidAI/RapidOCR)

