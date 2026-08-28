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

# Pastikan folder refpdf tersedia
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
    for idx, c in enumerate(chunks[:50]):  # Validasi sampel 50 chunk pertama
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

    is_valid = len(errors) == 0
    return is_valid, errors


def get_type_distribution(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Menghitung distribusi chunk_type."""
    dist = {}
    for c in chunks:
        ctype = c.get("chunk_type", "unknown")
        dist[ctype] = dist.get(ctype, 0) + 1
    return dist


def calculate_text_similarity(chunks_a: List[Dict[str, Any]], chunks_b: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Menghitung kemiripan teks keseluruhan.
    Mengembalikan (kemiripan_dokumen_teks, kemiripan_termasuk_gambar).
    
    Catatan: Landing.AI menghasilkan caption sintetis berbasis Vision-LLM (misal: 'Summary : This image...')
    untuk setiap figure/gambar, sedangkan Docling mengekstrak bounding box gambar tanpa memanggil Vision API.
    Oleh karena itu, kemiripan konten dokumen diukur dari chunk bertipe non-figure.
    """
    import re
    
    # 1. Teks dokumen (text + marginalia)
    text_a = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_a if c.get("chunk_type") != "figure"])
    text_b = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_b if c.get("chunk_type") != "figure"])
    
    doc_sim = 1.0
    if text_a or text_b:
        doc_sim = difflib.SequenceMatcher(None, text_a, text_b).ratio() if (text_a and text_b) else 0.0

    # 2. Seluruh teks (termasuk deskripsi gambar sintetis jika ada)
    all_a = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_a])
    all_b = "\n".join([re.sub(r'  +', ' ', c.get("text", "")) for c in chunks_b])
    all_sim = difflib.SequenceMatcher(None, all_a, all_b).ratio() if (all_a and all_b) else 0.0

    return doc_sim, all_sim


