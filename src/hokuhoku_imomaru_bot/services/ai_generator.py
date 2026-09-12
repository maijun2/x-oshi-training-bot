"""
AIGeneratorクラス

キャラクターに合った応答テキストを生成します。

生成元は 2 段構え（フェーズ2a）:
1. 頭脳（AgentCore Runtime、BrainClient 経由）— 設定されていればまずこちら
2. Bedrock Haiku 直呼び — 頭脳が未設定、または頭脳の呼び出しに失敗したときのフォールバック
   （失敗は logger.error で記録し、imomaru-bot-app-errors アラームを鳴らす）
"""
import json
import logging
from typing import Any, Dict, Optional

from ..prompts import (  # noqa: F401  (re-export: 既存の import 経路を維持)
    DEFAULT_RESPONSE_OSHI,
    DEFAULT_RESPONSE_GROUP,
    DEFAULT_RESPONSE_OSHI_RETWEET,
    DEFAULT_RESPONSE_GROUP_RETWEET,
    DEFAULT_REPLY_RESPONSE_TEMPLATE,
    MAX_TEXT_LENGTH,
    PROMPT_TEMPLATE,
    REPLY_PROMPT_TEMPLATE,
    EMOTION_CLASSIFICATION_PROMPT,
    VALID_EMOTION_KEYS,
)
from ..utils.brain_client import BrainClient, BrainError

logger = logging.getLogger(__name__)


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
        brain_client: Optional[BrainClient] = None,
    ):
        """
        AIGeneratorを初期化
        
        Args:
            bedrock_client: boto3 Bedrock Runtimeクライアント（フォールバック用）
            model_id: 使用するモデルID（フォールバック用）
            max_tokens: 最大トークン数
            temperature: 温度パラメータ
            brain_client: 頭脳（AgentCore Runtime）クライアント。None なら Bedrock 直呼びのみ
        """
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.brain_client = brain_client
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
        
        # ハッシュタグがない場合でも、本文が短ければハッシュタグを追加
        if hashtags not in text:
            return f"{text_without_hashtags} {hashtags}"
        
        return text
    
    def _ask_brain(self, task: str, task_input: Dict[str, Any]) -> Optional[str]:
        """
        頭脳にタスクを依頼する。未設定なら None、失敗したら ERROR ログを出して None
        （呼び出し側は None のとき Bedrock 直呼びにフォールバックする）
        """
        if self.brain_client is None:
            return None
        try:
            return self.brain_client.invoke(task, task_input)
        except BrainError as e:
            logger.error(f"Brain failed for task={task}; falling back to direct Bedrock: {e}")
            return None

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
        brain_text = self._ask_brain("oshi_response", {"post_content": post_content, "post_type": post_type})
        if brain_text is not None:
            truncated_text = self.truncate_text(brain_text)
            logger.info(f"Generated response using brain for {post_type} post: {len(truncated_text)} chars")
            return truncated_text

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
            brain_text = self._ask_brain("classify_emotion", {"response_text": response_text})
            if brain_text is not None:
                emotion_key = brain_text.strip().lower()
            else:
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
            if emotion_key in VALID_EMOTION_KEYS:
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
    def generate_reply_response(
        self,
        reply_text: str,
        reply_username: str,
        bot_tweet_text: str,
    ) -> str:
        """
        リプライに対する応答テキストを生成

        Args:
            reply_text: リプライの本文
            reply_username: リプライユーザーのユーザー名
            bot_tweet_text: ボットが投稿した元のツイート本文

        Returns:
            生成された応答テキスト（140文字以内）
        """
        brain_text = self._ask_brain(
            "reply_response",
            {"reply_text": reply_text, "reply_username": reply_username, "bot_tweet_text": bot_tweet_text},
        )
        if brain_text is not None:
            truncated_text = self.truncate_text(brain_text)
            logger.info(f"Generated reply response using brain: {len(truncated_text)} chars")
            return truncated_text

        try:
            prompt = REPLY_PROMPT_TEMPLATE.format(
                username=reply_username,
                bot_tweet_text=bot_tweet_text,
                reply_text=reply_text,
            )

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

            response_body = json.loads(response["body"].read())
            generated_text = response_body["content"][0]["text"].strip()

            truncated_text = self.truncate_text(generated_text)

            logger.info(f"Generated reply response: {len(truncated_text)} chars")
            return truncated_text

        except Exception as e:
            logger.warning(f"Failed to generate reply response: {e}")
            return DEFAULT_REPLY_RESPONSE_TEMPLATE.format(username=reply_username)

