#!/usr/bin/env bash
# Quay video demo trên bản deploy rồi ghép thành một tệp .mp4 duy nhất.
#
#   ADMIN_PASSWORD=... ./scripts/demo-video.sh
#   DEMO_BASE=http://localhost:3000 DEMO_SITE=http://localhost:8090 ./scripts/demo-video.sh   # quay bản local
#
# Mỗi cảnh trong apps/web/e2e/demo-video.spec.ts sinh ra một .webm; script này sắp theo số thứ tự
# trong tên cảnh (01…08), chèn tiêu đề mở đầu, rồi nối lại. Cảnh nào hỏng thì bỏ qua cảnh đó chứ
# không hỏng cả video, vì câu trả lời của mô hình có thể chậm hoặc khác nhau giữa các lần chạy.
set -Eeuo pipefail

cd "$(dirname "$0")/.."
WEB="apps/web"
OUT="${OUT:-docs/demo/msb-knowledge-assistant-demo.mp4}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

command -v ffmpeg >/dev/null || { echo "Cần ffmpeg (brew install ffmpeg)"; exit 1; }

export DEMO_BASE="${DEMO_BASE:-https://59-153-246-116.sslip.io}"
export DEMO_SITE="${DEMO_SITE:-https://demo.59-153-246-116.sslip.io}"
export E2E_ADMIN_PASSWORD="${ADMIN_PASSWORD:-${E2E_ADMIN_PASSWORD:-admin123}}"

# SKIP_RECORD=1 để ghép lại từ các cảnh đã quay lần trước (sửa tiêu đề, đổi thứ tự…)
if [[ -z "${SKIP_RECORD:-}" ]]; then
  echo "==> Quay các cảnh trên $DEMO_BASE (mất khoảng 8–12 phút)"
  rm -rf "$WEB/test-results"
  ( cd "$WEB" && npx playwright test e2e/demo-video.spec.ts --project=video ) || echo "!! một số cảnh lỗi, vẫn ghép các cảnh đã quay"
else
  echo "==> Bỏ qua bước quay, ghép lại từ $WEB/test-results"
fi

# bash 3.2 trên macOS không có mapfile
VIDEOS=()
while IFS= read -r line; do VIDEOS+=("$line"); done < <(find "$WEB/test-results" -name '*.webm' | sort)
[[ ${#VIDEOS[@]} -gt 0 ]] || { echo "Không có cảnh nào được quay"; exit 1; }
echo "==> Ghép ${#VIDEOS[@]} cảnh"

# Tiêu đề mở đầu: vẽ bằng Pillow rồi đưa vào ffmpeg dưới dạng ảnh tĩnh.
# (bản ffmpeg của Homebrew không kèm filter drawtext, nên không vẽ chữ trực tiếp trong ffmpeg được)
TITLE_PNG="$WORK/title.png"
apps/api/.venv/bin/python - "$TITLE_PNG" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont

def font(size, bold=False):
    for path in ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()

img = Image.new("RGB", (1600, 900), "#14233a")
d = ImageDraw.Draw(img)
d.rectangle([0, 0, 1600, 6], fill="#ee6d1f")
rows = [("MSB Knowledge Assistant", font(72), "#ffffff", 360),
        ("Demo trên bản triển khai thật", font(34), "#b4bfd2", 470),
        ("Dữ liệu mô phỏng · MSB AI Hackathon", font(26), "#ee6d1f", 540)]
for text, f, colour, y in rows:
    w = d.textbbox((0, 0), text, font=f)[2]
    d.text(((1600 - w) / 2, y), text, font=f, fill=colour)
img.save(sys.argv[1])
PY
TITLE="$WORK/00-title.mp4"
ffmpeg -hide_banner -loglevel error -loop 1 -t 3.5 -i "$TITLE_PNG" \
  -c:v libx264 -pix_fmt yuv420p -r 25 "$TITLE"

LIST="$WORK/list.txt"
echo "file '$TITLE'" > "$LIST"
i=0
for v in "${VIDEOS[@]}"; do
  i=$((i + 1))
  seg="$WORK/$(printf '%02d' "$i").mp4"
  # chuẩn hoá kích thước và khung hình để nối được bằng concat demuxer
  ffmpeg -hide_banner -loglevel error -i "$v" \
    -vf "scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=0x14233a,fps=25" \
    -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p "$seg"
  echo "file '$seg'" >> "$LIST"
done

mkdir -p "$(dirname "$OUT")"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$LIST" -c copy "$OUT"
echo "==> Xong: $OUT  ($(du -h "$OUT" | cut -f1), $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" | cut -d. -f1)s)"
