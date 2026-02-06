"""
AIGeneratorクラス

Amazon Bedrockを使用してキャラクターに合った応答テキストを生成します。
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# デフォルト応答テキスト（Bedrock API失敗時のフォールバック）
DEFAULT_RESPONSE_OSHI = "じゅりちゃんの投稿を見つけたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"
DEFAULT_RESPONSE_GROUP = "グループの投稿を見つけたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"
DEFAULT_RESPONSE_OSHI_RETWEET = "甘木ジュリちゃんがリポストしたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"
DEFAULT_RESPONSE_GROUP_RETWEET = "びっくえんじぇるがリポストしたｲﾓ🍠✨ #さつまいもの民 #びっくえんじぇる"

# 文字数制限
MAX_TEXT_LENGTH = 140

# プロンプトテンプレート
PROMPT_TEMPLATE = """あなたは「ほくほくいも丸くん🍠」というキャラクターです。
甘木ジュリさん(@juri_bigangel)の熱心なファンで、常に語尾に「◯◯ｲﾓ🍠」をつけて話します。

以下の投稿に対して、キャラクターに合った応答を生成してください：

{post_content}

制約:
- 適切な絵文字を使用すること
- 文末に必ず「#さつまいもの民 #びっくえんじぇる」を含めること
- ハッシュタグを含めて140文字以内に収めること
- 語尾は必ず「◯◯ｲﾓ🍠」の形式にすること（例：「嬉しいｲﾓ🍠」「最高ｲﾓ🍠」）
- 推しの名前は「甘木ジュリ」です。「天木」ではありません。必ず「甘木」と書いてください。

応答:"""

# 感情分類プロンプトテンプレート
EMOTION_CLASSIFICATION_PROMPT = """以下の応答文の感情を分類してください。

応答文: {response_text}

選択肢（emotion_keyのみを1つ返してください）:
- passion: 推しへの情熱・愛
- cheer: 躍動的な応援・エール
- gratitude_hug: 感謝・幸福感（抱擁）
- reverence: 感動・尊さ（拝む）
- excitement_move: 高揚・現場移動（チャリ）
- support_financial: 献身・支援（スパチャ）
- infatuation: 心酔・魅了（目がハート）
- deeply_moved: 感銘・落涙（感動の涙）
- kindness: 受容・穏やかな感謝（合掌）
- joy: 歓喜・達成感（やったあ）
- encouragement: 激励・ペンライト応援
- meal_time: 食事・期待（いただきます）

