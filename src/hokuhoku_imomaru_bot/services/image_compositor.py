"""
ImageCompositorクラス

Pillowを使用してプロフィール画像にレベルテキストを合成します。
"""
import logging
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# デフォルト設定
DEFAULT_FONT_SIZE = 24
DEFAULT_TEXT_COLOR = (255, 255, 255)  # 白
DEFAULT_OUTLINE_COLOR = (0, 0, 0)  # 黒
DEFAULT_OUTLINE_WIDTH = 2
DEFAULT_PADDING = 10


class ImageCompositor:
    """
    Pillowを使用してプロフィール画像にレベルテキストを合成するクラス
    
    Attributes:
        s3_client: boto3 S3クライアント
        bucket_name: S3バケット名
        base_image_key: ベース画像のS3キー
    """
    
    def __init__(
        self,
        s3_client,
        bucket_name: str,
        base_image_key: str = "base_profile.png",
        font_size: int = DEFAULT_FONT_SIZE,
        text_color: Tuple[int, int, int] = DEFAULT_TEXT_COLOR,
        outline_color: Tuple[int, int, int] = DEFAULT_OUTLINE_COLOR,
        outline_width: int = DEFAULT_OUTLINE_WIDTH,
        padding: int = DEFAULT_PADDING,
    ):
        """
        ImageCompositorを初期化
        
        Args:
            s3_client: boto3 S3クライアント
            bucket_name: S3バケット名
            base_image_key: ベース画像のS3キー
            font_size: フォントサイズ
            text_color: テキスト色（RGB）
            outline_color: 縁取り色（RGB）
            outline_width: 縁取り幅
            padding: 画像端からのパディング
        """
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.base_image_key = base_image_key
        self.font_size = font_size
        self.text_color = text_color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.padding = padding
    
    def _get_base_image(self) -> Image.Image:
        """
        S3からベース画像を取得
        
        Returns:
            PIL Imageオブジェクト
        
        Raises:
            Exception: S3からの取得に失敗した場合
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=self.base_image_key,
            )
            image_data = response["Body"].read()
            image = Image.open(BytesIO(image_data))
            
            # RGBAモードに変換（透過対応）
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            
            logger.info(f"Base image loaded: {image.size}")
            return image
            
        except Exception as e:
            logger.error(f"Failed to get base image from S3: {e}")
            raise
    
    def _get_font(self) -> ImageFont.FreeTypeFont:
        """
        フォントを取得
        
        Returns:
            ImageFontオブジェクト
        """
        try:
            # システムフォントを試す
            font = ImageFont.truetype("Arial Bold", self.font_size)
            return font
        except OSError:
            try:
                # macOSのフォントパス
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", self.font_size)
                return font
            except OSError:
                try:
                    # Linuxのフォントパス
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", self.font_size)
                    return font
                except OSError:
                    # デフォルトフォントを使用
                    logger.warning("Using default font")
                    return ImageFont.load_default()
    
    def _draw_text_with_outline(
        self,
        draw: ImageDraw.ImageDraw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
    ) -> None:
        """
        縁取り付きテキストを描画
        
        Args:
            draw: ImageDrawオブジェクト
            position: テキスト位置（x, y）
            text: 描画するテキスト
            font: フォント
        """
        x, y = position
        
        # 縁取りを描画（8方向）
        for dx in range(-self.outline_width, self.outline_width + 1):
            for dy in range(-self.outline_width, self.outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text(
                        (x + dx, y + dy),
                        text,
                        font=font,
                        fill=self.outline_color,
                    )
        
        # メインテキストを描画
        draw.text(position, text, font=font, fill=self.text_color)
    
    def composite_level_image(self, level: int) -> BytesIO:
        """
        レベルテキストを合成した画像を生成
        
        Args:
            level: 現在のレベル
        
        Returns:
            合成された画像のバイトストリーム（PNG形式）
        """
        # ベース画像を取得
        image = self._get_base_image()
        draw = ImageDraw.Draw(image)
        font = self._get_font()
        
        # レベルテキスト
        level_text = f"Lv.{level}"
        
        # テキストサイズを取得
        bbox = draw.textbbox((0, 0), level_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 右下に配置
        x = image.width - text_width - self.padding
        y = image.height - text_height - self.padding
        
        # 縁取り付きテキストを描画
        self._draw_text_with_outline(draw, (x, y), level_text, font)
        
        # BytesIOに保存
        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        
        logger.info(f"Level image composited: Lv.{level}")
        return output
    
    def composite_level_image_from_bytes(
        self,
        base_image_bytes: bytes,
        level: int,
    ) -> BytesIO:
        """
        バイトデータからレベルテキストを合成した画像を生成
        （テスト用メソッド）
        
        Args:
            base_image_bytes: ベース画像のバイトデータ
            level: 現在のレベル
        
        Returns:
            合成された画像のバイトストリーム（PNG形式）
        """
        # バイトデータから画像を読み込み
        image = Image.open(BytesIO(base_image_bytes))
        
        # RGBAモードに変換
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        
        draw = ImageDraw.Draw(image)
        font = self._get_font()
        
        # レベルテキスト
        level_text = f"Lv.{level}"
        
        # テキストサイズを取得
        bbox = draw.textbbox((0, 0), level_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 右下に配置
        x = image.width - text_width - self.padding
        y = image.height - text_height - self.padding
        
        # 縁取り付きテキストを描画
        self._draw_text_with_outline(draw, (x, y), level_text, font)
        
        # BytesIOに保存
        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        
        return output