def compare_datasets(generated_data: Dict[str, Any], reference_data: Dict[str, Any], gen_path: Path, ref_path: Path):
    """Membandingkan hasil generate dengan format reference."""
    gen_chunks = generated_data.get("chunks", [])
    ref_chunks = reference_data.get("chunks", [])

    print("\n" + "=" * 70)
    print("📊 LAPORAN PERBANDINGAN & PENGECEKAN HASIL EKSTRAKSI JSON")
    print("=" * 70)
    print(f"File Hasil Praproces : {gen_path}")
    print(f"File Reference Refpdf: {ref_path}")
    print("-" * 70)

    # 1. Validasi Schema
    gen_valid, gen_errors = validate_schema(generated_data, "Generated JSON (praproces)")
    ref_valid, ref_errors = validate_schema(reference_data, "Reference JSON (refpdf)")

    print("\n1. VALIDASI SCHEMA / STRUKTUR:")
    if gen_valid:
        print("   ✅ Format Hasil Praproces : Sesuai standar {'chunks': [...]}")
    else:
        print("   ❌ Format Hasil Praproces : TIDAK SESUAI")
        for err in gen_errors[:5]:
            print(f"      - {err}")

    if ref_valid:
        print("   ✅ Format Reference (refpdf) : Valid")
    else:
        print("   ⚠️ Format Reference (refpdf) : Ditemukan catatan validasi")

    # 2. Statistik Jumlah Chunks
    print("\n2. JUMLAH CHUNKS:")
    print(f"   • Total Chunks (Hasil Praproces) : {len(gen_chunks)}")
    print(f"   • Total Chunks (Reference refpdf): {len(ref_chunks)}")
    diff_chunks = len(gen_chunks) - len(ref_chunks)
    diff_sign = f"+{diff_chunks}" if diff_chunks > 0 else f"{diff_chunks}"
    print(f"   • Selisih Chunks                : {diff_sign}")

    # 3. Distribusi Chunk Types
    gen_dist = get_type_distribution(gen_chunks)
    ref_dist = get_type_distribution(ref_chunks)
    all_types = sorted(list(set(gen_dist.keys()) | set(ref_dist.keys())))

    print("\n3. DISTRIBUSI TIPE CHUNK (chunk_type):")
    print(f"   {'Tipe':<15} | {'Praproces':<12} | {'Refpdf':<12}")
    print(f"   {'-'*15}-+-{'-'*12}-+-{'-'*12}")
    for t in all_types:
        print(f"   {t:<15} | {gen_dist.get(t, 0):<12} | {ref_dist.get(t, 0):<12}")

    # 4. Cakupan Halaman (Pages)
    gen_pages = set()
    for c in gen_chunks:
        for g in c.get("grounding", []):
            gen_pages.add(g.get("page", 0))

    ref_pages = set()
    for c in ref_chunks:
        for g in c.get("grounding", []):
            ref_pages.add(g.get("page", 0))

    print("\n4. CAKUPAN HALAMAN (Page Coverage):")
    if gen_pages:
        print(f"   • Halaman Terdeteksi (Praproces) : {len(gen_pages)} halaman (Page {min(gen_pages)} s/d {max(gen_pages)})")
    else:
        print(f"   • Halaman Terdeteksi (Praproces) : 0 halaman")

    if ref_pages:
        print(f"   • Halaman Reference (Refpdf)     : {len(ref_pages)} halaman (Page {min(ref_pages)} s/d {max(ref_pages)})")
    else:
        print(f"   • Halaman Reference (Refpdf)     : 0 halaman")

    # 5. Kemiripan Konten Teks (Text Similarity)
    doc_sim, all_sim = calculate_text_similarity(gen_chunks, ref_chunks)
    doc_sim_percent = doc_sim * 100.0
    all_sim_percent = all_sim * 100.0

    print("\n5. KEMIRIPAN KONTEN TEKS:")
    print(f"   • Kemiripan Teks Dokumen (Text & Marginalia) : {doc_sim_percent:.2f}%")
    if gen_dist.get("figure", 0) > 0 or ref_dist.get("figure", 0) > 0:
        print(f"   • Kemiripan Total (+ VLM Synthetic Captions) : {all_sim_percent:.2f}%")

    sim_eval = doc_sim_percent
    if sim_eval >= 90.0:
        badge = "SANGAT BAIK / IDENTIK"
    elif sim_eval >= 70.0:
        badge = "BAIK / KEMIRIPAN TINGGI"
    elif sim_eval >= 40.0:
        badge = "CUKUP / PERLU PENYESUAIAN"
    else:
        badge = "RENDAH / STRUKTUR BERBEDA"
    print(f"   • Status Evaluasi Teks                       : {badge}")

    # 6. Sampel Perbandingan Chunk Pertama
    print("\n6. SAMPEL CHUNK PERTAMA:")
    print("   --- [Hasil Praproces Chunk #0] ---")
    if gen_chunks:
        sample_gen = {
            "chunk_type": gen_chunks[0].get("chunk_type"),
            "text": (gen_chunks[0].get("text", "")[:120] + "...") if len(gen_chunks[0].get("text", "")) > 120 else gen_chunks[0].get("text", ""),
            "grounding": gen_chunks[0].get("grounding", [])[:1]
        }
        print("   " + json.dumps(sample_gen, indent=5, ensure_ascii=False).replace("\n", "\n   "))
    else:
        print("   (Kosong)")

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
    """Mendeteksi pasangan file uji di praproces/ dan file reference di refpdf/."""
    # Skenario 1: Argumen diberikan lengkap (uji & ref)
    if len(sys.argv) > 2:
        return Path(sys.argv[1]), Path(sys.argv[2])
    
    # Skenario 2: Diberikan satu nama file (misal: python check.py UU_Nomor_4_Tahun_2009_ID-1.json)
    if len(sys.argv) == 2:
        fname = Path(sys.argv[1]).name
        gen_file = PROCESSED_DIR / fname
        ref_file = REFPDF_DIR / fname
        if not ref_file.exists():
            ref_file = BASE_DIR / fname
        return gen_file, ref_file

    # Skenario 3: Tanpa argumen -> cari file pertama yang ada di praproces/ dan cocokkan ke refpdf/
    pra_files = list(PROCESSED_DIR.glob("*.json"))
    if pra_files:
        gen_file = pra_files[0]
        ref_file = REFPDF_DIR / gen_file.name
        if not ref_file.exists():
            # Fallback ke root atau data external jika ada
            ref_file = BASE_DIR / gen_file.name
            if not ref_file.exists():
                ref_file = BASE_DIR.parent / "pdf-parser-to-json" / "data" / gen_file.name
        return gen_file, ref_file

    # Skenario Default
    gen_file = PROCESSED_DIR / DEFAULT_FILENAME
    ref_file = REFPDF_DIR / DEFAULT_FILENAME
    return gen_file, ref_file


def main():
    gen_path, ref_path = resolve_file_paths()

    if not gen_path.exists():
        print(f"[ERROR] File hasil uji praproces tidak ditemukan di: {gen_path}")
        print(f"Jalankan skrip 'pratest.py' terlebih dahulu.")
        return

    if not ref_path.exists():
        print(f"[ERROR] File reference refpdf tidak ditemukan di: {ref_path}")
        print(f"Pastikan file reference disimpan di folder: {REFPDF_DIR}")
        return

    try:
        with open(gen_path, "r", encoding="utf-8") as f:
            gen_data = json.load(f)

        with open(ref_path, "r", encoding="utf-8") as f:
            ref_data = json.load(f)

        compare_datasets(gen_data, ref_data, gen_path, ref_path)

    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat membaca atau membandingkan file: {e}")


if __name__ == "__main__":
    main()
