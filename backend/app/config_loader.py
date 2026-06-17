import json
import os
from pathlib import Path
from typing import Any, Dict


_CONFIG_ROOT = Path(__file__).resolve().parent.parent.parent / "config"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fuel_config() -> Dict[str, Any]:
    """加载燃料类型配置"""
    return _load_json(_CONFIG_ROOT / "fuel_types.json")


def load_cfd_config() -> Dict[str, Any]:
    """加载CFD流体仿真参数配置"""
    return _load_json(_CONFIG_ROOT / "cfd_parameters.json")


def load_air_quality_config() -> Dict[str, Any]:
    """加载空气质量扩散参数配置"""
    return _load_json(_CONFIG_ROOT / "air_quality_parameters.json")


def load_dynasty_lamps_config() -> Dict[str, Any]:
    """加载朝代环保灯配置"""
    return _load_json(_CONFIG_ROOT / "dynasty_lamps.json")


def load_modern_purifiers_config() -> Dict[str, Any]:
    """加载现代空气净化器参数配置"""
    return _load_json(_CONFIG_ROOT / "modern_purifiers.json")


def load_banquet_scenes_config() -> Dict[str, Any]:
    """加载多灯宴会场景配置"""
    return _load_json(_CONFIG_ROOT / "banquet_scenes.json")


def get_config_root() -> Path:
    """返回配置根目录"""
    return _CONFIG_ROOT
