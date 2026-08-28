import os
import sys
import json
import time
from pathlib import Path

# Inisialisasi direktori dasar (relatif terhadap lokasi file skrip ini)
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

# Pastikan folder input dan output selalu tersedia
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# KONFIGURASI INPUT FILE
# Ubah nama file di bawah ini sesuai nama file PDF yang Anda simpan di folder 'input'
# Atau jalankan script dengan argumen: python testing1.py nama_file.pdf
# ==============================================================================
DEFAULT_FILE_NAME = "UU_Nomor_5_Tahun_1983_ID-7.pdf"  # Nama file PDF default di folder input


def get_input_file_path() -> Path:
    """Mendapatkan path lengkap ke file PDF di folder input."""
    if len(sys.argv) > 1:
        # Jika nama file atau path diberikan melalui argumen CLI
        arg_path = Path(sys.argv[1])
        if arg_path.is_absolute() or arg_path.exists():
            return arg_path
        return INPUT_DIR / arg_path.name
    
    # Gunakan default file name
    input_path = INPUT_DIR / DEFAULT_FILE_NAME
    
    # Jika file default belum ada, cari file PDF pertama yang tersedia di folder input
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

    # Tentukan path file output JSON berdasarkan nama file input
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