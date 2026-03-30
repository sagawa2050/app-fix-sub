import gradio as gr
import re
import difflib
import os
import traceback

def align_and_fix_subtitles(script_text, srt_file):
    # Kiểm tra dữ liệu đầu vào
    if not script_text or not script_text.strip(): 
        return None, "Vui lòng dán nội dung kịch bản vào ô số 1."
    if not srt_file: 
        return None, "Vui lòng tải lên file SRT lỗi vào ô số 2."
        
    try:
        srt_path = srt_file if isinstance(srt_file, str) else srt_file.name

        # 1. Đọc và làm sạch Kịch Bản (TXT) từ Textbox
        script_raw = script_text
        
        script_clean = re.sub(r'\s+', '', script_raw)
        if len(script_clean) == 0:
            raise ValueError("Kịch bản trống.")

        PUNC_END = set("。、！？.,」』”’")
        PUNC_START = set("「『“‘")

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
            srt_pure_to_block.extend([i] * len(clean_pure_text))

        # ====================================================
        # LÕI THUẬT TOÁN V27: SO KHỚP CHIA CHẶN (ANCHOR-GUIDED)
        # ====================================================
        anchor_len = 12 # Độ dài cụm từ độc nhất để làm mốc neo
        srt_ngrams = {}
        for i in range(len(srt_pure) - anchor_len + 1):
            gram = srt_pure[i:i+anchor_len]
            srt_ngrams[gram] = -1 if gram in srt_ngrams else i
            
        txt_ngrams = {}
        for i in range(len(txt_pure) - anchor_len + 1):
            gram = txt_pure[i:i+anchor_len]
            txt_ngrams[gram] = -1 if gram in txt_ngrams else i

        common_anchors = []
        for gram, srt_idx in srt_ngrams.items():
            if srt_idx != -1:
                txt_idx = txt_ngrams.get(gram, -1)
                if txt_idx != -1:
                    # Lọc nhiễu: Mốc neo không được trôi quá 25% dòng thời gian
                    drift = abs(srt_idx / max(1, len(srt_pure)) - txt_idx / max(1, len(txt_pure)))
                    if drift < 0.25:
                        common_anchors.append((srt_idx, txt_idx, anchor_len))
                        
        common_anchors.sort() # Sắp xếp mốc neo theo thời gian thực
        
        # Lọc mốc neo hợp lệ (chống vắt chéo)
        valid_anchors = []
        last_txt = -1
        last_srt = -1
        for anchor in common_anchors:
            srt_idx, txt_idx, a_len = anchor
            if txt_idx > last_txt and srt_idx >= last_srt:
                valid_anchors.append(anchor)
                last_txt = txt_idx + a_len
                last_srt = srt_idx + a_len

        txt_pure_to_block = [-1] * len(txt_pure)
        anchors = [(0, 0, 0)] + valid_anchors + [(len(srt_pure), len(txt_pure), 0)]
        
        # Xử lý nội dung ở khoảng giữa các mốc neo
        for k in range(len(anchors) - 1):
            srt_start = anchors[k][0] + anchors[k][2]
            srt_end = anchors[k+1][0]
            txt_start = anchors[k][1] + anchors[k][2]
            txt_end = anchors[k+1][1]
            
            srt_seg = srt_pure[srt_start:srt_end]
            txt_seg = txt_pure[txt_start:txt_end]
            
            if srt_seg or txt_seg:
                sm = difflib.SequenceMatcher(None, srt_seg, txt_seg, autojunk=False)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag == 'equal':
                        for m in range(j2 - j1):
                            txt_pure_to_block[txt_start + j1 + m] = srt_pure_to_block[srt_start + i1 + m]
                    elif tag == 'replace':
                        for m in range(j2 - j1):
                            srt_m = srt_start + i1 + int(m * (i2 - i1) / max(1, j2 - j1))
                            srt_m = min(srt_m, srt_start + i2 - 1)
                            if srt_m < len(srt_pure_to_block):
                                txt_pure_to_block[txt_start + j1 + m] = srt_pure_to_block[srt_m]
                    elif tag == 'insert':
                        block_idx = srt_pure_to_block[srt_start + i1 - 1] if (srt_start + i1) > 0 else (srt_pure_to_block[0] if srt_pure_to_block else 0)
                        for m in range(j2 - j1):
                            txt_pure_to_block[txt_start + j1 + m] = block_idx
            
            # Gắn cứng dữ liệu tại chính mốc neo
            if k < len(anchors) - 2:
                a_srt = anchors[k+1][0]
                a_txt = anchors[k+1][1]
                a_len = anchors[k+1][2]
                for m in range(a_len):
                    txt_pure_to_block[a_txt + m] = srt_pure_to_block[a_srt + m]
        
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

        # 3. LẮP RÁP & BẢO TOÀN CẤU TRÚC PREMIERE
        final_srt = []
        for i, b in enumerate(parsed_blocks):
            out_text = final_texts[i].strip()
            if not out_text:
                out_text = "　"
            final_srt.append(f"{i + 1}\n{b['time']}\n{out_text}")

        srt_result_content = "\n\n".join(final_srt)

        # 4. Xuất File
        original_filename = os.path.basename(srt_path)
        name_only, ext = os.path.splitext(original_filename)
        output_path = f"{name_only}_FIXED{ext}"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_result_content)
            
        return output_path, srt_result_content
        
    except Exception as e:
        raise gr.Error(f"LỖI HỆ THỐNG: {str(e)}\n\nChi tiết:\n{traceback.format_exc()}")

# --- GIAO DIỆN WEB ---
with gr.Blocks() as web_app:
    gr.Markdown("<h1 style='text-align: center;'>🎯 App Fix Subtitle - So Khớp Tuyệt Đối (V27)</h1>")
    
    with gr.Row():
        with gr.Column(scale=1):
            # Thay đổi ở đây: Dùng Textbox thay vì File input
            script_input = gr.Textbox(
                label="1. DÁN KỊCH BẢN CHUẨN VÀO ĐÂY", 
                lines=20, 
                placeholder="Dán toàn bộ nội dung kịch bản của bạn vào đây..."
            )
            srt_input = gr.File(label="2. Kéo thả SUB LỖI do Premiere làm (.srt)")
            submit_btn = gr.Button("🚀 Chạy Thuật Toán V27", variant="primary", size="lg")
            
        with gr.Column(scale=1):
            output_file = gr.File(label="📥 TẢI VỀ: File Sub Hoàn Chỉnh")
            preview_text = gr.Textbox(
                label="👀 XEM TRƯỚC: Nội dung SRT", 
                lines=18, 
                interactive=False, 
                placeholder="Kết quả của file Sub sẽ hiển thị ở đây để bạn kiểm tra..."
            )

    submit_btn.click(
        fn=align_and_fix_subtitles, 
        inputs=[script_input, srt_input], 
        outputs=[output_file, preview_text]
    )

if __name__ == "__main__":
    gr.close_all()
    web_app.launch()
