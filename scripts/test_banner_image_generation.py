#!/usr/bin/env python3
"""
バナー画像生成のローカルテストスクリプト

レベル表示の位置とサイズを調整して、生成された画像を確認します。
"""
import sys
from pathlib import Path
from PIL import Image

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from hokuhoku_imomaru_bot.services.image_compositor import ImageCompositor


def test_local_image_generation():
    """ローカルで画像生成をテスト"""
    print("=" * 60)
    print("バナー画像生成テスト（ローカル）")
    print("=" * 60)
    
    # ベース画像のパス
    base_image_path = project_root / ".backup/s3/hoku2-imomaru-images/imomaru-banner-base.png"
    
    if not base_image_path.exists():
        print(f"❌ ベース画像が見つかりません: {base_image_path}")
        return 1
    
    print(f"\n[1] ベース画像を読み込み中...")
    print(f"   パス: {base_image_path}")
    
    # ベース画像を読み込んで情報を表示
    base_image = Image.open(base_image_path)
    print(f"   画像サイズ: {base_image.size[0]} x {base_image.size[1]} px")
    
    # 画像をバイトデータとして読み込み
    with open(base_image_path, "rb") as f:
        image_bytes = f.read()
    
    print(f"\n[2] レベル表示を合成中（フォントサイズ96px、位置微調整）...")
    
    # 位置微調整のテスト（テスト1をベースに微調整）
    test_configs = [
        {"padding_right": 80, "padding_bottom": 80, "label": "少し右・少し下（80px）"},
        {"padding_right": 70, "padding_bottom": 70, "label": "もう少し右・もう少し下（70px）"},
        {"padding_right": 60, "padding_bottom": 60, "label": "さらに右・さらに下（60px）"},
    ]
    
    output_dir = project_root / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    for i, config in enumerate(test_configs, 1):
        print(f"\n   テスト {i}: {config['label']}")
        
        # ImageCompositorを作成（S3なしでローカルテスト用）
        # padding_rightとpadding_bottomを個別に指定できるように一時的に修正
        compositor = ImageCompositor(
            s3_client=None,  # S3は使わない
            bucket_name="dummy",
            font_size=96,
            padding=20,  # デフォルト値（使わない）
        )
        
        # composite_level_image_from_bytesを使って位置をカスタマイズ
        from PIL import ImageDraw, ImageFont
        from io import BytesIO
        
        # 画像を読み込み
        image = Image.open(BytesIO(image_bytes))
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        
        draw = ImageDraw.Draw(image)
        
        # フォントを取得
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 96)
        except:
            font = ImageFont.load_default()
        
        # レベルテキスト
        level_text = "Lv.13"
        
        # テキストサイズを取得
        bbox = draw.textbbox((0, 0), level_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 右下から指定した距離に配置
        x = image.width - text_width - config["padding_right"]
        y = image.height - text_height - config["padding_bottom"]
        
        # 縁取り付きテキストを描画
        outline_width = 2
        outline_color = (0, 0, 0)
        text_color = (255, 255, 255)
        
        # 縁取りを描画（8方向）
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), level_text, font=font, fill=outline_color)
        
        # メインテキストを描画
        draw.text((x, y), level_text, font=font, fill=text_color)
        
        # BytesIOに保存
        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        
        # 画像を保存
        output_path = output_dir / f"banner_adjusted_{i}_r{config['padding_right']}_b{config['padding_bottom']}.png"
        with open(output_path, "wb") as f:
            f.write(output.read())
        
        print(f"   ✅ 保存完了: {output_path}")
        print(f"      位置: 右から{config['padding_right']}px、下から{config['padding_bottom']}px")
    
    print("\n" + "=" * 60)
    print("✅ テスト完了")
    print("=" * 60)
    print(f"\n生成された画像を確認してください:")
    print(f"  {output_dir}/")
    print(f"\n確認ポイント:")
    print(f"  1. 「Lv.13」の文字が右下のひし形部分に重なっているか")
    print(f"  2. 位置が適切か（ひし形の中心付近）")
    print(f"  3. 文字が読みやすいか")
    
    return 0


if __name__ == "__main__":
    sys.exit(test_local_image_generation())