該当する感情がない場合は "none" と返してください。
emotion_keyのみを返してください（説明不要）:"""


class AIGenerator:
    """
    Amazon Bedrockを使用してキャラクターに合った応答テキストを生成するクラス
    
    Attributes:
        bedrock_client: boto3 Bedrock Runtimeクライアント
        model_id: 使用するモデルID
    """
    
    # Bedrock設定
    # Claude Haiku 4.5はInference Profile経由でのみ呼び出し可能
    # また、temperatureとtop_pは同時に指定できない
    DEFAULT_MODEL_ID = "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
    DEFAULT_MAX_TOKENS = 200
    DEFAULT_TEMPERATURE = 0.7
    
    def __init__(
        self,
        bedrock_client,
        model_id: str = DEFAULT_MODEL_ID,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        """
        AIGeneratorを初期化
        
        Args:
            bedrock_client: boto3 Bedrock Runtimeクライアント
            model_id: 使用するモデルID
            max_tokens: 最大トークン数
            temperature: 温度パラメータ
        """
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    def build_prompt(self, post_content: str) -> str:
        """
        プロンプトを構築
        
        Args:
            post_content: 元の投稿内容
        
        Returns:
            構築されたプロンプト
        """
        return PROMPT_TEMPLATE.format(post_content=post_content)
    
    def truncate_text(self, text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
        """
        テキストを指定文字数以内に切り詰め
        
        Args:
            text: 切り詰めるテキスト
            max_length: 最大文字数
        
        Returns:
            切り詰められたテキスト
        """
        if len(text) <= max_length:
            return text
        
        # ハッシュタグを保持するために、ハッシュタグ部分を抽出
        hashtags = "#さつまいもの民 #びっくえんじぇる"
        hashtag_len = len(hashtags)
        
        # ハッシュタグを除いた最大長
        content_max_len = max_length - hashtag_len - 1  # スペース分
        
        # テキストからハッシュタグを除去
        text_without_hashtags = text.replace(hashtags, "").strip()
        
        if len(text_without_hashtags) > content_max_len:
            # 切り詰めて「...」を追加
            truncated = text_without_hashtags[:content_max_len - 3] + "..."
            return f"{truncated} {hashtags}"
        
        return text
    
    def generate_response(
        self,
        post_content: str,
        post_type: str = "oshi",
    ) -> str:
        """
        投稿内容に基づいて応答テキストを生成
        
        Args:
            post_content: 元の投稿内容
            post_type: "oshi" または "group"
        
        Returns:
            生成された応答テキスト（140文字以内）
        """
        try:
            prompt = self.build_prompt(post_content)
            
            # Bedrock API呼び出し（Claude形式）
            # Claude Haiku 4.5ではtemperatureとtop_pを同時に指定できない
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
            
            # レスポンスをパース
            response_body = json.loads(response["body"].read())
            generated_text = response_body["content"][0]["text"].strip()
            
            # 140文字以内に切り詰め
            truncated_text = self.truncate_text(generated_text)
            
            logger.info(f"Generated response using model={self.model_id} for {post_type} post: {len(truncated_text)} chars")
            return truncated_text
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            # フォールバック応答を返す
            return self._get_fallback_response(post_type)
    
    def _get_fallback_response(self, post_type: str) -> str:
        """
        フォールバック応答を取得
        
        Args:
            post_type: "oshi", "group", "oshi_retweet", "group_retweet"
        
        Returns:
            フォールバック応答テキスト
        """
        if post_type == "oshi":
            return DEFAULT_RESPONSE_OSHI
        elif post_type == "oshi_retweet":
            return DEFAULT_RESPONSE_OSHI_RETWEET
        elif post_type == "group_retweet":
            return DEFAULT_RESPONSE_GROUP_RETWEET
        return DEFAULT_RESPONSE_GROUP
    
    def generate_retweet_response(self, post_type: str = "oshi") -> str:
        """
        リツイート（リポスト）用の固定応答を生成
        
        Args:
            post_type: "oshi" または "group"
        
        Returns:
            リツイート用応答テキスト
        """
        if post_type == "oshi":
            return DEFAULT_RESPONSE_OSHI_RETWEET
        return DEFAULT_RESPONSE_GROUP_RETWEET
    
    def classify_emotion(self, response_text: str) -> Optional[str]:
        """
        応答テキストの感情を分類
        
        Args:
            response_text: 分類する応答テキスト
        
        Returns:
            感情キー（emotion_key）、分類失敗時はNone
        """
        try:
            prompt = EMOTION_CLASSIFICATION_PROMPT.format(response_text=response_text)
            
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 50,
                "temperature": 0.0,  # 決定的な応答を得るため
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )
            
            response_body = json.loads(response["body"].read())
            emotion_key = response_body["content"][0]["text"].strip().lower()
            
            # 有効な感情キーかチェック
            valid_keys = {
                "passion", "cheer", "gratitude_hug", "reverence",
                "excitement_move", "support_financial", "infatuation",
                "deeply_moved", "kindness", "joy", "encouragement", "meal_time"
            }
            
            if emotion_key in valid_keys:
                logger.info(f"Classified emotion: {emotion_key}")
                return emotion_key
            elif emotion_key == "none":
                logger.info("Emotion classification returned 'none'")
                return None
            else:
                logger.warning(f"Unknown emotion key returned: {emotion_key}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to classify emotion: {e}")
            return None
