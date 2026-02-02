"""
ImageCompositorクラスのユニットテスト

要件 5.1, 5.2, 5.3, 5.4, 5.5, 5.6: プロフィール画像合成を検証
"""
import pytest
from unittest.mock import Mock, MagicMock
from io import BytesIO

from PIL import Image

from src.hokuhoku_imomaru_bot.services.image_compositor import ImageCompositor


def create_test_image(width: int = 400, height: int = 400, color: str = "blue") -> bytes:
    """テスト用の画像を作成"""
    image = Image.new("RGB", (width, height), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class TestImageCompositor:
    """ImageCompositorクラスのテスト"""
    
    @pytest.fixture
    def mock_s3_client(self):
        """モックS3クライアント"""
        return Mock()
    
    @pytest.fixture
    def compositor(self, mock_s3_client):
        """ImageCompositorインスタンス"""
        return ImageCompositor(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
        )
    
    def test_composite_level_image_returns_bytesio(self, compositor, mock_s3_client):
        """composite_level_image()がBytesIOを返すことを確認"""
        # モックS3レスポンスを設定
        test_image = create_test_image()
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        result = compositor.composite_level_image(5)
        
        assert isinstance(result, BytesIO)
    
    def test_composite_level_image_is_valid_png(self, compositor, mock_s3_client):
        """合成された画像が有効なPNG形式であることを確認"""
        test_image = create_test_image()
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        result = compositor.composite_level_image(10)
        
        # PILで読み込めることを確認
        image = Image.open(result)
        assert image.format == "PNG"
    
    def test_composite_level_image_preserves_size(self, compositor, mock_s3_client):
        """合成後も画像サイズが保持されることを確認"""
        test_image = create_test_image(width=300, height=300)
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        result = compositor.composite_level_image(15)
        
        image = Image.open(result)
        assert image.size == (300, 300)
    
    def test_composite_level_image_calls_s3(self, compositor, mock_s3_client):
        """S3からベース画像を取得することを確認"""
        test_image = create_test_image()
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        compositor.composite_level_image(1)
        
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="base_profile.png",
        )
    
    def test_composite_level_image_custom_key(self, mock_s3_client):
        """カスタムベース画像キーが使用されることを確認"""
        compositor = ImageCompositor(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            base_image_key="custom/profile.png",
        )
        
        test_image = create_test_image()
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        compositor.composite_level_image(1)
        
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="custom/profile.png",
        )
    
    def test_composite_level_image_s3_error(self, compositor, mock_s3_client):
        """S3エラー時に例外が発生することを確認"""
        mock_s3_client.get_object.side_effect = Exception("S3 Error")
        
        with pytest.raises(Exception, match="S3 Error"):
            compositor.composite_level_image(1)
    
    def test_composite_level_image_from_bytes(self, compositor):
        """composite_level_image_from_bytes()が正しく動作することを確認"""
        test_image = create_test_image()
        
        result = compositor.composite_level_image_from_bytes(test_image, 20)
        
        assert isinstance(result, BytesIO)
        image = Image.open(result)
        assert image.format == "PNG"
    
    def test_composite_level_image_different_levels(self, compositor, mock_s3_client):
        """異なるレベルで画像が生成されることを確認"""
        test_image = create_test_image()
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        for level in [1, 10, 50, 99]:
            result = compositor.composite_level_image(level)
            assert isinstance(result, BytesIO)
            # 読み込み位置をリセット
            result.seek(0)
            image = Image.open(result)
            assert image.format == "PNG"
    
    def test_composite_level_image_rgba_conversion(self, compositor, mock_s3_client):
        """RGB画像がRGBAに変換されることを確認"""
        # RGB画像を作成
        rgb_image = Image.new("RGB", (100, 100), "red")
        output = BytesIO()
        rgb_image.save(output, format="PNG")
        test_image = output.getvalue()
        
        mock_body = MagicMock()
        mock_body.read.return_value = test_image
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        
        result = compositor.composite_level_image(5)
        
        image = Image.open(result)
        assert image.mode == "RGBA"
    
    def test_custom_font_size(self, mock_s3_client):
        """カスタムフォントサイズが設定されることを確認"""
        compositor = ImageCompositor(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            font_size=48,
        )
        
        assert compositor.font_size == 48
    
    def test_custom_colors(self, mock_s3_client):
        """カスタム色が設定されることを確認"""
        compositor = ImageCompositor(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            text_color=(255, 0, 0),
            outline_color=(0, 255, 0),
        )
        
        assert compositor.text_color == (255, 0, 0)
        assert compositor.outline_color == (0, 255, 0)
    
    def test_custom_padding(self, mock_s3_client):
        """カスタムパディングが設定されることを確認"""
        compositor = ImageCompositor(
            s3_client=mock_s3_client,
            bucket_name="test-bucket",
            padding=20,
        )
        
        assert compositor.padding == 20
