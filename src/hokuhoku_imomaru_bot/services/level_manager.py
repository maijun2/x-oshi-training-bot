"""
LevelManagerクラス

レベルアップ判定と必要XP管理を行います。
"""
from typing import Dict, Optional, Tuple


class LevelManager:
    """
    レベルアップ判定と必要XP管理を行うクラス
    
    Attributes:
        xp_table: レベルと必要経験値のマッピング {level: required_xp}
        max_level: 最大レベル
    """
    
    def __init__(self, xp_table: Dict[int, int]):
        """
        LevelManagerを初期化
        
        Args:
            xp_table: レベルと必要経験値のマッピング {level: required_xp}
        """
        if not xp_table:
            raise ValueError("xp_table cannot be empty")
        
        self.xp_table = xp_table
        self.max_level = max(xp_table.keys())
    
    def get_required_xp(self, level: int) -> Optional[int]:
        """
        指定レベルに必要な累積経験値を取得
        
        Args:
            level: レベル
        
        Returns:
            必要な累積経験値（レベルが存在しない場合はNone）
        """
        return self.xp_table.get(level)
    
    def get_xp_to_next_level(self, current_level: int, current_xp: float) -> Optional[int]:
        """
        次のレベルまでに必要な経験値を計算
        
        Args:
            current_level: 現在のレベル
            current_xp: 現在の累積経験値
        
        Returns:
            次のレベルまでに必要な経験値（最大レベルの場合はNone）
        """
        if current_level >= self.max_level:
            return None
        
        next_level_xp = self.get_required_xp(current_level + 1)
        if next_level_xp is None:
            return None
        
        remaining = next_level_xp - current_xp
        return max(0, int(remaining))
    
    def calculate_level(self, cumulative_xp: float) -> int:
        """
        累積経験値から現在のレベルを計算
        
        Args:
            cumulative_xp: 累積経験値
        
        Returns:
            現在のレベル
        """
        current_level = 1
        for level in sorted(self.xp_table.keys()):
            if cumulative_xp >= self.xp_table[level]:
                current_level = level
            else:
                break
        return current_level
    
    def check_level_up(
        self,
        current_level: int,
        cumulative_xp: float,
    ) -> Tuple[bool, int]:
        """
        レベルアップ判定を行う
        
        Args:
            current_level: 現在のレベル
            cumulative_xp: 累積経験値
        
        Returns:
            (レベルアップしたか, 新しいレベル)のタプル
        """
        if current_level >= self.max_level:
            return (False, current_level)
        
        new_level = self.calculate_level(cumulative_xp)
        
        if new_level > current_level:
            return (True, new_level)
        
        return (False, current_level)
    
    def get_level_progress(
        self,
        current_level: int,
        cumulative_xp: float,
    ) -> Dict[str, any]:
        """
        レベル進捗情報を取得
        
        Args:
            current_level: 現在のレベル
            cumulative_xp: 累積経験値
        
        Returns:
            レベル進捗情報
        """
        current_level_xp = self.get_required_xp(current_level) or 0
        next_level_xp = self.get_required_xp(current_level + 1)
        xp_to_next = self.get_xp_to_next_level(current_level, cumulative_xp)
        
        progress = {
            "current_level": current_level,
            "cumulative_xp": cumulative_xp,
            "current_level_xp": current_level_xp,
            "next_level_xp": next_level_xp,
            "xp_to_next_level": xp_to_next,
            "is_max_level": current_level >= self.max_level,
        }
        
        # 進捗率を計算（最大レベルでない場合）
        if next_level_xp is not None and next_level_xp > current_level_xp:
            xp_in_level = cumulative_xp - current_level_xp
            xp_needed = next_level_xp - current_level_xp
            progress["progress_percent"] = min(100.0, (xp_in_level / xp_needed) * 100)
        else:
            progress["progress_percent"] = 100.0
        
        return progress
