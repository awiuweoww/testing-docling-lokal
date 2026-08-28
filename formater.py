import os
import re
import sys
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
INPUT_OUTPUT_DIR = BASE_DIR / "output"       # Folder tempat hasil JSON mentah dari testing1.py
PROCESSED_DIR = BASE_DIR / "formater"      # Folder tujuan untuk JSON berformat standar

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
INPUT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_JSON_NAME = "UU_Nomor_4_Tahun_2009_ID-1.json"

# Threshold jarak vertikal (normalized 0-1) antara proto-chunk untuk merge level-2.
# Proto-chunk berurutan pada halaman yang sama di-merge jika gap < threshold.
MERGE_GAP_THRESHOLD = 0.015  # ~1.5% tinggi halaman

# Jika gap antara elemen > threshold ini, teks digabung dengan \n\n.
# Jika gap <= threshold ini, teks digabung dengan \n.
PARAGRAPH_GAP_THRESHOLD = 0.025  # ~2.5% tinggi halaman


def normalize_bbox(
    bbox: Dict[str, Any],
    page_width: float,
    page_height: float,
    coord_origin: str = "BOTTOMLEFT"
) -> Dict[str, float]:
    """
    Normalisasi koordinat bounding box ke skala 0.0 - 1.0 (origin: TOP-LEFT).
    """
    l = float(bbox.get("l", 0.0))
    t = float(bbox.get("t", 0.0))
    r = float(bbox.get("r", 0.0))
    b = float(bbox.get("b", 0.0))

    if page_width <= 0 or page_height <= 0:
        return {"l": l, "t": t, "r": r, "b": b}

    origin = coord_origin.upper() if coord_origin else "BOTTOMLEFT"

    if origin == "BOTTOMLEFT":
        # Pada sistem koordinat PDF standar (BOTTOMLEFT), nilai Y diukur dari bawah ke atas.
        # Konversi ke koordinat tampilan (TOP-LEFT):
        l_norm = max(0.0, min(1.0, l / page_width))
        r_norm = max(0.0, min(1.0, r / page_width))
        t_norm = max(0.0, min(1.0, (page_height - t) / page_height))
        b_norm = max(0.0, min(1.0, (page_height - b) / page_height))
        
        # Pastikan t_norm <= b_norm
        if t_norm > b_norm:
            t_norm, b_norm = b_norm, t_norm
            
        return {
            "l": l_norm,
            "t": t_norm,
            "r": r_norm,
            "b": b_norm
        }
    else:
        # TOPLEFT coordinate origin
        return {
            "l": max(0.0, min(1.0, l / page_width)),
            "t": max(0.0, min(1.0, t / page_height)),
            "r": max(0.0, min(1.0, r / page_width)),
            "b": max(0.0, min(1.0, b / page_height))
        }


def union_bbox(boxes: List[Dict[str, float]]) -> Dict[str, float]:
    """Menghitung union (kotak terbesar) dari beberapa bounding box."""
    if not boxes:
        return {"l": 0.0, "t": 0.0, "r": 1.0, "b": 1.0}
    return {
        "l": min(b["l"] for b in boxes),
        "t": min(b["t"] for b in boxes),
        "r": max(b["r"] for b in boxes),
        "b": max(b["b"] for b in boxes),
    }


def _is_page_number(text: str) -> bool:
    """
    Deteksi apakah teks adalah nomor halaman sederhana (page number).
    Contoh yang termasuk: '- 2 -', '$-3-$', '- 87 -', '12'
    Contoh yang BUKAN: 'Pasal 19 . . .', 'BAB IX . . .', '24. Jasa . . .'
    """
    import re
    t = text.strip()
    # Pattern: optional dash/dollar, optional space, number, optional space, optional dash/dollar
    # Matches: "- 2 -", "$-3-$", "- 87 -", "–  26  –", etc.
    if re.match(r'^[\$\-–\s]*\d+[\$\-–\s]*$', t):
        return True
    return False


