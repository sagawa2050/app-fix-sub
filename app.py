import gradio as gr
import re
import difflib
import os
import traceback

def align_and_fix_subtitles(script_file, srt_file):
    if not script_file or not srt_file: return None, "Vui lòng tải lên đầy đủ 2 file."
    try:
        script_path = script_file if isinstance(script_file, str) else script_file.name
        srt_path = srt_file if isinstance(srt_file, str) else srt_file.name

        # 1. Đọc và làm sạch Kịch Bản (TXT)
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            script_raw = f.read()
        
        # Xóa khoảng trắng thừa nhưng GIỮ NGUYÊN chữ và dấu
        script_clean = re.sub(r'\s+', '', script_raw)

        if len(script_clean) == 0:
            raise ValueError("Kịch bản TXT trống.")

        # Tập hợp Dấu câu
        PUNC_END = set("。、！？.,」』”’")
        PUNC_START = set("「『“‘")

        # Tách riêng chữ thuần (không lấy dấu) để so khớp chính xác
        pure_chars = []
        for i, char in enumerate(script_clean):
            if char not in PUNC_END and char not in PUNC_START:
                pure_chars.append((char, i))
                
        txt_pure = "".join([c[0] for c in pure_chars])

        # 2. Đọc SRT gốc của Premiere
        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            srt_raw = f.read()
        
        blocks = re.split(r'\n\s*\n', srt_raw.strip())
        parsed_blocks = []
        srt_pure = ""
        srt_pure_to_block = [] 
        
        for i, block in enumerate(blocks):
            lines = block.split('\n')
            if len(lines) < 2: continue
            stt = lines[0]
            time_frame = lines[1]
            text = "".join(lines[2:])
            
            clean_text = re.sub(r'\s+', '', text)
            clean_pure_text = "".join([c for c in clean_text if c not in PUNC_END and c not in PUNC_START])
            
            parsed_blocks.append({
                'stt': stt, 'time': time_frame, 'raw_text': text
            })
            
            srt_pure += clean_pure_text
            # Đánh dấu từng ký tự thuộc về Block thời gian nào
            srt_pure_to_block.extend([i] * len(clean_pure_text))

        # ====================================================
        # LÕI THUẬT TOÁN V25/V26: SO KHỚP CHÍNH TẢ TUYỆT ĐỐI
        # ====================================================
        
        sm = difflib.SequenceMatcher(None, srt_pure, txt_pure, autojunk=False)
        txt_pure_to_block = [-1] * len(txt_pure)
        
        # Ánh xạ chữ đúng vào vị trí của chữ sai
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                for k in range(j2 - j1):
                    txt_pure_to_block[j1 + k] = srt_pure_to_block[i1 + k]
            elif tag == 'replace':
                for k in range(j2 - j1):
                    srt_idx = i1 + int(k * (i2 - i1) / (j2 - j1))
                    srt_idx = min(srt_idx, i2 - 1)
                    txt_pure_to_block[j1 + k] = srt_pure_to_block[srt_idx]
            elif tag == 'insert':
                block_idx = srt_pure_to_block[i1 - 1] if i1 > 0 else srt_pure_to_block[0]
                for k in range(j2 - j1):
                    txt_pure_to_block[j1 + k] = block_idx

        # Chống chảy ngược kịch bản
        for j in range(1, len(txt_pure_to_block)):
            if txt_pure_to_block[j] < txt_pure_to_block[j-1]:
                txt_pure_to_block[j] = txt_pure_to_block[j-1]

        # Ánh xạ ngược lại vào Script chứa dấu câu
        script_to_block = [-1] * len(script_clean)
        pure_idx = 0
        
        for i, char in enumerate(script_clean):
            if char not in PUNC_END and char not in PUNC_START:
                if pure_idx < len(txt_pure_to_block):
                    script_to_block[i] = txt_pure_to_block[pure_idx]
                pure_idx += 1

        # Đẩy dấu câu vào cùng Block với chữ
        for i, char in enumerate(script_clean):
            if char in PUNC_END:
                b_idx = 0
                for prev in range(i - 1, -1, -1):
                    if script_to_block[prev] != -1:
                        b_idx = script_to_block[prev]
                        break
                script_to_block[i] = b_idx
            elif char in PUNC_START:
                b_idx = len(parsed_blocks) - 1
                for nxt in range(i + 1, len(script_clean)):
                    if script_to_block[nxt] != -1:
                        b_idx = script_to_block[nxt]
                        break
                script_to_block[i] = b_idx

        final_texts = ["" for _ in range(len(parsed_blocks))]
        for i, block_idx in enumerate(script_to_block):
            if block_idx != -1:
                final_texts[block_idx] += script_clean[i]

        # ====================================================
        # BỘ LỌC DẤU CÂU THÔNG MINH (CHỐNG RỚT DÒNG)
        # ====================================================
        
        # Nếu dòng bắt đầu bằng dấu 。、 thì đẩy nó ngược lên dòng trên
        for i in range(1, len(final_texts)):
            while final_texts[i] and final_texts[i][0] in PUNC_END:
                char_to_move = final_texts[i][0]
                final_texts[i] = final_texts[i][1:]
                
                prev = i - 1
                while prev >= 0 and not final_texts[prev].strip():
                    prev -= 1
                
                if prev >= 0:
                    final_texts[prev] += char_to_move
                else:
                    final_texts[i] = char_to_move + final_texts[i]
                    break

        # Nếu dòng kết thúc bằng dấu 「 thì đẩy nó xuống dòng dưới
        for i in range(len(final_texts) - 1):
            while final_texts[i] and final_texts[i][-1] in PUNC_START:
                char_to_move = final_texts[i][-1]
                final_texts[i] = final_texts[i][:-1]
                
                nxt = i + 1
                while nxt < len(final_texts) and not final_texts[nxt].strip():
                    nxt += 1
                
                if nxt < len(final_texts):
                    final_texts[nxt] = char_to_move + final_texts[nxt]
                else:
                    final_texts[i] += char_to_move
                    break

        # 3. LẮP RÁP & BẢO TOÀN 100% CẤU TRÚC PREMIERE
        final_srt = []
        for i, b in enumerate(parsed_blocks):
            out_text = final_texts[i].strip()
            
            # KHÔNG XÓA DÒNG CỦA PREMIERE: Nếu Premiere trống (do nhạc nền), điền khoảng trắng tàng hình
            if not out_text:
                out_text = "　"
                
            final_srt.append(f"{i + 1}\n{b['time']}\n{out_text}")

        # Chuẩn bị nội dung Text để Xem Trước
        srt_result_content = "\n\n".join(final_srt)

        # 4. Xuất File
        original_filename = os.path.basename(srt_path)
        name_only, ext = os.path.splitext(original_filename)
        output_path = f"{name_only}_FIXED{ext}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_result_content)
            
        # Trả về cả đường dẫn File (để Tải) và Chuỗi ký tự (để Xem trước)
        return output_path, srt_result_content
        
    except Exception as e:
        raise gr.Error(f"LỖI HỆ THỐNG: {str(e)}\n\nChi tiết:\n{traceback.format_exc()}")

