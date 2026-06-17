"""
vr_gong_deng: 公众虚拟操作宫灯体验模块
职责：
  1. 虚拟操作参数校验（火焰强度、堵塞度、燃料类型、灯型）
  2. 操作前后净化效果预测（差值分析）
  3. 教育性科普知识生成（按灯型/按操作维度）
  4. 滑块分级推荐（安全区间/建议区间/危险区间）
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class VRParameterInfo:
    """单个滑块的参数说明 + 分级推荐"""
    key: str
    name_cn: str
    unit: str
    min_value: float
    max_value: float
    default_value: float
    recommended_min: float
    recommended_max: float
    warning_min: float = float("-inf")
    warning_max: float = float("inf")
    description: str = ""
    grade_labels: List[str] = field(default_factory=list)   # 分级名称（从低到高）
    grade_colors: List[str] = field(default_factory=list)   # 分级颜色
    grade_thresholds: List[float] = field(default_factory=list)  # 分级阈值


@dataclass
class VRPurificationDelta:
    """操作前后净化效果变化预测"""
    parameter_changed: str
    old_value: float
    new_value: float
    old_settling_efficiency: float
    new_settling_efficiency: float
    delta_settling_efficiency_pct: float   # ±pct 变化
    old_purification_rate: float
    new_purification_rate: float
    delta_purification_rate_pct_points: float
    old_avg_pm25_ugm3: float
    new_avg_pm25_ugm3: float
    delta_pm25_ugm3: float
    feedback_level: str   # "improvement" / "neutral" / "degradation" / "warning"
    feedback_text: str


@dataclass
class VREduFacts:
    """VR 体验教育性科普内容"""
    lamp_type: str
    general_history: List[str] = field(default_factory=list)
    fluid_mechanics_principle: List[str] = field(default_factory=list)
    parameter_specific: Dict[str, List[str]] = field(default_factory=dict)
    archaeological_findings: List[str] = field(default_factory=list)
    modern_comparison: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 虚拟宫灯管理器
# ---------------------------------------------------------------------------
class VRGongDeng:
    """公众虚拟操作宫灯体验管理器"""

    # 火焰强度分级
    FLAME_GRADES = VRParameterInfo(
        key="flame_intensity",
        name_cn="灯油火焰强度",
        unit="相对倍率",
        min_value=0.0,
        max_value=1.5,
        default_value=0.7,
        recommended_min=0.4,
        recommended_max=0.9,
        warning_min=0.2,
        warning_max=1.2,
        description="模拟灯油燃烧的火焰大小。火焰越大，排烟量越多，温度越高，但需要更大的自然对流力才能有效净化。",
        grade_labels=["微火", "小火/节能", "推荐亮度", "旺火", "浓烟警告"],
        grade_colors=["#64B5F6", "#81C784", "#4CAF50", "#FFB74D", "#E57373"],
        grade_thresholds=[0.2, 0.4, 0.9, 1.2, 1.5],
    )

    # 烟道堵塞度分级
    BLOCKAGE_GRADES = VRParameterInfo(
        key="blockage_degree",
        name_cn="烟道清洁度（堵塞度）",
        unit="堵塞比例",
        min_value=0.0,
        max_value=1.0,
        default_value=0.05,
        recommended_min=0.0,
        recommended_max=0.25,
        warning_min=0.25,
        warning_max=0.6,
        description="模拟长期使用后烟道内烟尘焦油的堵塞情况。堵塞会降低烟道流通面积，使烟气无法顺利沉降，烟雾从灯口溢出。",
        grade_labels=["通畅如新", "轻微积灰", "需要清洁", "严重堵塞", "完全堵塞"],
        grade_colors=["#81C784", "#AED581", "#FFB74D", "#FF8A65", "#E57373"],
        grade_thresholds=[0.1, 0.25, 0.5, 0.75, 1.0],
    )

    # 燃料类型
    FUEL_TYPES = {
        "animal_fat": {
            "name_cn": "动物脂肪（汉代常用）",
            "smoke_factor": 1.0,
            "calorific_value_kj_kg": 32400,
            "description": "牛脂、羊脂等，汉代贵族主要灯油来源。烟量适中，燃烧稳定。",
            "historical_note": "《史记·货殖列传》记载：'掘冢搏掩，任侠并兼，借交报仇，纂逐幽隐，不避法禁，走死地如骛者，其实皆为财用耳。'汉代贵族照明多用动物脂肪。",
        },
        "vegetable_oil": {
            "name_cn": "植物油（隋唐后普及）",
            "smoke_factor": 0.7,
            "calorific_value_kj_kg": 37000,
            "description": "麻油、豆油等，烟量较少，亮度较高，汉以后逐渐普及。",
            "historical_note": "南北朝时期贾思勰《齐民要术》已有榨油技术记载，植物油到隋唐时期逐渐成为主流灯油。",
        },
        "beeswax": {
            "name_cn": "蜂蜡（古代奢侈品）",
            "smoke_factor": 0.3,
            "calorific_value_kj_kg": 42000,
            "description": "蜜蜡燃烧烟极少，有淡淡香味，古代只有帝王和高级贵族才能使用。",
            "historical_note": "《西京杂记》记载南越王向汉高祖进贡蜜蜡烛二百枚，可见蜜蜡在汉代是珍稀贡品。",
        },
        "kerosene": {
            "name_cn": "煤油（近代对比参考）",
            "smoke_factor": 1.8,
            "calorific_value_kj_kg": 43000,
            "description": "19世纪后才传入中国的现代灯油，烟量大，亮度高。",
            "historical_note": "鸦片战争后煤油随洋货进入中国，民间称'洋油'，20世纪中期前广泛使用。",
        },
    }

    # 科普知识库（按灯型组织）
    EDUCATION_FACTS_DB = {
        "changxin_gongdeng": {
            "general_history": [
                "长信宫灯是西汉中山靖王刘胜妻窦绾墓出土，1968年河北满城陵山一号汉墓。",
                "灯具整体为一宫女跪坐执灯造型，通体鎏金，高48cm，重15.85kg，属国家一级文物。",
                "灯体刻有'长信尚浴'等铭文，因曾在窦太后长信宫使用而得名。",
                "1971年经郭沫若先生考证，认为是'中华第一灯'，现藏于中国国家博物馆。",
            ],
            "fluid_mechanics_principle": [
                "宫女右臂中空形成烟道，灯焰加热空气产生浮力，热烟气顺着右臂自然上升进入宫女体内。",
                "宫女体内盛水，烟气经过水面时，水溶性烟尘和PM2.5被水吸收——这就是2000年前的'水滤技术'。",
                "经过水滤的气体在腹腔内减速停留，大颗粒烟尘靠重力沉降——利用的是重力沉降原理。",
                "灯罩可左右开合调节进风量，控制火焰大小和明暗——这是最早的风量调节阀设计。",
                "烟气停留时间 = 腔体体积 / 烟气流速，约 3.5L / 0.4m/s ≈ 8.75秒，保证有足够沉降时间。",
            ],
            "parameter_specific": {
                "flame_intensity": [
                    "火焰强度<0.2：燃料不足，亮度低，排烟少，净化效率约55%。",
                    "火焰强度0.4-0.9：推荐区间，浮力和排烟平衡，净化效率可达65-70%。",
                    "火焰强度>1.2：燃烧过于剧烈，排烟超过烟道处理能力，烟从灯口溢出，净化效率骤降至35%以下。",
                ],
                "blockage_degree": [
                    "堵塞度<10%：通畅状态，烟道雷诺数Re≈800（层流），净化效率最佳。",
                    "堵塞度25-50%：需清洁，烟道有效面积缩小，流速增大Re≈2000（过渡流），净化效率下降10-15%。",
                    "堵塞度>75%：严重堵塞，烟气几乎无法通过，大量从灯口直接溢出，净化失效。",
                ],
                "fuel_type": [
                    "蜂蜡烟量最小（0.3倍），是汉代最理想的灯油，但极为昂贵。",
                    "动物脂肪是汉代主流燃料，烟量适中，长信宫灯就是为这种燃料设计的。",
                    "煤油烟量最大（1.8倍），如穿越回汉代使用，宫灯将无法处理。",
                ],
            },
            "archaeological_findings": [
                "出土时腹腔内有白色水碱痕迹，证实古代确实在宫女体内注水进行水滤。",
                "烟道内壁有焦油状附着物，是长期使用后的烟尘残留，印证堵塞问题真实存在。",
                "灯盘和灯罩设计为可拆卸结构，便于清洁烟道——古人已经考虑到维护问题！",
            ],
            "modern_comparison": [
                "长信宫灯净化效率（约60%）≈ 现代粗效G4滤网水平。",
                "CADR估算值≈ 80 m³/h ≈ 现代桌面型迷你净化器。",
                "噪音≈ 5dB ≈ 完全无声，现代净化器最低也有30dB。",
                "环保价值：100分 vs 现代净化器约40-60分（需电+耗材）。",
            ],
        },
        "yanyu_deng": {
            "general_history": [
                "雁鱼灯1985年出土于山西省朔州市朔城区照十八庄村一号汉墓。",
                "整体造型为鸿雁回首衔鱼，鱼腹中空接灯罩，雁颈为烟道，雁腹盛水。",
                "通高54cm，长37cm，属国家一级文物，现藏山西博物院。",
                "与长信宫灯设计思路一致，但造型更生动有趣，是汉代仿生灯具代表。",
            ],
            "fluid_mechanics_principle": [
                "雁颈为S形弯曲烟道，比长信宫灯的直烟道更长，烟气停留时间增加约30%。",
                "S形弯道会产生离心效应，使烟气中的颗粒物被甩向管壁沉降——相当于'惯性分离器'。",
                "鱼身灯罩导光向前，光线集中于前方桌面，是最早的'定向照明'设计。",
            ],
        },
        "niu_deng": {
            "general_history": [
                "错银铜牛灯1980年出土于江苏省扬州市邗江县甘泉山二号汉墓。",
                "整体造型为一头驯牛伫立，牛背驮灯盏，通体饰错银纹饰，工艺极为精湛。",
                "通高46cm，长36.4cm，属国家一级文物，现藏南京博物院。",
                "为东汉光武帝刘秀第九子刘荆墓出土，诸侯王级别的奢侈品。",
            ],
            "fluid_mechanics_principle": [
                "牛角双通道烟道设计，两根烟道并联，烟气流通面积比单烟道大40%。",
                "双烟道同时工作，降低了烟气流速，延长了在牛腹中的停留时间，沉降更充分。",
                "牛腹容量比长信宫灯大，盛水量更多，水滤效果更好。",
            ],
        },
    }

    def __init__(self, dynasty_lamps_cfg: Optional[Dict] = None):
        self.lamps_db = (dynasty_lamps_cfg or {}).get("dynasty_lamps", {})

    # ------------------------------------------------------------------
    # 1. 参数校验
    # ------------------------------------------------------------------
    def validate_flame_intensity(self, value: float) -> Tuple[bool, str, str]:
        """
        校验火焰强度
        返回 (是否合法, 等级标签, 说明文本)
        """
        info = self.FLAME_GRADES
        if value < info.min_value or value > info.max_value:
            return False, "超限", f"火焰强度应在 [{info.min_value}, {info.max_value}] 之间"
        label = self._get_grade_label(info, value)
        level = self._get_feedback_level(value, info)
        suggestion = self._get_value_suggestion(value, info, "火焰")
        return True, label, suggestion

    def validate_blockage_degree(self, value: float) -> Tuple[bool, str, str]:
        """校验烟道堵塞度"""
        info = self.BLOCKAGE_GRADES
        if value < info.min_value or value > info.max_value:
            return False, "超限", f"堵塞度应在 [{info.min_value}, {info.max_value}] 之间"
        label = self._get_grade_label(info, value)
        level = self._get_feedback_level(value, info)
        suggestion = self._get_value_suggestion(value, info, "堵塞")
        return True, label, suggestion

    def validate_lamp_type(self, lamp_type: str) -> bool:
        return lamp_type in self.lamps_db or lamp_type in self.EDUCATION_FACTS_DB

    def validate_fuel_type(self, fuel_type: str) -> bool:
        return fuel_type in self.FUEL_TYPES

    # ------------------------------------------------------------------
    # 2. 操作前后净化效果预测
    # ------------------------------------------------------------------
    def predict_purification_delta(
        self,
        parameter: str,
        old_value: float,
        new_value: float,
        base_settling_efficiency: float = 0.6,
        base_purification_rate: float = 0.55,
        base_avg_pm25: float = 35.0,
        lamp_type: str = "changxin_gongdeng",
    ) -> VRPurificationDelta:
        """
        预测参数调整后净化效果变化趋势。
        注意：这是基于系数的快速估算，用于前端实时反馈，非精确 CFD 结果。
        精确结果应调用 CFD_simulator.simulate()。
        """
        if parameter == "flame_intensity":
            # 火焰影响：0.7 左右最优（正态形），两边下降
            def eff_factor(x):
                # 以 x=0.7 为中心的高斯峰，1.1倍放大
                return min(1.2, max(0.3, 1.15 * np.exp(-((x - 0.7) ** 2) / 0.25)))
            old_factor = eff_factor(old_value)
            new_factor = eff_factor(new_value)
        elif parameter == "blockage_degree":
            # 堵塞越大，效率越低，线性衰减到 0.1 为止
            def eff_factor(x):
                return max(0.1, 1.0 - 1.1 * x)
            old_factor = eff_factor(old_value)
            new_factor = eff_factor(new_value)
        elif parameter == "fuel_type_switch":
            fuels = self.FUEL_TYPES
            # old_value/new_value 这里是 smoke_factor
            # 烟越大，越难处理，效率越低
            old_factor = max(0.4, 1.0 - 0.3 * (old_value - 1.0))
            new_factor = max(0.4, 1.0 - 0.3 * (new_value - 1.0))
        else:
            old_factor = 1.0
            new_factor = 1.0

        old_settle = min(0.99, max(0.01, base_settling_efficiency * old_factor))
        new_settle = min(0.99, max(0.01, base_settling_efficiency * new_factor))
        old_rate = min(0.99, max(0.01, base_purification_rate * old_factor))
        new_rate = min(0.99, max(0.01, base_purification_rate * new_factor))
        old_pm25 = base_avg_pm25 / max(old_factor, 0.3)
        new_pm25 = base_avg_pm25 / max(new_factor, 0.3)

        delta_settle_pct = round((new_settle - old_settle) * 100, 2)
        delta_rate_pct = round((new_rate - old_rate) * 100, 2)
        delta_pm25 = round(new_pm25 - old_pm25, 2)

        # 判断反馈等级
        if abs(delta_settle_pct) < 1.0 and abs(delta_pm25) < 1.0:
            level, text = "neutral", "操作对净化效果影响很小"
        elif delta_settle_pct > 2.0 and delta_pm25 < -2.0:
            level, text = (
                "improvement",
                f"好选择！沉降效率 +{delta_settle_pct}%，PM2.5 浓度 {delta_pm25} μg/m³",
            )
        elif delta_settle_pct < -3.0 or delta_pm25 > 5.0:
            level, text = (
                "warning",
                f"注意：沉降效率 {delta_settle_pct}%，PM2.5 上升 +{delta_pm25} μg/m³，"
                f"建议回调参数",
            )
        else:
            level = "degradation" if delta_settle_pct < 0 else "improvement"
            text = (
                f"净化效率{delta_settle_pct:+.2f}%，PM2.5{delta_pm25:+.2f} μg/m³"
            )

        return VRPurificationDelta(
            parameter_changed=parameter,
            old_value=old_value,
            new_value=new_value,
            old_settling_efficiency=round(old_settle, 4),
            new_settling_efficiency=round(new_settle, 4),
            delta_settling_efficiency_pct=delta_settle_pct,
            old_purification_rate=round(old_rate, 4),
            new_purification_rate=round(new_rate, 4),
            delta_purification_rate_pct_points=delta_rate_pct,
            old_avg_pm25_ugm3=round(old_pm25, 2),
            new_avg_pm25_ugm3=round(new_pm25, 2),
            delta_pm25_ugm3=delta_pm25,
            feedback_level=level,
            feedback_text=text,
        )

    # ------------------------------------------------------------------
    # 3. 教育性科普内容
    # ------------------------------------------------------------------
    def get_edu_facts(self, lamp_type: str) -> VREduFacts:
        """返回指定灯型的完整教育科普内容"""
        if lamp_type not in self.EDUCATION_FACTS_DB:
            lamp_type = "changxin_gongdeng"
        db = self.EDUCATION_FACTS_DB[lamp_type]
        lamp_cfg = self.lamps_db.get(lamp_type, {})

        # 把考古数据从 cfg 合并进 archaeological_findings
        archaeology = list(db.get("archaeological_findings", []))
        unearthed = lamp_cfg.get("unearthed_location")
        unearthed_year = lamp_cfg.get("unearthed_year")
        collection = lamp_cfg.get("current_collection")
        ref = lamp_cfg.get("archaeological_reference")
        if unearthed and unearthed_year:
            archaeology.append(f"出土地：{unearthed}（{unearthed_year}年）")
        if collection:
            archaeology.append(f"现藏：{collection}")
        if ref:
            archaeology.append(f"考古报告：{ref}")

        return VREduFacts(
            lamp_type=lamp_type,
            general_history=db.get("general_history", []),
            fluid_mechanics_principle=db.get("fluid_mechanics_principle", []),
            parameter_specific=db.get("parameter_specific", {}),
            archaeological_findings=archaeology,
            modern_comparison=db.get("modern_comparison", []),
        )

    # ------------------------------------------------------------------
    # 4. 获取完整 VR 参数元数据（给前端 UI 生成 slider）
    # ------------------------------------------------------------------
    def get_vr_parameter_schema(self) -> Dict[str, Any]:
        return {
            "flame_intensity": {
                "key": self.FLAME_GRADES.key,
                "name": self.FLAME_GRADES.name_cn,
                "unit": self.FLAME_GRADES.unit,
                "min": self.FLAME_GRADES.min_value,
                "max": self.FLAME_GRADES.max_value,
                "default": self.FLAME_GRADES.default_value,
                "recommended_range": [
                    self.FLAME_GRADES.recommended_min,
                    self.FLAME_GRADES.recommended_max,
                ],
                "warning_range": [
                    self.FLAME_GRADES.warning_min,
                    self.FLAME_GRADES.warning_max,
                ],
                "description": self.FLAME_GRADES.description,
                "grades": [
                    {
                        "label": self.FLAME_GRADES.grade_labels[i],
                        "color": self.FLAME_GRADES.grade_colors[i],
                        "threshold": self.FLAME_GRADES.grade_thresholds[i],
                    }
                    for i in range(len(self.FLAME_GRADES.grade_labels))
                ],
            },
            "blockage_degree": {
                "key": self.BLOCKAGE_GRADES.key,
                "name": self.BLOCKAGE_GRADES.name_cn,
                "unit": self.BLOCKAGE_GRADES.unit,
                "min": self.BLOCKAGE_GRADES.min_value,
                "max": self.BLOCKAGE_GRADES.max_value,
                "default": self.BLOCKAGE_GRADES.default_value,
                "recommended_range": [
                    self.BLOCKAGE_GRADES.recommended_min,
                    self.BLOCKAGE_GRADES.recommended_max,
                ],
                "warning_range": [
                    self.BLOCKAGE_GRADES.warning_min,
                    self.BLOCKAGE_GRADES.warning_max,
                ],
                "description": self.BLOCKAGE_GRADES.description,
                "grades": [
                    {
                        "label": self.BLOCKAGE_GRADES.grade_labels[i],
                        "color": self.BLOCKAGE_GRADES.grade_colors[i],
                        "threshold": self.BLOCKAGE_GRADES.grade_thresholds[i],
                    }
                    for i in range(len(self.BLOCKAGE_GRADES.grade_labels))
                ],
            },
            "fuel_types": [
                {
                    "key": k,
                    "name": v["name_cn"],
                    "smoke_factor": v["smoke_factor"],
                    "description": v["description"],
                    "historical_note": v["historical_note"],
                }
                for k, v in self.FUEL_TYPES.items()
            ],
            "lamp_types": [
                {
                    "key": k,
                    "name": v.get("name", k),
                    "dynasty": v.get("dynasty", ""),
                }
                for k, v in self.lamps_db.items()
            ],
        }

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    @staticmethod
    def _get_grade_label(info: VRParameterInfo, value: float) -> str:
        thresholds = info.grade_thresholds
        labels = info.grade_labels
        for i, th in enumerate(thresholds):
            if value <= th:
                return labels[i]
        return labels[-1]

    @staticmethod
    def _get_feedback_level(value: float, info: VRParameterInfo) -> str:
        if info.recommended_min <= value <= info.recommended_max:
            return "optimal"
        elif value < info.warning_min or value > info.warning_max:
            return "warning"
        else:
            return "acceptable"

    @staticmethod
    def _get_value_suggestion(value: float, info: VRParameterInfo, name: str) -> str:
        level = VRGongDeng._get_feedback_level(value, info)
        if level == "optimal":
            return f"✅ {info.name_cn} = {value} 处于推荐区间 [{info.recommended_min}, {info.recommended_max}]"
        elif level == "acceptable":
            return f"ℹ️ {info.name_cn} = {value} 可以接受，建议调整到 [{info.recommended_min}, {info.recommended_max}] 获得最佳效果"
        else:
            if value < info.warning_min:
                return f"⚠️ {name}过低（{value}），效率不高，建议 ≥ {info.warning_min}"
            else:
                return f"⚠️ {name}过高（{value}），净化可能失效，建议 ≤ {info.warning_max}"

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    @staticmethod
    def delta_to_dict(d: VRPurificationDelta) -> Dict[str, Any]:
        return {
            "parameter_changed": d.parameter_changed,
            "old_value": d.old_value,
            "new_value": d.new_value,
            "old_settling_efficiency": d.old_settling_efficiency,
            "new_settling_efficiency": d.new_settling_efficiency,
            "delta_settling_efficiency_pct": d.delta_settling_efficiency_pct,
            "old_purification_rate": d.old_purification_rate,
            "new_purification_rate": d.new_purification_rate,
            "delta_purification_rate_pct_points": d.delta_purification_rate_pct_points,
            "old_avg_pm25_ugm3": d.old_avg_pm25_ugm3,
            "new_avg_pm25_ugm3": d.new_avg_pm25_ugm3,
            "delta_pm25_ugm3": d.delta_pm25_ugm3,
            "feedback_level": d.feedback_level,
            "feedback_text": d.feedback_text,
        }

    @staticmethod
    def facts_to_dict(f: VREduFacts) -> Dict[str, Any]:
        return {
            "lamp_type": f.lamp_type,
            "general_history": f.general_history,
            "fluid_mechanics_principle": f.fluid_mechanics_principle,
            "parameter_specific": f.parameter_specific,
            "archaeological_findings": f.archaeological_findings,
            "modern_comparison": f.modern_comparison,
        }


# numpy 兼容（避免未安装情况下也能导入）
try:
    import numpy as np  # noqa: F401  (上面的方法中使用)
except ImportError:
    # 简易替换：math 实现 exp
    import math
    class _MiniNp:
        @staticmethod
        def exp(x): return math.exp(x)
    np = _MiniNp()
