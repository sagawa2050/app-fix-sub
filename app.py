import gradio as gr
import re
import difflib
import os

# ==========================================
# KHU VỰC CẤP QUYỀN (Thay đổi tài khoản ở đây)
# ==========================================
DANH_SACH_VIP = [
    ("admin", "123456"),
    ("khach", "dungthu123")
]

def align_and_fix_subtitles(script_file, srt_file):
    if not script_file or not srt_file:
        return None
    try:
        # Đọc Kịch bản
        with open(script_file.name, 'r', encoding='utf-8', errors='ignore') as f:
            script_raw = f.read()
        script_clean = re.sub(r'\s+', '', script_raw)

        # Đọc Sub Lỗi
        with open(srt_file.name, 'r', encoding='utf-8', errors='ignore') as f:
            srt_raw = f.read()
        
        blocks = re.split(r'\n\s*\n', srt_raw.strip())
        parsed_blocks = []
        srt_clean = ""
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) < 3: continue
            stt = lines[0]
            time_frame = lines[1]
            text = "".join(lines[2:])
            
            text_clean = re.sub(r'\s+', '', text)
            if not text_clean: continue
            
            start_idx = len(srt_clean)
            srt_clean += text_clean
            end_idx = len(srt_clean) - 1 
            
            parsed_blocks.append({
                'stt': stt, 'time': time_frame, 'start': start_idx, 'end': end_idx, 'raw_text': text
            })

        # Thuật toán lập bản đồ ký tự
        sm = difflib.SequenceMatcher(None, srt_clean, script_clean)
        map_srt2script = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1): map_srt2script[i1 + k] = j1 + k
            elif tag == 'replace':
                for k in range(i2 - i1): map_srt2script[i1 + k] = j1 + int((k / (i2 - i1)) * (j2 - j1))
            elif tag == 'delete':
                for k in range(i2 - i1): map_srt2script[i1 + k] = j1

        final_srt = []
        last_script_end = -1
        
        for b in parsed_blocks:
            s_idx = map_srt2script.get(b['start'], last_script_end + 1)
            e_idx = map_srt2script.get(b['end'], s_idx)
            s_idx = max(s_idx, last_script_end + 1)
            e_idx = max(e_idx, s_idx)
            
            while e_idx + 1 < len(script_clean) and script_clean[e_idx + 1] in '。、！？.,」』”’':
                e_idx += 1
                
            if s_idx <= e_idx and s_idx < len(script_clean):
                correct_text = script_clean[s_idx : e_idx + 1]
            else:
                correct_text = b['raw_text']
                
            last_script_end = e_idx
            final_srt.append(f"{b['stt']}\n{b['time']}\n{correct_text}")

        # ----------------------------------------------------
        # TÍNH NĂNG MỚI: TỰ ĐỘNG ĐẶT TÊN THEO FILE GỐC
        # ----------------------------------------------------
        # Trích xuất tên gốc của file srt (VD: tap01.srt)
        original_filename = os.path.basename(srt_file.name)
        
        # MẸO NHỎ: Thêm chữ "_FIXED" vào đuôi để lúc tải về máy không bị đè mất file gốc
        # Nếu bạn không thích chữ _FIXED, chỉ cần đổi thành: output_path = original_filename
        name_only, ext = os.path.splitext(original_filename)
        output_path = f"{name_only}_FIXED{ext}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n\n".join(final_srt))
            
        return output_path
        
    except Exception as e:
        print(f"Lỗi: {e}")
        return None

# --- GIAO DIỆN WEB ---
with gr.Blocks(theme=gr.themes.Base()) as web_app:
    gr.Markdown("<h1 style='text-align: center;'>🎯 App Fix Subtitle - Hệ thống Bản quyền</h1>")
    with gr.Row():
        with gr.Column():
            script_input = gr.File(label="1. Kéo thả KỊCH BẢN CHUẨN (.txt)")
            srt_input = gr.File(label="2. Kéo thả SUB LỖI (.srt)")
            submit_btn = gr.Button("🚀 Chạy Thuật Toán", variant="primary")
        with gr.Column():
            output_file = gr.File(label="📥 File Sub Hoàn Chỉnh (Tải về tại đây)")

    submit_btn.click(fn=align_and_fix_subtitles, inputs=[script_input, srt_input], outputs=output_file)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    web_app.launch(server_name="0.0.0.0", server_port=port, auth=DANH_SACH_VIP, auth_message="ĐĂNG NHẬP ĐỂ SỬ DỤNG!")
