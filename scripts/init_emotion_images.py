#!/usr/bin/env python3
"""
感情画像マスタの初期データをDynamoDBに投入するスクリプト

使用方法:
    AWS_DEFAULT_REGION=ap-northeast-1 uv run python scripts/init_emotion_images.py
"""
import boto3

# 感情画像マスタデータ
EMOTION_IMAGES_DATA = [
    {"emotion_key": "passion", "filename": "imomaru_oshi.png", "description": "推しへの情熱・愛"},
    {"emotion_key": "cheer", "filename": "imomaru_cheer.png", "description": "躍動的な応援・エール"},
    {"emotion_key": "gratitude_hug", "filename": "imomaru_thanks.png", "description": "感謝・幸福感（抱擁）"},
    {"emotion_key": "reverence", "filename": "imomaru_toutoi.png", "description": "感動・尊さ（拝む）"},
    {"emotion_key": "excitement_move", "filename": "imomaru_chari.png", "description": "高揚・現場移動（チャリ）"},
    {"emotion_key": "support_financial", "filename": "imomaru_superchat.png", "description": "献身・支援（スパチャ）"},
    {"emotion_key": "infatuation", "filename": "imomaru_love.png", "description": "心酔・魅了（目がハート）"},
    {"emotion_key": "deeply_moved", "filename": "imomaru_moved.png", "description": "感銘・落涙（感動の涙）"},
    {"emotion_key": "kindness", "filename": "imomaru_kindness.png", "description": "受容・穏やかな感謝（合掌）"},
    {"emotion_key": "joy", "filename": "imomaru_joy.png", "description": "歓喜・達成感（やったあ）"},
    {"emotion_key": "encouragement", "filename": "imomaru_support.png", "description": "激励・ペンライト応援"},
    {"emotion_key": "meal_time", "filename": "imomaru_eat.png", "description": "食事・期待（いただきます）"},
]

TABLE_NAME = "imomaru-bot-emotion-images"


def main():
    """メイン処理"""
    dynamodb = boto3.client("dynamodb")
    
    print(f"Inserting {len(EMOTION_IMAGES_DATA)} emotion images into {TABLE_NAME}...")
    
    for item in EMOTION_IMAGES_DATA:
        dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={
                "emotion_key": {"S": item["emotion_key"]},
                "filename": {"S": item["filename"]},
                "description": {"S": item["description"]},
            },
        )
        print(f"  ✓ {item['emotion_key']} -> {item['filename']}")
    
    print(f"\nDone! {len(EMOTION_IMAGES_DATA)} items inserted.")


if __name__ == "__main__":
    main()