# --- GIAO DIỆN WEB ---
with gr.Blocks() as web_app:
    gr.Markdown("<h1 style='text-align: center;'>🎯 App Fix Subtitle - So Khớp Tuyệt Đối (V26)</h1>")
    
    with gr.Row():
        # Cột bên trái: Khu vực Nhập liệu
        with gr.Column(scale=1):
            script_input = gr.File(label="1. Kéo thả KỊCH BẢN CHUẨN (.txt)")
            srt_input = gr.File(label="2. Kéo thả SUB LỖI do Premiere làm (.srt)")
            submit_btn = gr.Button("🚀 Chạy Thuật Toán", variant="primary", size="lg")
            
        # Cột bên phải: Khu vực Kết quả (Tải về + Xem trước)
        with gr.Column(scale=1):
            output_file = gr.File(label="📥 TẢI VỀ: File Sub Hoàn Chỉnh")
            preview_text = gr.Textbox(
                label="👀 XEM TRƯỚC: Nội dung SRT", 
                lines=18, 
                interactive=False, 
                placeholder="Kết quả của file Sub sẽ hiển thị ở đây để bạn kiểm tra..."
            )

    # Kết nối Nút bấm với 2 Đầu ra
    submit_btn.click(
        fn=align_and_fix_subtitles, 
        inputs=[script_input, srt_input], 
        outputs=[output_file, preview_text]
    )

if __name__ == "__main__":
    gr.close_all()
    web_app.launch(theme=gr.themes.Base())