def map_label_to_chunk_type(label: str, content_layer: str = "", text: str = "") -> str:
    """
    Memetakan label dokumen ke tipe chunk standar: 'text', 'marginalia', 'figure'.
    
    Logika utama:
    - Elemen furniture yang berupa nomor halaman → 'marginalia'
    - Elemen furniture yang berupa konten (Pasal, BAB, dll) → 'text'
    - Elemen gambar → 'figure'
    - Semua elemen body (termasuk section_header) → 'text'
    """
    lbl = (label or "").lower().strip()
    layer = (content_layer or "").lower().strip()
    
    if layer == "furniture":
        # Hanya nomor halaman sederhana yang jadi marginalia
        # Page_footer yang berisi konten (seperti "Pasal 19 . . .") → text
        if lbl == "page_header" and _is_page_number(text):
            return "marginalia"
        elif lbl == "page_footer":
            # page_footer: cek apakah isinya nomor halaman atau konten
            if _is_page_number(text):
                return "marginalia"
            else:
                return "text"  # Konten continuation di footer → text
        else:
            # page_header non-number → marginalia (header biasanya judul dokumen)
            return "marginalia"
    
    if any(k in lbl for k in ["figure", "picture", "image", "logo"]):
        return "figure"
    
    return "text"


# ============================================================================
# Docling Tree-Based Merge Engine
# ============================================================================

def _get_text_info(
    t_item: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> Dict[str, Any]:
    """Extract normalized text info from a Docling text item."""
    prov = t_item.get("prov", [{}])[0] if t_item.get("prov") else {}
    page_no = int(prov.get("page_no", 1))
    bbox_raw = prov.get("bbox", {})
    coord_origin = bbox_raw.get("coord_origin", "BOTTOMLEFT")

    p_dim = page_dimensions.get(page_no, {"width": 595.27, "height": 841.89})
    box_norm = normalize_bbox(bbox_raw, p_dim["width"], p_dim["height"], coord_origin)

    # Normalize multi-spaces → single space (Docling seringkali menghasilkan
    # spasi ganda/triple yang Landing.AI tidak memiliki)
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
    """
    Mengonversi struktur data tabel Docling ke format Markdown Table standar.
    Mencegah hilangnya data sel, baris, maupun relasi kolom pada dokumen.
    """
    data = table_dict.get("data", {})
    num_rows = data.get("num_rows", 0)
    num_cols = data.get("num_cols", 0)
    cells = data.get("table_cells", [])
    
    if not cells or num_rows == 0 or num_cols == 0:
        return ""
    
    # Inisialisasi matriks 2D
    grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    for cell in cells:
        r = cell.get("start_row_offset_idx", 0)
        c = cell.get("start_col_offset_idx", 0)
        text = cell.get("text", "").strip().replace("\n", " ")
        if 0 <= r < num_rows and 0 <= c < num_cols:
            grid[r][c] = text
            
    # Susun Markdown Table
    lines = []
    # Header baris pertama
    lines.append("| " + " | ".join(grid[0]) + " |")
    # Separator
    lines.append("| " + " | ".join(["---"] * num_cols) + " |")
    # Baris data berikutnya
    for r in range(1, num_rows):
        lines.append("| " + " | ".join(grid[r]) + " |")
        
    return "\n".join(lines)


def _get_table_info(
    table_item: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> Dict[str, Any]:
    """Extract normalized table info and convert to Markdown chunk."""
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
    """Recursively get all leaf items (text, table, group) from a reference."""
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
    """Get overall bounding box of a proto-chunk."""
    return union_bbox([leaf["box"] for leaf in proto])


def _proto_page(proto: List[Dict[str, Any]]) -> int:
    """Get the page index of a proto-chunk (uses first leaf)."""
    return proto[0]["page_idx"] if proto else -1


def _is_furniture(proto: List[Dict[str, Any]]) -> bool:
    """Check if a proto-chunk is a true marginalia furniture element (e.g., page number)."""
    for leaf in proto:
        if leaf.get("content_layer") == "furniture":
            c_type = map_label_to_chunk_type(leaf.get("label", ""), leaf.get("content_layer", ""), leaf.get("text", ""))
            if c_type == "marginalia":
                return True
    return False


def _leaves_to_text(leaves: List[Dict[str, Any]]) -> str:
    """
    Gabungkan teks dari beberapa leaf items.
    Gunakan \n\n untuk gap besar (paragraph break), \n untuk gap kecil.
    """
    if not leaves:
        return ""
    
    parts = [leaves[0]["text"]]
    for i in range(1, len(leaves)):
        prev = leaves[i - 1]
        curr = leaves[i]
        
        # Hitung gap vertikal
        if curr["page_idx"] == prev["page_idx"]:
            gap = curr["box"]["t"] - prev["box"]["b"]
        else:
            gap = 1.0  # beda halaman = besar
        
        if gap > PARAGRAPH_GAP_THRESHOLD:
            parts.append("")  # empty line -> \n\n
            parts.append(curr["text"])
        else:
            parts.append(curr["text"])
    
    return "\n".join(parts)


def _build_proto_chunks(
    doc: Dict[str, Any],
    page_dimensions: Dict[int, Dict[str, float]]
) -> List[List[Dict[str, Any]]]:
    """
    Build proto-chunks from Docling document tree.
    
    Level 1: Each body child becomes a proto-chunk.
    - Direct text ref → proto-chunk with 1 leaf
    - Group ref → proto-chunk with all group's leaf texts merged
    - Table ref → proto-chunk formatted as Markdown table
    
    Pictures and standalone tables are also included.
    """
    texts_list = doc.get("texts", [])
    groups_list = doc.get("groups", [])
    tables_list = doc.get("tables", [])
    body = doc.get("body", {})
    
    # Build lookup maps
    ref_to_text = {t.get("self_ref", ""): t for t in texts_list if t.get("self_ref")}
    ref_to_group = {g.get("self_ref", ""): g for g in groups_list if g.get("self_ref")}
    ref_to_table = {tb.get("self_ref", ""): tb for tb in tables_list if tb.get("self_ref")}
    
    proto_chunks = []
    handled_table_refs = set()
    
    # Process body children
    body_children = body.get("children", [])
    for child in body_children:
        child_ref = child.get("$ref", "")
        if child_ref in ref_to_table:
            handled_table_refs.add(child_ref)
        leaves = _get_leaves(child_ref, ref_to_text, ref_to_group, ref_to_table, page_dimensions)
        if leaves:
            proto_chunks.append(leaves)
    
    # Process any unhandled standalone tables
    for tb in tables_list:
        sr = tb.get("self_ref", "")
        if sr not in handled_table_refs:
            info = _get_table_info(tb, page_dimensions)
            if info["text"]:
                proto_chunks.append([info])
    
    # Process pictures (if any, add as separate proto-chunks)
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
    """
    Level 2: Merge consecutive proto-chunks pada halaman yang sama
    jika gap vertikal antara mereka < MERGE_GAP_THRESHOLD.
    
    Furniture (marginalia) dan figure TIDAK di-merge.
    """
    if not proto_chunks:
        return []
    
    final_chunks = []
    i = 0
    
    while i < len(proto_chunks):
        current_leaves = list(proto_chunks[i])
        
        # Furniture dan figure tidak di-merge
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
        
        # Check if figure
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
        
        # Body element: try merging with next proto-chunks
        j = i + 1
        while j < len(proto_chunks):
            next_proto = proto_chunks[j]
            
            # Don't merge with furniture or figure
            if _is_furniture(next_proto):
                break
            if any(l["label"] in ("picture", "figure") for l in next_proto):
                break
            
            # Must be same page
            curr_page = _proto_page(current_leaves)
            next_page = _proto_page(next_proto)
            if curr_page != next_page:
                break
            
            # Check vertical gap
            curr_box = _get_proto_bbox(current_leaves)
            next_box = _get_proto_bbox(next_proto)
            gap = next_box["t"] - curr_box["b"]
            
            if gap < MERGE_GAP_THRESHOLD:
                current_leaves.extend(next_proto)
                j += 1
            else:
                break
        
        # Create chunk from merged leaves
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
    """
    Mengonversi struktur output Docling (export_to_dict) ke format standar chunks.
    
    Menggunakan dua level merge:
    1. Tree-based: Elemen dalam group yang sama → 1 proto-chunk
    2. Spatial: Proto-chunk berurutan pada halaman sama + gap kecil → merge
    """
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

    # Level 1: Build proto-chunks from document tree
    proto_chunks = _build_proto_chunks(doc, page_dimensions)
    
    # Sort proto-chunks secara fisik (page, top, left) agar urutan bacaan konsisten
    # dan elemen seperti gambar / header berada di posisi yang tepat di setiap halaman
    proto_chunks.sort(key=lambda pc: (
        _proto_page(pc),
        _get_proto_bbox(pc)["t"],
        _get_proto_bbox(pc)["l"]
    ))
    
    # Level 2: Merge proto-chunks yang berdekatan secara spasial
    chunks = _merge_proto_chunks(proto_chunks)

    return {"chunks": chunks}


def _convert_flat_docling(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback: Konversi Docling tanpa tree (jika body/groups tidak tersedia).
    Menggunakan pendekatan flat + spatial merge.
    """
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
    
    # Build flat elements
    elements = []
    for item in doc.get("texts", []):
        text_content = item.get("text", "").strip()
        if not text_content:
            continue
        info = _get_text_info(item, page_dimensions)
        elements.append(info)
    
    # Sort by page then vertical position
    elements.sort(key=lambda e: (e["page_idx"], e["box"]["t"]))
    
    # Each element becomes its own proto-chunk
    proto_chunks = [[e] for e in elements]
    
    return {"chunks": _merge_proto_chunks(proto_chunks)}


def convert_generic_to_standard(raw_data: Any) -> Dict[str, Any]:
    """
    Mengonversi berbagai kemungkinan struktur JSON (Docling, MinerU, atau format dict) ke format standar.
    """
    if isinstance(raw_data, dict):
        # Sudah memiliki format {"chunks": [...]}
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

        # Format output DoclingDocument
        if "texts" in raw_data or "pages" in raw_data or raw_data.get("schema_name") == "DoclingDocument":
            # Cek apakah ada body tree structure
            body = raw_data.get("body", {})
            has_tree = bool(body.get("children"))
            if has_tree:
                return convert_docling_to_standard(raw_data)
            else:
                return _convert_flat_docling(raw_data)

        # MinerU / Magic-PDF format
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

    # Fallback generic
    return {"chunks": []}


def process_json_file(input_file: Path, output_file: Path):
    """Membaca file JSON mentah, melakukan transformasi format, dan menyimpan ke file tujuan."""
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
    # Cek apakah nama file diberikan via CLI argumen
    if len(sys.argv) > 1:
        target_name = Path(sys.argv[1]).name
    else:
        # Gunakan default atau cari file JSON pertama di folder output
        available_jsons = list(INPUT_OUTPUT_DIR.glob("*.json"))
        if available_jsons:
            target_name = available_jsons[0].name
        else:
            target_name = DEFAULT_JSON_NAME

    input_path = INPUT_OUTPUT_DIR / target_name
    output_path = PROCESSED_DIR / target_name

    # Jika file di folder output belum ada, cek apakah ada di root pdf-parser
    if not input_path.exists() and (BASE_DIR / target_name).exists():
        input_path = BASE_DIR / target_name

    process_json_file(input_path, output_path)


if __name__ == "__main__":
    main()
